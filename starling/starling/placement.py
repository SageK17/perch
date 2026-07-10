"""
Redundancy policy and provider selection.

Two questions live here:

  1. *How* is a chunk made durable -- N full replicas, or (k, m) erasure coding?
     That's the :class:`Policy`.
  2. *Which* providers hold the copies/shards of a given chunk? That's
     :func:`choose_providers`, which uses weighted rendezvous hashing (a.k.a.
     highest-random-weight) so that placement is:
       - spread roughly in proportion to each provider's free space,
       - deterministic for a given chunk + provider set (stable, no central map),
       - and minimally disturbed when a provider is added or removed.

The engine still records the actual chosen locations in the manifest -- HRW
decides placement at write time; the manifest is the source of truth for reads
and repair.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from .backends.base import Backend


class NotEnoughProviders(RuntimeError):
    """Fewer healthy providers than the policy needs to place a chunk."""


@dataclass(frozen=True)
class Policy:
    """How much redundancy each chunk gets, and by what method."""

    mode: str = "replicate"  # "replicate" | "erasure"
    replicas: int = 3
    k: int = 4
    m: int = 2

    def __post_init__(self) -> None:
        if self.mode not in ("replicate", "erasure"):
            raise ValueError("mode must be 'replicate' or 'erasure'")
        if self.mode == "replicate" and self.replicas < 1:
            raise ValueError("replicas must be >= 1")
        if self.mode == "erasure" and (self.k < 1 or self.m < 0):
            raise ValueError("need k >= 1 and m >= 0")

    def fan_out(self) -> int:
        """Number of distinct providers a single chunk touches."""
        return self.replicas if self.mode == "replicate" else self.k + self.m

    def failures_tolerated(self) -> int:
        """How many providers can vanish while every chunk stays recoverable."""
        return self.replicas - 1 if self.mode == "replicate" else self.m

    def overhead(self) -> float:
        """Stored bytes per logical byte (before dedup/compression)."""
        return float(self.replicas) if self.mode == "replicate" else (self.k + self.m) / self.k

    def describe(self) -> str:
        if self.mode == "replicate":
            return f"{self.replicas}x replication (survives {self.failures_tolerated()} lost providers)"
        return (
            f"Reed-Solomon ({self.k}+{self.m}) "
            f"(survives {self.m} lost providers, {self.overhead():.2f}x space)"
        )

    def to_dict(self) -> Dict:
        return {"mode": self.mode, "replicas": self.replicas, "k": self.k, "m": self.m}

    @classmethod
    def from_dict(cls, d: Dict) -> "Policy":
        return cls(
            mode=d.get("mode", "replicate"),
            replicas=int(d.get("replicas", 3)),
            k=int(d.get("k", 4)),
            m=int(d.get("m", 2)),
        )


def _hrw_score(provider_id: str, chunk_key: bytes, weight: float) -> float:
    """Weighted highest-random-weight score. Bigger weight -> chosen more often."""
    digest = hashlib.sha256(provider_id.encode("utf-8") + chunk_key).digest()
    u = int.from_bytes(digest[:8], "big") / float(1 << 64)
    u = min(max(u, 1e-12), 1.0 - 1e-12)
    return -weight / math.log(u)


def choose_providers(
    policy: Policy,
    providers: Sequence[Backend],
    chunk_hash: bytes,
    healthy: Optional[set] = None,
    exclude: Optional[set] = None,
) -> List[str]:
    """Pick ``policy.fan_out()`` distinct providers for one chunk.

    ``healthy`` restricts to providers currently reachable; ``exclude`` skips
    ones already holding this chunk (used when repairing to a fresh provider).
    """
    need = policy.fan_out()
    exclude = exclude or set()
    eligible = [
        p
        for p in providers
        if p.id not in exclude
        and (healthy is None or p.id in healthy)
        and p.free_bytes() > 0
    ]
    if len(eligible) < need:
        raise NotEnoughProviders(
            f"policy needs {need} providers, only {len(eligible)} are eligible"
        )
    ranked = sorted(
        eligible,
        key=lambda p: _hrw_score(p.id, chunk_hash, max(float(p.free_bytes()), 1.0)),
        reverse=True,
    )
    return [p.id for p in ranked[:need]]
