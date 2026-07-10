"""An in-process backend. Handy for tests and dry-runs; nothing is persisted."""

from __future__ import annotations

from typing import Dict, Iterator

from .base import Backend, BlobNotFound


class MemoryBackend(Backend):
    kind = "memory"

    def __init__(self, id: str, capacity: int = 0) -> None:
        self.id = id
        self.capacity = capacity
        self._store: Dict[str, bytes] = {}

    def put(self, key: str, blob: bytes) -> None:
        self._store[key] = bytes(blob)

    def get(self, key: str) -> bytes:
        try:
            return self._store[key]
        except KeyError:
            raise BlobNotFound(key) from None

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self._store

    def list_keys(self) -> Iterator[str]:
        return iter(list(self._store.keys()))

    def used_bytes(self) -> int:
        return sum(len(v) for v in self._store.values())
