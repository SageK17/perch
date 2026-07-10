"""
Builds live Backend objects from the plain-dict specs saved in a vault config.

A provider spec looks like::

    {"id": "drive-a", "kind": "local", "root": "/data/a", "capacity": 16106127360}

Only the ``local`` and ``memory`` kinds are wired up here because they run with
no credentials. To enable a real cloud, import its adapter from
``cloud_template`` (or your own module) and add a branch below.
"""

from __future__ import annotations

import os
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
    if kind == "s3":
        from .s3 import S3Backend

        # Secrets live in the environment, never in config.json.
        ak = os.environ.get(spec.get("access_key_env", "AWS_ACCESS_KEY_ID"))
        sk = os.environ.get(spec.get("secret_key_env", "AWS_SECRET_ACCESS_KEY"))
        st = os.environ.get(spec.get("session_token_env", "AWS_SESSION_TOKEN"))
        if not ak or not sk:
            raise ValueError(
                f"s3 provider {bid!r}: set credentials in the env vars named by "
                f"access_key_env/secret_key_env (default AWS_ACCESS_KEY_ID / "
                f"AWS_SECRET_ACCESS_KEY)"
            )
        return S3Backend(
            bid, spec["bucket"],
            access_key=ak, secret_key=sk, session_token=st,
            endpoint_url=spec.get("endpoint_url"),
            region=spec.get("region", "us-east-1"),
            prefix=spec.get("prefix", "starling/"),
            capacity=capacity,
        )

    raise ValueError(
        f"unknown backend kind {kind!r} (known: local, memory, s3)"
    )
