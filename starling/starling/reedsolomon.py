"""
Reed-Solomon erasure coding over GF(2**8) -- "RAID across free clouds".

Replication is simple but wasteful: keeping 3 copies costs 3x the space to
survive 2 failures. Erasure coding does far better. With parameters (k, m) we
split each chunk into ``k`` data shards and compute ``m`` parity shards; any
``k`` of the ``k + m`` shards reconstruct the original. Spread one shard per
provider and you survive *any* ``m`` providers vanishing, at only
(k + m) / k space overhead. For example (k=4, m=2) tolerates 2 lost providers
for 1.5x space -- versus 3x for equivalent replication.

The code is a *systematic* Reed-Solomon built from a Vandermonde matrix:

    M = V . (V_top)^-1

where V is a (k+m) x k Vandermonde matrix over distinct field nodes. Because
every square Vandermonde submatrix is invertible, every k-row submatrix of M is
invertible too -- which is exactly the property that guarantees any k shards
suffice to decode. Making the top k x k block the identity means the first k
shards are the raw data (cheap, copy-only reads).

Pure standard library; no numpy. Chunk sizes here are small (tens of KB), so
the straightforward byte loops are plenty fast.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

# --------------------------------------------------------------------------- #
# GF(2**8) arithmetic, primitive polynomial 0x11d, generator 2.
# --------------------------------------------------------------------------- #
_EXP = [0] * 512
_LOG = [0] * 256


def _init_tables() -> None:
    x = 1
    for i in range(255):
        _EXP[i] = x
        _LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        _EXP[i] = _EXP[i - 255]


_init_tables()


def _mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _div(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("GF division by zero")
    if a == 0:
        return 0
    return _EXP[(_LOG[a] - _LOG[b]) % 255]


def _pow(a: int, n: int) -> int:
    if n == 0:
        return 1
    if a == 0:
        return 0
    return _EXP[(_LOG[a] * n) % 255]


@lru_cache(maxsize=256)
def _mul_table(scalar: int) -> bytes:
    """256-entry translate table to multiply a whole shard by ``scalar`` at C speed."""
    if scalar == 0:
        return bytes(256)
    base = _LOG[scalar]
    return bytes(_EXP[base + _LOG[v]] if v else 0 for v in range(256))


# --------------------------------------------------------------------------- #
# Matrices over GF(256).
# --------------------------------------------------------------------------- #
def _mat_mul(a: List[List[int]], b: List[List[int]]) -> List[List[int]]:
    rows, inner, cols = len(a), len(b), len(b[0])
    out = [[0] * cols for _ in range(rows)]
    for i in range(rows):
        for kk in range(inner):
            aik = a[i][kk]
            if aik == 0:
                continue
            brow = b[kk]
            orow = out[i]
            for j in range(cols):
                if brow[j]:
                    orow[j] ^= _mul(aik, brow[j])
    return out


def _mat_invert(src: List[List[int]]) -> List[List[int]]:
    """Gauss-Jordan inverse of a square GF(256) matrix."""
    n = len(src)
    m = [row[:] + [1 if i == j else 0 for j in range(n)] for i, row in enumerate(src)]
    for col in range(n):
        pivot = col
        while pivot < n and m[pivot][col] == 0:
            pivot += 1
        if pivot == n:
            raise ValueError("matrix is singular; cannot invert")
        m[col], m[pivot] = m[pivot], m[col]
        inv = _div(1, m[col][col])
        m[col] = [_mul(v, inv) for v in m[col]]
        for r in range(n):
            if r != col and m[r][col]:
                factor = m[r][col]
                m[r] = [a ^ _mul(factor, b) for a, b in zip(m[r], m[col])]
    return [row[n:] for row in m]


@lru_cache(maxsize=64)
def _encode_matrix(k: int, m: int) -> List[List[int]]:
    total = k + m
    if total > 256:
        raise ValueError("k + m must be <= 256")
    vander = [[_pow(node, j) for j in range(k)] for node in range(total)]
    top_inv = _mat_invert([vander[i][:] for i in range(k)])
    return _mat_mul(vander, top_inv)  # top k rows become the identity


def _apply_row(row: List[int], shards: List[bytes], length: int) -> bytes:
    """Compute sum_j row[j] * shards[j] over GF(256), elementwise across bytes.

    ``bytes.translate`` does the per-byte multiply in C; accumulation is a single
    big-integer XOR. Both replace what would otherwise be per-byte Python loops.
    """
    acc = 0
    for coeff, shard in zip(row, shards):
        if coeff == 0:
            continue
        acc ^= int.from_bytes(shard.translate(_mul_table(coeff)), "big")
    return acc.to_bytes(length, "big")


# --------------------------------------------------------------------------- #
# Public API.
# --------------------------------------------------------------------------- #
def encode(data: bytes, k: int, m: int) -> List[bytes]:
    """Split ``data`` into k data shards + m parity shards (all equal length).

    The original length isn't recoverable from the shards alone, so the caller
    must remember it (Starling stores it in the manifest) and pass it to
    :func:`decode`.
    """
    if k < 1 or m < 0:
        raise ValueError("need k >= 1 and m >= 0")
    shard_len = (len(data) + k - 1) // k or 1
    padded = data + bytes(shard_len * k - len(data))
    data_shards = [padded[i * shard_len : (i + 1) * shard_len] for i in range(k)]
    matrix = _encode_matrix(k, m)
    shards = list(data_shards)  # systematic: first k rows are identity
    for i in range(k, k + m):
        shards.append(_apply_row(matrix[i], data_shards, shard_len))
    return shards


def decode(shards: List[Optional[bytes]], k: int, m: int, orig_len: int) -> bytes:
    """Reconstruct the original bytes from any k present shards.

    ``shards`` has k + m slots; missing shards are ``None``.
    """
    present = [i for i, s in enumerate(shards) if s is not None]
    if len(present) < k:
        raise ValueError(f"need at least {k} shards, have {len(present)}")
    chosen = present[:k]
    # Fast path: all k data shards survived -> just concatenate them.
    if chosen == list(range(k)):
        joined = b"".join(shards[i] for i in range(k))  # type: ignore[misc]
        return joined[:orig_len]
    matrix = _encode_matrix(k, m)
    sub = [matrix[i][:] for i in chosen]
    inv = _mat_invert(sub)
    length = len(shards[chosen[0]])  # type: ignore[arg-type]
    received = [shards[i] for i in chosen]
    data_shards = [_apply_row(inv[j], received, length) for j in range(k)]  # type: ignore[arg-type]
    return b"".join(data_shards)[:orig_len]
