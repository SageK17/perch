"""
Client-side cryptography for Starling.

Everything a provider ever receives is ciphertext. The master key is derived
from a passphrase with scrypt and never leaves this machine. From it we derive
two independent sub-keys via HKDF:

  * an *encryption* key used with AES-256-GCM (authenticated encryption), and
  * a *naming* key used to compute opaque, per-chunk storage keys so that a
    provider can't tell which of your chunks are related, nor recognise a chunk
    it has seen in someone else's vault.

If the third-party ``cryptography`` package is available we use AES-256-GCM.
If it isn't, we fall back to a pure-standard-library authenticated stream
cipher (HMAC-SHA256 keystream in counter mode, encrypt-then-MAC). The wire
format records which was used so a vault stays readable either way.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import struct
from dataclasses import dataclass

# AES-256-GCM if we can get it; otherwise a stdlib-only fallback (see below).
def _load_aesgcm():
    """Return the AESGCM class, or None if it can't load.

    We catch BaseException, not just Exception: a present-but-broken install
    (missing native bindings) can raise a Rust pyo3 PanicException, which is a
    BaseException and also prints a backtrace straight to file descriptor 2. We
    redirect fd 2 to null around the probe so a broken optional dependency
    degrades silently to the fallback rather than spraying the terminal.
    """
    devnull = os.open(os.devnull, os.O_WRONLY)
    saved = os.dup(2)
    try:
        os.dup2(devnull, 2)
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore

        AESGCM(b"\x00" * 32)  # force the native backend to load now, or fail now
        return AESGCM
    except BaseException:  # pragma: no cover - only where the lib is absent/broken
        return None
    finally:
        os.dup2(saved, 2)
        os.close(saved)
        os.close(devnull)


AESGCM = _load_aesgcm()
_HAVE_AESGCM = AESGCM is not None

# One-byte tag stored with each blob so we can decrypt regardless of which
# primitive produced it.
_ALG_AESGCM = 0x01
_ALG_HMAC_CTR = 0x02

_MAGIC = b"STRLNG1"


def _hkdf(master: bytes, info: bytes, length: int = 32) -> bytes:
    """HKDF-SHA256 expand (extract step folded in with a fixed empty salt)."""
    prk = hmac.new(b"\x00" * 32, master, hashlib.sha256).digest()
    out, block, counter = b"", b"", 1
    while len(out) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        out += block
        counter += 1
    return out[:length]


def derive_master_key(passphrase: str, salt: bytes) -> bytes:
    """Turn a human passphrase into a 32-byte master key with scrypt.

    scrypt is memory-hard, which makes brute-forcing the passphrase expensive
    even for someone who has scraped every ciphertext chunk from the providers.
    """
    n, r, p = 2**15, 8, 1
    # OpenSSL caps scrypt memory at 32 MiB by default, which these parameters
    # sit right on top of; raise the ceiling so the KDF isn't rejected.
    maxmem = 256 * n * r + (1 << 20)
    return hashlib.scrypt(
        passphrase.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        maxmem=maxmem,
        dklen=32,
    )


@dataclass
class KeyRing:
    """Holds the master key and the sub-keys derived from it."""

    master: bytes

    def __post_init__(self) -> None:
        if len(self.master) != 32:
            raise ValueError("master key must be 32 bytes")
        self._enc = _hkdf(self.master, b"starling:chunk-encryption", 32)
        self._name = _hkdf(self.master, b"starling:storage-naming", 32)

    # -- naming ---------------------------------------------------------------
    def storage_key(self, content_hash: bytes, shard: int = 0) -> str:
        """Opaque, deterministic key under which a chunk/shard is stored.

        Deterministic so the same chunk always lands at the same key (enabling
        dedup and idempotent re-uploads), keyed so providers learn nothing.
        """
        mac = hmac.new(
            self._name, content_hash + struct.pack(">I", shard), hashlib.sha256
        ).digest()
        return mac.hex()

    # -- content addressing ---------------------------------------------------
    @staticmethod
    def content_hash(data: bytes) -> bytes:
        return hashlib.sha256(data).digest()

    # -- authenticated encryption --------------------------------------------
    def encrypt(self, plaintext: bytes) -> bytes:
        """Encrypt-and-authenticate a blob. Output is self-describing."""
        nonce = os.urandom(12)
        if _HAVE_AESGCM:
            ct = AESGCM(self._enc).encrypt(nonce, plaintext, _MAGIC)
            alg = _ALG_AESGCM
        else:
            ct = _hmac_ctr_seal(self._enc, nonce, plaintext, _MAGIC)
            alg = _ALG_HMAC_CTR
        return bytes([alg]) + nonce + ct

    def decrypt(self, blob: bytes) -> bytes:
        alg, nonce, ct = blob[0], blob[1:13], blob[13:]
        if alg == _ALG_AESGCM:
            if not _HAVE_AESGCM:
                raise RuntimeError(
                    "blob needs AES-GCM but the 'cryptography' package is missing"
                )
            return AESGCM(self._enc).decrypt(nonce, ct, _MAGIC)
        if alg == _ALG_HMAC_CTR:
            return _hmac_ctr_open(self._enc, nonce, ct, _MAGIC)
        raise ValueError(f"unknown cipher algorithm byte {alg:#x}")


# --------------------------------------------------------------------------- #
# Pure-stdlib fallback: HMAC-SHA256 keystream (CTR) with encrypt-then-MAC.
# Not AES, but a sound construction if HMAC-SHA256 behaves as a PRF, which is
# the standard assumption. Only used when 'cryptography' is unavailable.
# --------------------------------------------------------------------------- #
def _keystream(key: bytes, nonce: bytes, nbytes: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < nbytes:
        out += hmac.new(key, nonce + struct.pack(">Q", counter), hashlib.sha256).digest()
        counter += 1
    return bytes(out[:nbytes])


def _xor(a: bytes, b: bytes) -> bytes:
    """XOR two equal-length byte strings via one big-int op (C-speed)."""
    n = len(a)
    return (int.from_bytes(a, "big") ^ int.from_bytes(b, "big")).to_bytes(n, "big")


def _hmac_ctr_seal(key: bytes, nonce: bytes, plaintext: bytes, aad: bytes) -> bytes:
    enc_key = _hkdf(key, b"ctr-enc", 32)
    mac_key = _hkdf(key, b"ctr-mac", 32)
    ct = _xor(plaintext, _keystream(enc_key, nonce, len(plaintext)))
    tag = hmac.new(mac_key, aad + nonce + ct, hashlib.sha256).digest()
    return ct + tag


def _hmac_ctr_open(key: bytes, nonce: bytes, blob: bytes, aad: bytes) -> bytes:
    enc_key = _hkdf(key, b"ctr-enc", 32)
    mac_key = _hkdf(key, b"ctr-mac", 32)
    ct, tag = blob[:-32], blob[-32:]
    expected = hmac.new(mac_key, aad + nonce + ct, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise ValueError("authentication failed: ciphertext was tampered with")
    return _xor(ct, _keystream(enc_key, nonce, len(ct)))


def using_aes() -> bool:
    """True when real AES-256-GCM is in use (vs the stdlib fallback)."""
    return _HAVE_AESGCM
