"""
Shrinking the actual data.

Dedup already removes whole duplicate chunks; this squeezes what's left. For
each chunk we try several codecs and keep whichever produces the fewest bytes,
recording the winner so we know how to reverse it:

  * ``raw``  -- store as-is (already-compressed / random data; nothing to gain)
  * ``zlib`` -- fast general compression (DEFLATE)
  * ``lzma`` -- xz/LZMA: slower, but typically 15-40% smaller than zlib on text
  * ``zdict``-- zlib primed with a shared vault-wide dictionary, so many small,
                similar files reference common blocks instead of each carrying
                their own copy (this is the "codebook" idea, applied to content)

Whichever wins per chunk is used, so you always get the best available shrink
for that particular data -- and already-compressed media (JPEG/MP4/ZIP) simply
falls through to ``raw`` rather than wasting space.

Honest limit: none of this shrinks truly random or already-compressed bytes.
The wins come from compressible or repetitive data (text, code, logs, docs, and
lots of similar files). That's a law (counting/pigeonhole), not a tuning knob.
"""

from __future__ import annotations

import lzma
import zlib
from collections import Counter
from typing import Iterable, List, Optional, Tuple

MAX_DICT = 32 * 1024      # zlib's history window bounds a useful preset dictionary
_TRAIN_BLOCK = 32
_KEEP_IF_UNDER = 0.98     # keep a compressed form only if it beats raw by >=2%


def _zdict_compress(data: bytes, zdict: bytes, level: int = 6) -> bytes:
    co = zlib.compressobj(level, zlib.DEFLATED, zlib.MAX_WBITS, 8,
                          zlib.Z_DEFAULT_STRATEGY, zdict)
    return co.compress(data) + co.flush()


def _zdict_decompress(blob: bytes, zdict: bytes) -> bytes:
    do = zlib.decompressobj(wbits=zlib.MAX_WBITS, zdict=zdict)
    return do.decompress(blob) + do.flush()


def best(data: bytes, zdict: Optional[bytes] = None) -> Tuple[bytes, str]:
    """Return ``(payload, tag)`` for the smallest codec that beats raw."""
    candidates: List[Tuple[bytes, str]] = [
        (zlib.compress(data, 6), "zlib"),
        (lzma.compress(data, format=lzma.FORMAT_XZ, preset=6), "lzma"),
    ]
    if zdict:
        candidates.append((_zdict_compress(data, zdict), "zdict"))
    payload, tag = min(candidates, key=lambda c: len(c[0]))
    if len(payload) >= len(data) * _KEEP_IF_UNDER:
        return data, "raw"      # not worth it -> store plaintext
    return payload, tag


def decompress(payload: bytes, tag: str, zdict: Optional[bytes] = None) -> bytes:
    if tag == "raw":
        return payload
    if tag == "zlib":
        return zlib.decompress(payload)
    if tag == "lzma":
        return lzma.decompress(payload)
    if tag == "zdict":
        if zdict is None:
            raise ValueError("zdict codec needs its dictionary")
        return _zdict_decompress(payload, zdict)
    raise ValueError(f"unknown compression tag {tag!r}")


def build_dictionary(samples: Iterable[bytes], max_size: int = MAX_DICT,
                     block: int = _TRAIN_BLOCK) -> bytes:
    """Learn a shared dictionary from sample blobs.

    Tally fixed-size blocks across the samples and keep the recurring ones,
    rarest-first so the most common land at the tail (where zlib favours them).
    If nothing recurs, fall back to a representative sample; worst case the
    dictionary just doesn't help -- it never hurts correctness.
    """
    counts: Counter = Counter()
    samples = list(samples)
    for s in samples:
        mv = memoryview(s)
        for i in range(0, len(s) - block + 1, block):
            counts[bytes(mv[i : i + block])] += 1

    recurring = [blk for blk, c in counts.items() if c >= 2]
    recurring.sort(key=lambda b: counts[b])  # most common last

    out = bytearray()
    for blk in recurring:
        out += blk
        if len(out) >= max_size:
            break
    if not out and samples:
        out += max(samples, key=len)[:max_size]
    return bytes(out[-max_size:])
