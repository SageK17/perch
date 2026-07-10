"""
Content-defined chunking (a FastCDC-style gear-hash splitter).

Why not just cut every N bytes? Because if you insert one byte near the start
of a file, every fixed-size block after it shifts and none of them dedup any
more. Content-defined chunking places boundaries based on the *data* rolling
through a hash window, so an edit only disturbs the one or two chunks around
it -- everything else keeps its old boundaries and dedups against what's
already stored.

The gear table + normalised-chunking masks below follow the FastCDC paper
(Xia et al., 2016). ``normalization`` sharpens the chunk-size distribution so
we get fewer tiny and fewer giant chunks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

# A fixed, pseudo-random 256-entry gear table. Generated once from a SHA-256
# stream so it's deterministic across machines and versions (changing it would
# break dedup against already-stored data).
def _build_gear() -> list:
    import hashlib

    table, seed = [], b"starling-gear-v1"
    while len(table) < 256:
        seed = hashlib.sha256(seed).digest()
        for i in range(0, len(seed), 8):
            if len(table) >= 256:
                break
            table.append(int.from_bytes(seed[i : i + 8], "big"))
    return table


_GEAR = _build_gear()

MIN_CHUNK = 2 * 1024
AVG_CHUNK = 16 * 1024
MAX_CHUNK = 64 * 1024

# The rolling fingerprint is a fixed-width 64-bit register. In C it wraps for
# free; in Python we must mask it every step, or `fp << 1` grows without bound
# into a multi-thousand-bit bignum and chunking becomes O(n^2).
_FP_MASK = (1 << 64) - 1

# A boundary occurs when (fp & mask) == 0, so the expected chunk size is about
# 2**popcount(mask) bytes. For a ~16 KB (2**14) average we want ~14 one-bits.
# Normalised chunking uses a stricter mask before the average size (more bits ->
# cuts less -> avoids tiny chunks) and a laxer one after it (fewer bits -> cuts
# more -> avoids giant chunks).
_MASK_S = 0x5959_5907_0000_0000  # 15 one-bits: harder to satisfy -> avoid tiny chunks
_MASK_L = 0x5959_4903_0000_0000  # 13 one-bits: easier to satisfy -> avoid giant chunks


@dataclass(frozen=True)
class Chunk:
    offset: int
    data: bytes


def _cut_point(data: bytes, start: int, end: int) -> int:
    """Return the length of the next chunk in ``data[start:end]``."""
    n = end - start
    if n <= MIN_CHUNK:
        return n
    gear = _GEAR
    fp = 0
    i = MIN_CHUNK
    normal = start + min(AVG_CHUNK, n)
    limit = start + min(MAX_CHUNK, n)
    pos = start + i
    # Region 1: below the average size, use the strict mask.
    while pos < normal:
        fp = ((fp << 1) + gear[data[pos]]) & _FP_MASK
        if not (fp & _MASK_S):
            return pos - start + 1
        pos += 1
    # Region 2: above the average size, use the lax mask.
    while pos < limit:
        fp = ((fp << 1) + gear[data[pos]]) & _FP_MASK
        if not (fp & _MASK_L):
            return pos - start + 1
        pos += 1
    return limit - start


def chunk_bytes(data: bytes) -> Iterator[Chunk]:
    """Split an in-memory blob into content-defined chunks."""
    n = len(data)
    offset = 0
    while offset < n:
        length = _cut_point(data, offset, n)
        yield Chunk(offset, data[offset : offset + length])
        offset += length


def chunk_stream(fh, read_size: int = 1 << 20) -> Iterator[Chunk]:
    """Split a file-like object without holding the whole file in memory."""
    buf = b""
    base = 0
    while True:
        block = fh.read(read_size)
        if not block:
            break
        buf += block
        # Emit every full chunk we can while keeping a MAX_CHUNK tail, so a
        # boundary is never decided on a partially-read window.
        while len(buf) >= MAX_CHUNK:
            length = _cut_point(buf, 0, len(buf))
            yield Chunk(base, buf[:length])
            base += length
            buf = buf[length:]
    while buf:
        length = _cut_point(buf, 0, len(buf))
        yield Chunk(base, buf[:length])
        base += length
        buf = buf[length:]
