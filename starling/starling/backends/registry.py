"""
Builds live Backend objects from the plain-dict specs saved in a vault config.

A provider spec looks like::

    {"id": "drive-a", "kind": "local", "root": "/data/a", "capacity": 16106127360}

Only the ``local`` and ``memory`` kinds are wired up here because they run with
no credentials. To enable a real cloud, import its adapter from
``cloud_template`` (or your own module) and add a branch below.
"""

from __future__ import annotations

from typing import Any, Dict

from .base import Backend
from .local import LocalDirBackend
from .memory import MemoryBackend


def build_backend(spec: Dict[str, Any]) -> Backend:
    kind = spec.get("kind", "local")
    bid = spec["id"]
    capacity = int(spec.get("capacity", 0) or 0)

    if kind == "local":
        return LocalDirBackend(bid, spec["root"], capacity=capacity)
    if kind == "memory":
        return MemoryBackend(bid, capacity=capacity)

    # --- Real clouds: uncomment and supply credentials from env/secrets. ---
    # if kind == "s3":
    #     from .cloud_template import S3Backend
    #     return S3Backend(bid, spec["bucket"], endpoint_url=spec.get("endpoint_url"),
    #                      access_key=..., secret_key=..., capacity=capacity)

    raise ValueError(
        f"unknown backend kind {kind!r} (known: local, memory; "
        "see backends/cloud_template.py to add clouds)"
    )
