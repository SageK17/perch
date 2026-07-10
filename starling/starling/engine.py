"""
The Vault: the high-level engine that turns a pile of free accounts into one
big, encrypted, deduplicated, redundant drive.

Write path (``put``): a file is split into content-defined chunks; each unique
chunk is compressed, encrypted, then either replicated or erasure-coded across
distinct providers chosen by weighted rendezvous hashing. Chunks already stored
(by content hash) are skipped -- that's deduplication. The manifest records
where every piece landed.

Read path (``get``): for each chunk we pull one replica (trying providers in
turn) or enough erasure shards to reconstruct, decrypt, decompress, and verify
the plaintext hash. A provider being down or a shard being corrupt is survivable
as long as the policy's redundancy budget isn't exhausted.

Maintenance: ``rm`` reference-counts and garbage-collects chunks; ``fsck`` finds
under-replicated or missing pieces and heals them onto healthy providers;
``sync`` mirrors the encrypted manifest to the providers for disaster recovery.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from . import compression, reedsolomon
from .backends import Backend, BlobNotFound, build_backend
from .crypto import KeyRing, derive_master_key
from .manifest import MANIFEST_BACKUP_HASH, Manifest
from .placement import NotEnoughProviders, Policy, choose_providers

CONFIG_NAME = "config.json"
MANIFEST_NAME = "manifest.enc"
CONFIG_VERSION = 1


class VaultError(RuntimeError):
    pass


@dataclass
class PutResult:
    path: str
    size: int
    chunks: int
    new_chunks: int
    dedup_bytes: int


class Vault:
    def __init__(self, vault_dir: str, config: dict, keyring: KeyRing) -> None:
        self.dir = Path(vault_dir)
        self.config = config
        self.keyring = keyring
        self.policy = Policy.from_dict(config.get("policy", {}))
        self.backends: Dict[str, Backend] = {
            spec["id"]: build_backend(spec) for spec in config.get("providers", [])
        }
        mpath = self.dir / MANIFEST_NAME
        self.manifest = Manifest.load(str(mpath), keyring) if mpath.exists() else Manifest()
        self._healthy: Optional[set] = None

    # ------------------------------------------------------------------ setup
    @classmethod
    def create(
        cls,
        vault_dir: str,
        passphrase: str,
        policy: Optional[Policy] = None,
        providers: Optional[List[dict]] = None,
    ) -> "Vault":
        vault_dir = str(vault_dir)
        os.makedirs(vault_dir, exist_ok=True)
        cfg_path = os.path.join(vault_dir, CONFIG_NAME)
        if os.path.exists(cfg_path):
            raise VaultError(f"a vault already exists at {vault_dir}")
        salt = os.urandom(16)
        config = {
            "version": CONFIG_VERSION,
            "salt": salt.hex(),
            "policy": (policy or Policy()).to_dict(),
            "providers": providers or [],
            "created": time.time(),
        }
        keyring = KeyRing(derive_master_key(passphrase, salt))
        with open(cfg_path, "w") as fh:
            json.dump(config, fh, indent=2)
        vault = cls(vault_dir, config, keyring)
        vault._save_manifest()
        return vault

    @classmethod
    def open(cls, vault_dir: str, passphrase: str) -> "Vault":
        cfg_path = os.path.join(vault_dir, CONFIG_NAME)
        if not os.path.exists(cfg_path):
            raise VaultError(f"no vault at {vault_dir} (run `starling init` first)")
        with open(cfg_path) as fh:
            config = json.load(fh)
        keyring = KeyRing(derive_master_key(passphrase, bytes.fromhex(config["salt"])))
        # Fail fast on a wrong passphrase (manifest won't authenticate) instead
        # of constructing a vault that emits garbage later.
        mpath = Path(vault_dir) / MANIFEST_NAME
        if mpath.exists():
            try:
                Manifest.load(str(mpath), keyring)
            except Exception as exc:
                raise VaultError("could not open vault (wrong passphrase?)") from exc
        return cls(vault_dir, config, keyring)

    def _save_config(self) -> None:
        with open(self.dir / CONFIG_NAME, "w") as fh:
            json.dump(self.config, fh, indent=2)

    def _save_manifest(self) -> None:
        self.manifest.save(str(self.dir / MANIFEST_NAME), self.keyring)

    def add_provider(self, spec: dict) -> None:
        if any(p["id"] == spec["id"] for p in self.config["providers"]):
            raise VaultError(f"provider id {spec['id']!r} already exists")
        self.backends[spec["id"]] = build_backend(spec)  # validates the spec
        self.config["providers"].append(spec)
        self._save_config()
        self._healthy = None

    def set_policy(self, policy: Policy) -> None:
        self.policy = policy
        self.config["policy"] = policy.to_dict()
        self._save_config()

    # --------------------------------------------------------------- health
    def _healthy_ids(self, refresh: bool = False) -> set:
        if self._healthy is None or refresh:
            self._healthy = {b.id for b in self.backends.values() if b.health_check()}
        return self._healthy

    # --------------------------------------------------------- chunk storage
    def _store_chunk(self, plaintext: bytes) -> str:
        """Store one chunk (dedup-aware) and return its content-hash hex."""
        ph = hashlib.sha256(plaintext).digest()
        ph_hex = ph.hex()
        if self.manifest.has_chunk(ph_hex):
            self.manifest.incref(ph_hex)
            return ph_hex

        payload, tag, dict_id = self._compress_best(plaintext)
        blob = self.keyring.encrypt(payload)

        backends = list(self.backends.values())
        healthy = self._healthy_ids()
        chosen = choose_providers(self.policy, backends, ph, healthy=healthy)

        record: dict = {
            "size": len(plaintext),
            "c": tag,
            "mode": self.policy.mode,
            "refcount": 1,
        }
        if dict_id:
            record["dict"] = dict_id
        if self.policy.mode == "replicate":
            skey = self.keyring.storage_key(ph, 0)
            for pid in chosen:
                self.backends[pid].put(skey, blob)
            record["replicas"] = [[pid, skey] for pid in chosen]
            record["stored"] = len(blob) * len(chosen)
        else:  # erasure
            k, m = self.policy.k, self.policy.m
            shards = reedsolomon.encode(blob, k, m)
            shard_recs = []
            for i, (pid, shard) in enumerate(zip(chosen, shards)):
                skey = self.keyring.storage_key(ph, i)
                self.backends[pid].put(skey, shard)
                shard_recs.append([pid, skey, hashlib.sha256(shard).hexdigest()])
            record["erasure"] = {"k": k, "m": m, "enc_len": len(blob), "shards": shard_recs}
            record["stored"] = sum(len(s) for s in shards)

        self.manifest.put_chunk(ph_hex, record)
        return ph_hex

    def _read_chunk(self, ph_hex: str) -> bytes:
        """Fetch, reconstruct, decrypt, decompress and verify one chunk."""
        rec = self.manifest.get_chunk(ph_hex)
        if rec is None:
            raise VaultError(f"chunk {ph_hex[:12]} missing from manifest")

        if rec["mode"] == "replicate":
            blob = None
            for pid, skey in rec["replicas"]:
                b = self.backends.get(pid)
                if b is None:
                    continue
                try:
                    blob = b.get(skey)
                    break
                except (BlobNotFound, Exception):
                    continue
            if blob is None:
                raise VaultError(f"all replicas of chunk {ph_hex[:12]} unreachable")
        else:
            er = rec["erasure"]
            k, m = er["k"], er["m"]
            slots: List[Optional[bytes]] = [None] * (k + m)
            have = 0
            for i, (pid, skey, sh_hash) in enumerate(er["shards"]):
                if have >= k:
                    break
                b = self.backends.get(pid)
                if b is None:
                    continue
                try:
                    shard = b.get(skey)
                except Exception:
                    continue
                if hashlib.sha256(shard).hexdigest() != sh_hash:
                    continue  # corrupt shard -> treat as an erasure
                slots[i] = shard
                have += 1
            if have < k:
                raise VaultError(
                    f"chunk {ph_hex[:12]}: only {have}/{k} good shards, cannot reconstruct"
                )
            blob = reedsolomon.decode(slots, k, m, er["enc_len"])

        payload = self.keyring.decrypt(blob)
        plaintext = self._decompress_payload(payload, rec)
        if hashlib.sha256(plaintext).hexdigest() != ph_hex:
            raise VaultError(f"integrity check failed for chunk {ph_hex[:12]}")
        return plaintext

    def _delete_chunk_blobs(self, rec: dict) -> None:
        if rec["mode"] == "replicate":
            for pid, skey in rec["replicas"]:
                if pid in self.backends:
                    self.backends[pid].delete(skey)
        else:
            for pid, skey, _ in rec["erasure"]["shards"]:
                if pid in self.backends:
                    self.backends[pid].delete(skey)

    # ----------------------------------------------------------- compression
    def _compress_best(self, plaintext: bytes):
        """Pick the smallest codec for this chunk; returns (payload, tag, dict_id)."""
        zdict = None
        if self.manifest.active_dict:
            zdict = self.manifest.dictionaries.get(self.manifest.active_dict)
        payload, tag = compression.best(plaintext, zdict=zdict)
        return payload, tag, (self.manifest.active_dict if tag == "zdict" else None)

    def _decompress_payload(self, payload: bytes, rec: dict) -> bytes:
        if "c" in rec:
            zdict = None
            if rec.get("dict"):
                zdict = self.manifest.dictionaries.get(rec["dict"])
                if zdict is None:
                    raise VaultError(f"missing dictionary {rec['dict']} for a chunk")
            return compression.decompress(payload, rec["c"], zdict=zdict)
        # legacy records used a boolean 'compressed' flag (zlib or raw)
        import zlib as _zlib
        return _zlib.decompress(payload) if rec.get("compressed") else payload

    def train_dictionary(self, samples, max_size: int = compression.MAX_DICT) -> dict:
        """Learn a shared dictionary; new writes (and any recompress) use it."""
        d = compression.build_dictionary(samples, max_size=max_size)
        if not d:
            raise VaultError("no sample data to train a dictionary from")
        did = hashlib.sha256(d).hexdigest()[:16]
        self.manifest.dictionaries[did] = d
        self.manifest.active_dict = did
        self._save_manifest()
        return {"id": did, "size": len(d)}

    def sample_chunk_plaintexts(self, limit: int = 400) -> List[bytes]:
        out: List[bytes] = []
        for ph_hex in list(self.manifest.chunks)[:limit]:
            try:
                out.append(self._read_chunk(ph_hex))
            except VaultError:
                pass
        return out

    def _recompress_chunk(self, ph_hex: str, rec: dict) -> None:
        """Re-encode an existing chunk with the current best codec, in place."""
        plaintext = self._read_chunk(ph_hex)
        payload, tag, dict_id = self._compress_best(plaintext)
        blob = self.keyring.encrypt(payload)
        if rec["mode"] == "replicate":
            for pid, skey in rec["replicas"]:
                if pid in self.backends:
                    self.backends[pid].put(skey, blob)
            rec["stored"] = len(blob) * len(rec["replicas"])
        else:
            er = rec["erasure"]
            k, m = er["k"], er["m"]
            shards = reedsolomon.encode(blob, k, m)
            new = []
            for i, (pid, skey, _h) in enumerate(er["shards"]):
                if pid in self.backends:
                    self.backends[pid].put(skey, shards[i])
                new.append([pid, skey, hashlib.sha256(shards[i]).hexdigest()])
            er["shards"] = new
            er["enc_len"] = len(blob)
            rec["stored"] = sum(len(s) for s in shards)
        rec["c"] = tag
        if dict_id:
            rec["dict"] = dict_id
        else:
            rec.pop("dict", None)

    def recompress_all(self) -> dict:
        """Re-encode every stored chunk with the current best codec/dictionary."""
        before = self.manifest.stored_bytes()
        n = 0
        for ph_hex in list(self.manifest.chunks):
            self._recompress_chunk(ph_hex, self.manifest.chunks[ph_hex])
            n += 1
        self._save_manifest()
        return {"chunks": n, "before": before, "after": self.manifest.stored_bytes()}

    # ----------------------------------------------------------------- files
    def put_bytes(self, data: bytes, vault_path: str) -> PutResult:
        from .chunker import chunk_bytes

        if not self.backends:
            raise VaultError("no providers configured; add some with `starling provider add`")
        vault_path = _norm(vault_path)
        # Releasing an overwritten file's old chunks keeps refcounts honest.
        old = self.manifest.get_file(vault_path)
        chunk_hexes: List[str] = []
        new_chunks = dedup_bytes = 0
        for chunk in chunk_bytes(data):
            existed = self.manifest.has_chunk(hashlib.sha256(chunk.data).hexdigest())
            ph_hex = self._store_chunk(chunk.data)
            chunk_hexes.append(ph_hex)
            if existed:
                dedup_bytes += len(chunk.data)
            else:
                new_chunks += 1
        self.manifest.set_file(
            vault_path,
            {
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "chunks": chunk_hexes,
                "mtime": time.time(),
            },
        )
        if old:
            self._release_chunks(old["chunks"])
        self._save_manifest()
        return PutResult(vault_path, len(data), len(chunk_hexes), new_chunks, dedup_bytes)

    def put(self, local_path: str, vault_path: Optional[str] = None) -> PutResult:
        with open(local_path, "rb") as fh:
            data = fh.read()
        if vault_path is None:
            vault_path = os.path.basename(local_path)
        return self.put_bytes(data, vault_path)

    def get_bytes(self, vault_path: str) -> bytes:
        vault_path = _norm(vault_path)
        f = self.manifest.get_file(vault_path)
        if f is None:
            raise VaultError(f"no such file in vault: {vault_path}")
        out = b"".join(self._read_chunk(ph) for ph in f["chunks"])
        if hashlib.sha256(out).hexdigest() != f["sha256"]:
            raise VaultError(f"reassembled {vault_path} does not match stored hash")
        return out

    def get(self, vault_path: str, out_path: str) -> int:
        data = self.get_bytes(vault_path)
        with open(out_path, "wb") as fh:
            fh.write(data)
        return len(data)

    def _release_chunks(self, chunk_hexes: List[str]) -> None:
        for ph_hex in chunk_hexes:
            if self.manifest.decref(ph_hex) <= 0:
                rec = self.manifest.get_chunk(ph_hex)
                if rec:
                    self._delete_chunk_blobs(rec)
                    self.manifest.drop_chunk(ph_hex)

    def rm(self, vault_path: str) -> bool:
        vault_path = _norm(vault_path)
        f = self.manifest.remove_file(vault_path)
        if f is None:
            return False
        self._release_chunks(f["chunks"])
        self._save_manifest()
        return True

    def ls(self, prefix: str = "") -> List[dict]:
        prefix = prefix.lstrip("/")
        return [
            {"path": p, "size": f["size"], "chunks": len(f["chunks"]), "mtime": f["mtime"]}
            for p, f in self.manifest.iter_files(prefix)
        ]

    # ------------------------------------------------------------------ stats
    def stats(self) -> dict:
        logical = self.manifest.logical_bytes()
        unique = self.manifest.unique_chunk_bytes()
        stored = self.manifest.stored_bytes()
        providers = []
        pooled_cap = 0
        for b in self.backends.values():
            cap = b.capacity
            pooled_cap += cap
            providers.append(
                {
                    "id": b.id,
                    "kind": b.kind,
                    "capacity": cap,
                    "used": b.used_bytes(),
                    "healthy": b.id in (self._healthy or set()) if self._healthy else None,
                }
            )
        dedup_ratio = (logical / unique) if unique else 1.0
        # Usable pooled capacity after paying the redundancy tax.
        usable_cap = pooled_cap / self.policy.overhead() if pooled_cap else 0
        return {
            "policy": self.policy.describe(),
            "files": len(self.manifest.files),
            "chunks": len(self.manifest.chunks),
            "logical_bytes": logical,
            "unique_bytes": unique,
            "stored_bytes": stored,
            "dedup_ratio": dedup_ratio,
            "space_amplification": (stored / logical) if logical else 0.0,
            "pooled_capacity": pooled_cap,
            "usable_capacity": int(usable_cap),
            "providers": providers,
        }

    # ------------------------------------------------------------------- fsck
    def fsck(self, repair: bool = False, deep: bool = False) -> dict:
        """Check redundancy (and optionally integrity), healing if asked."""
        healthy = self._healthy_ids(refresh=True)
        report = {
            "checked": 0,
            "healthy": 0,
            "degraded": 0,
            "lost": 0,
            "repaired": 0,
            "issues": [],
        }
        for ph_hex, rec in list(self.manifest.chunks.items()):
            report["checked"] += 1
            present, total, locs = self._chunk_presence(rec, deep)
            need = rec["erasure"]["k"] if rec["mode"] == "erasure" else 1
            if present >= total:
                report["healthy"] += 1
                continue
            if present < need:
                report["lost"] += 1
                report["issues"].append(
                    {"chunk": ph_hex[:12], "state": "lost", "present": present, "of": total}
                )
                continue
            report["degraded"] += 1
            report["issues"].append(
                {"chunk": ph_hex[:12], "state": "degraded", "present": present, "of": total}
            )
            if repair and self._repair_chunk(ph_hex, rec, healthy):
                report["repaired"] += 1
        if repair and report["repaired"]:
            self._save_manifest()
        return report

    def _chunk_presence(self, rec: dict, deep: bool):
        """Return (present, total, per-location-ok list)."""
        if rec["mode"] == "replicate":
            locs = rec["replicas"]
            oks = [self._loc_ok(pid, skey, None, deep) for pid, skey in locs]
        else:
            locs = rec["erasure"]["shards"]
            oks = [self._loc_ok(pid, skey, sh, deep) for pid, skey, sh in locs]
        return sum(oks), len(locs), oks

    def _loc_ok(self, pid: str, skey: str, shard_hash: Optional[str], deep: bool) -> bool:
        b = self.backends.get(pid)
        if b is None:
            return False
        try:
            if deep or shard_hash is not None:
                data = b.get(skey)
                if shard_hash is not None and hashlib.sha256(data).hexdigest() != shard_hash:
                    return False
                return True
            return b.exists(skey)
        except Exception:
            return False

    def _repair_chunk(self, ph_hex: str, rec: dict, healthy: set) -> bool:
        """Rebuild missing copies/shards of a recoverable chunk onto new providers."""
        ph = bytes.fromhex(ph_hex)
        try:
            if rec["mode"] == "replicate":
                blob = None
                for pid, skey in rec["replicas"]:
                    b = self.backends.get(pid)
                    if b and b.exists(skey):
                        blob = b.get(skey)
                        break
                if blob is None:
                    return False
                live = {pid for pid, skey in rec["replicas"]
                        if pid in self.backends and self.backends[pid].exists(skey)}
                want = self.policy.replicas - len(live)
                if want <= 0:
                    return False
                skey = self.keyring.storage_key(ph, 0)
                extra = choose_providers(
                    Policy(mode="replicate", replicas=want),
                    list(self.backends.values()), ph, healthy=healthy,
                    exclude=set(pid for pid, _ in rec["replicas"]),
                )
                for pid in extra:
                    self.backends[pid].put(skey, blob)
                rec["replicas"] = [[p, s] for p, s in rec["replicas"] if p in live] + \
                                  [[pid, skey] for pid in extra]
                rec["stored"] = len(blob) * len(rec["replicas"])
                return True
            else:
                blob = self._read_chunk_ciphertext(rec)
                if blob is None:
                    return False
                er = rec["erasure"]
                k, m = er["k"], er["m"]
                shards = reedsolomon.encode(blob, k, m)
                used = {pid for pid, _, _ in er["shards"]}
                new_shards = []
                for i, (pid, skey, sh) in enumerate(er["shards"]):
                    b = self.backends.get(pid)
                    if b and b.exists(skey):
                        new_shards.append([pid, skey, sh])
                        continue
                    repl = choose_providers(
                        Policy(mode="replicate", replicas=1),
                        list(self.backends.values()), ph, healthy=healthy,
                        exclude=used,
                    )[0]
                    used.add(repl)
                    skey_i = self.keyring.storage_key(ph, i)
                    self.backends[repl].put(skey_i, shards[i])
                    new_shards.append([repl, skey_i, hashlib.sha256(shards[i]).hexdigest()])
                er["shards"] = new_shards
                return True
        except (NotEnoughProviders, VaultError):
            return False

    def _read_chunk_ciphertext(self, rec: dict) -> Optional[bytes]:
        """Reconstruct the encrypted blob (not plaintext) for erasure repair."""
        er = rec["erasure"]
        k, m = er["k"], er["m"]
        slots: List[Optional[bytes]] = [None] * (k + m)
        have = 0
        for i, (pid, skey, sh) in enumerate(er["shards"]):
            b = self.backends.get(pid)
            if b is None:
                continue
            try:
                shard = b.get(skey)
            except Exception:
                continue
            if hashlib.sha256(shard).hexdigest() != sh:
                continue
            slots[i] = shard
            have += 1
        if have < k:
            return None
        return reedsolomon.decode(slots, k, m, er["enc_len"])

    # ------------------------------------------------------------------- sync
    def sync_push(self) -> int:
        """Mirror the encrypted manifest to every provider for recovery."""
        blob = self.manifest.serialize(self.keyring)
        skey = self.keyring.storage_key(hashlib.sha256(MANIFEST_BACKUP_HASH).digest(), 0)
        n = 0
        for b in self.backends.values():
            try:
                b.put(skey, blob)
                n += 1
            except Exception:
                pass
        return n

    def sync_pull(self) -> bool:
        """Recover the manifest from any provider that has a backup copy."""
        skey = self.keyring.storage_key(hashlib.sha256(MANIFEST_BACKUP_HASH).digest(), 0)
        for b in self.backends.values():
            try:
                blob = b.get(skey)
            except Exception:
                continue
            self.manifest = Manifest.deserialize(blob, self.keyring)
            self._save_manifest()
            return True
        return False


def _norm(path: str) -> str:
    return path.strip().lstrip("/")
