"""
A backend backed by a local directory.

In production each provider would be a *different* remote free account. For
development, demos, and tests, pointing several LocalDirBackends at several
folders faithfully models "one blob store per provider" -- the engine treats
them exactly as it would treat real remote drives, so the distribution,
dedup, failure-recovery, and self-heal logic all exercise the same code paths.

Keys are hashes, so we shard them into two-character subdirectories to avoid
piling hundreds of thousands of files into one directory.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from .base import Backend, BlobNotFound


class LocalDirBackend(Backend):
    kind = "local"

    def __init__(self, id: str, root: str, capacity: int = 0) -> None:
        self.id = id
        self.capacity = capacity
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = key.replace("/", "_")
        return self.root / safe[:2] / safe

    def put(self, key: str, blob: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "wb") as fh:
            fh.write(blob)
        os.replace(tmp, path)  # atomic: a reader never sees a half-written blob

    def get(self, key: str) -> bytes:
        try:
            with open(self._path(key), "rb") as fh:
                return fh.read()
        except FileNotFoundError:
            raise BlobNotFound(key) from None

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink()
        except FileNotFoundError:
            pass

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def list_keys(self) -> Iterator[str]:
        for sub in self.root.iterdir():
            if sub.is_dir():
                for f in sub.iterdir():
                    if f.is_file() and not f.name.endswith(".tmp"):
                        yield f.name

    def used_bytes(self) -> int:
        total = 0
        for sub in self.root.iterdir():
            if sub.is_dir():
                for f in sub.iterdir():
                    if f.is_file():
                        total += f.stat().st_size
        return total
