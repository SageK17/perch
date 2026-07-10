"""
The provider SPI.

A *backend* is any dumb blob store keyed by string: put, get, delete, exists,
list, and report how much it holds. That's the entire contract. Starling does
all the intelligence -- chunking, encryption, dedup, redundancy -- on top, so a
backend can be a folder, an in-memory dict, an S3 bucket, a Google Drive, a
Dropbox, or a WebDAV share, and the engine never has to care which.

Everything handed to a backend is already encrypted ciphertext under an opaque
key, so a provider learns nothing about your data or filenames.
"""

from __future__ import annotations

import abc
from typing import Iterator


class BlobNotFound(KeyError):
    """Raised by :meth:`Backend.get` when a key isn't present."""


class Backend(abc.ABC):
    #: Stable identifier used in the manifest to say where a shard lives.
    id: str
    #: Human-facing type, e.g. "local", "memory", "s3", "gdrive".
    kind: str = "abstract"
    #: Advertised free-tier capacity in bytes; 0 means unknown/unmetered.
    capacity: int = 0

    @abc.abstractmethod
    def put(self, key: str, blob: bytes) -> None:
        """Store ``blob`` under ``key`` (idempotent: overwriting is fine)."""

    @abc.abstractmethod
    def get(self, key: str) -> bytes:
        """Return the blob at ``key`` or raise :class:`BlobNotFound`."""

    @abc.abstractmethod
    def delete(self, key: str) -> None:
        """Remove ``key``. Deleting a missing key is not an error."""

    @abc.abstractmethod
    def exists(self, key: str) -> bool:
        ...

    @abc.abstractmethod
    def list_keys(self) -> Iterator[str]:
        ...

    @abc.abstractmethod
    def used_bytes(self) -> int:
        """Total bytes currently stored here."""

    def free_bytes(self) -> int:
        """Best-effort remaining capacity; large sentinel if unmetered."""
        if not self.capacity:
            return 1 << 62
        return max(0, self.capacity - self.used_bytes())

    def health_check(self) -> bool:
        """Cheap round-trip probe used by ``starling fsck``/placement."""
        probe = "__starling_health__"
        try:
            self.put(probe, b"ok")
            ok = self.get(probe) == b"ok"
            self.delete(probe)
            return ok
        except Exception:
            return False

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        cap = "unmetered" if not self.capacity else f"{self.capacity} B"
        return f"<{type(self).__name__} id={self.id!r} kind={self.kind} cap={cap}>"
