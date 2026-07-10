"""
The manifest: Starling's index and single source of truth.

It records, for every logical file, the ordered list of chunks that make it up;
and for every chunk, exactly where its copies (or erasure shards) physically
live. Because content-addressed chunks are shared between files, the manifest
is also the reference counter that drives garbage collection.

It is small relative to your data (kilobytes per GB), so we keep the working
copy on the local disk for speed, and can also back up an encrypted copy to the
providers themselves -- meaning your passphrase plus the providers are enough to
recover everything, even if this machine is lost.

On disk the manifest is always encrypted: serialised to JSON, compressed, then
sealed with the vault key. A provider (or anyone who steals the file) sees only
ciphertext.
"""

from __future__ import annotations

import json
import zlib
from typing import Dict, Iterator, List, Optional, Tuple

from .crypto import KeyRing

MANIFEST_VERSION = 1

# Well-known, keyed name under which the encrypted manifest is mirrored to
# providers (so `starling sync` / disaster recovery can find it).
MANIFEST_BACKUP_HASH = b"starling::manifest-backup::v1"


class Manifest:
    def __init__(self) -> None:
        # path -> {"size": int, "sha256": hex, "chunks": [ph_hex, ...], "mtime": float}
        self.files: Dict[str, dict] = {}
        # ph_hex -> chunk record (see engine for the exact shape written)
        self.chunks: Dict[str, dict] = {}

    # -- files ----------------------------------------------------------------
    def set_file(self, path: str, record: dict) -> None:
        self.files[path] = record

    def get_file(self, path: str) -> Optional[dict]:
        return self.files.get(path)

    def remove_file(self, path: str) -> Optional[dict]:
        return self.files.pop(path, None)

    def iter_files(self, prefix: str = "") -> Iterator[Tuple[str, dict]]:
        for path in sorted(self.files):
            if path.startswith(prefix):
                yield path, self.files[path]

    # -- chunks ---------------------------------------------------------------
    def has_chunk(self, ph_hex: str) -> bool:
        return ph_hex in self.chunks

    def get_chunk(self, ph_hex: str) -> Optional[dict]:
        return self.chunks.get(ph_hex)

    def put_chunk(self, ph_hex: str, record: dict) -> None:
        self.chunks[ph_hex] = record

    def incref(self, ph_hex: str) -> None:
        self.chunks[ph_hex]["refcount"] = self.chunks[ph_hex].get("refcount", 0) + 1

    def decref(self, ph_hex: str) -> int:
        rec = self.chunks.get(ph_hex)
        if not rec:
            return 0
        rec["refcount"] = rec.get("refcount", 1) - 1
        return rec["refcount"]

    def drop_chunk(self, ph_hex: str) -> Optional[dict]:
        return self.chunks.pop(ph_hex, None)

    # -- stats ----------------------------------------------------------------
    def logical_bytes(self) -> int:
        """Sum of file sizes as the user sees them (dedup counted many times)."""
        return sum(f["size"] for f in self.files.values())

    def unique_chunk_bytes(self) -> int:
        """Sum of distinct chunk plaintext sizes (what dedup actually keeps)."""
        return sum(c["size"] for c in self.chunks.values())

    def stored_bytes(self) -> int:
        """Physical ciphertext bytes across all providers (incl. redundancy)."""
        total = 0
        for c in self.chunks.values():
            total += c.get("stored", 0)
        return total

    # -- serialisation --------------------------------------------------------
    def _to_obj(self) -> dict:
        return {"version": MANIFEST_VERSION, "files": self.files, "chunks": self.chunks}

    @classmethod
    def _from_obj(cls, obj: dict) -> "Manifest":
        man = cls()
        man.files = obj.get("files", {})
        man.chunks = obj.get("chunks", {})
        return man

    def serialize(self, keyring: KeyRing) -> bytes:
        raw = json.dumps(self._to_obj(), separators=(",", ":")).encode("utf-8")
        return keyring.encrypt(zlib.compress(raw, 9))

    @classmethod
    def deserialize(cls, blob: bytes, keyring: KeyRing) -> "Manifest":
        raw = zlib.decompress(keyring.decrypt(blob))
        return cls._from_obj(json.loads(raw))

    def save(self, path: str, keyring: KeyRing) -> None:
        import os

        blob = self.serialize(keyring)
        tmp = path + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(blob)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str, keyring: KeyRing) -> "Manifest":
        with open(path, "rb") as fh:
            return cls.deserialize(fh.read(), keyring)
