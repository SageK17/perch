"""
Delta compression: store a near-duplicate chunk as its *difference* from a
similar one already in the vault.

Exact-match dedup only catches chunks that are byte-identical. But backups,
document versions, and edited files are full of chunks that are *almost* the
same -- one paragraph changed, a few bytes different. This module stores such a
chunk as a small patch against a similar "base" chunk, so you pay only for what
actually changed.

Two pieces:

  * ``sketch`` -- a handful of similarity features for a chunk. Two similar
    chunks share features with high probability (bottom-k of rolling-window
    hashes -- a min-hash sketch), so we can *find* a good base without comparing
    every pair. Shift-robust: an insertion in the middle barely changes it.
  * ``make_delta`` / ``apply_delta`` -- the patch itself, using zlib primed with
    the base chunk as its preset dictionary. Shared runs between target and base
    become cheap back-references; if the target ~ base, the patch is tiny. Pure
    standard library.

Correctness: a delta needs the *exact* base bytes to decode, and Starling can
always reconstruct the base (it's a normal, hash-verified chunk that is pinned
in place while any delta depends on it). Bases are never themselves deltas, so
there are no chains -- decoding a delta is always exactly one hop.
"""

from __future__ import annotations

import hashlib
import zlib
from typing import List

_SHINGLE = 16          # window size whose hashes form the sketch
_FEATURES = 4          # bottom-k features kept per chunk


def sketch(data: bytes, shingle: int = _SHINGLE, features: int = _FEATURES) -> List[str]:
    """Return up to ``features`` similarity features (hex strings) for ``data``."""
    if len(data) <= shingle:
        return [hashlib.blake2b(data, digest_size=8).hexdigest()]

    base = 1_000_003
    mask = (1 << 64) - 1
    top = pow(base, shingle - 1, 1 << 64)

    h = 0
    for i in range(shingle):
        h = (h * base + data[i]) & mask

    mins: List[int] = [h]
    for i in range(shingle, len(data)):
        h = ((h - data[i - shingle] * top) * base + data[i]) & mask
        if h in mins:
            continue
        if len(mins) < features:
            mins.append(h)
            mins.sort()
        elif h < mins[-1]:
            mins[-1] = h
            mins.sort()
    return [format(v, "016x") for v in mins]


_ANCHOR = 16   # match granularity; shared runs shorter than this stay literal
_COPY, _LIT = 0, 1


def _write_varint(buf: bytearray, n: int) -> None:
    while True:
        b = n & 0x7F
        n >>= 7
        buf.append(b | (0x80 if n else 0))
        if not n:
            return


def _read_varint(data: bytes, i: int):
    shift = val = 0
    while True:
        b = data[i]
        i += 1
        val |= (b & 0x7F) << shift
        if not (b & 0x80):
            return val, i
        shift += 7


def make_delta(base: bytes, target: bytes) -> bytes:
    """Encode ``target`` as copies from ``base`` plus literals; tiny when similar.

    A greedy copy/literal diff (rsync/bsdiff-style), unbounded by any window, so
    it handles chunks of any size. Anchors are exact 16-byte windows of the base,
    so there are no false matches; the op stream is then zlib-compressed.
    """
    index = {}
    for i in range(len(base) - _ANCHOR + 1):
        index.setdefault(bytes(base[i : i + _ANCHOR]), i)

    ops = bytearray()
    literal = bytearray()
    i, n = 0, len(target)

    def flush_literal():
        if literal:
            ops.append(_LIT)
            _write_varint(ops, len(literal))
            ops.extend(literal)
            literal.clear()

    while i < n:
        pos = index.get(bytes(target[i : i + _ANCHOR])) if i + _ANCHOR <= n else None
        if pos is None:
            literal.append(target[i])
            i += 1
            continue
        length = _ANCHOR
        while pos + length < len(base) and i + length < n and base[pos + length] == target[i + length]:
            length += 1
        flush_literal()
        ops.append(_COPY)
        _write_varint(ops, pos)
        _write_varint(ops, length)
        i += length
    flush_literal()
    return zlib.compress(bytes(ops), 6)


def apply_delta(base: bytes, patch: bytes) -> bytes:
    """Reconstruct the exact target from ``base`` and a patch from :func:`make_delta`."""
    data = zlib.decompress(patch)
    out = bytearray()
    i, n = 0, len(data)
    while i < n:
        tag = data[i]
        i += 1
        if tag == _COPY:
            off, i = _read_varint(data, i)
            length, i = _read_varint(data, i)
            out += base[off : off + length]
        else:
            length, i = _read_varint(data, i)
            out += data[i : i + length]
            i += length
    return bytes(out)
