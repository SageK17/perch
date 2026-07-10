"""
Measure how much smaller the *data* gets, honestly.

Builds a realistic mix -- many small, similar JSON log files; a compressible
text document; and an already-compressed (random) blob -- then reports the
stored size of the unique chunks under each compression layer:

    raw            after dedup, no compression
    zlib           the old per-chunk DEFLATE
    best (lzma)    Starling's best-of codec, no dictionary
    best + dict    best-of plus a shared vault dictionary

All figures are DATA size at replication factor 1 (redundancy would multiply
every row equally, so it's left out to isolate the compression effect).

    python3 examples/benchmark.py
"""

import hashlib
import json
import os
import random
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from starling import compression  # noqa: E402
from starling.chunker import chunk_bytes  # noqa: E402


def make_corpus():
    rng = random.Random(7)
    words = ("the quick brown fox jumps over a lazy dog river mountain code data "
             "star cloud vault chunk shard parity backup restore").split()
    corpus = {}
    # 80 similar JSON log files (same shape, different values) -- not duplicates
    for i in range(80):
        rec = {
            "ts": 1_700_000_000 + i, "level": rng.choice(["INFO", "WARN", "ERROR"]),
            "service": "starling-api", "region": "us-east-1", "host": "node-07",
            "msg": " ".join(rng.choice(words) for _ in range(10)),
            "user_id": rng.randint(1000, 9999), "latency_ms": rng.randint(1, 500),
            "ok": rng.choice([True, False]),
        }
        corpus[f"logs/{i}.json"] = (json.dumps(rec) + "\n").encode() * 4
    # a compressible prose document
    corpus["docs/book.txt"] = (" ".join(rng.choice(words) for _ in range(30_000))).encode()
    # an already-compressed / random blob (stands in for a JPEG or ZIP)
    corpus["media/photo.jpg"] = os.urandom(500_000)
    return corpus


def main():
    corpus = make_corpus()
    logical = sum(len(v) for v in corpus.values())

    # dedup: keep one copy of each unique chunk
    unique = {}
    for data in corpus.values():
        for c in chunk_bytes(data):
            unique[hashlib.sha256(c.data).hexdigest()] = c.data
    chunks = list(unique.values())
    raw = sum(len(c) for c in chunks)

    zlib_total = sum(len(zlib.compress(c, 6)) for c in chunks)
    best_total = sum(len(compression.best(c)[0]) for c in chunks)
    zdict = compression.build_dictionary(chunks)
    dict_total = sum(len(compression.best(c, zdict=zdict)[0]) for c in chunks)

    winners = {}
    for c in chunks:
        _, tag = compression.best(c, zdict=zdict)
        winners[tag] = winners.get(tag, 0) + 1

    print(f"Logical data (what you have) : {logical:>12,} bytes  "
          f"({len(corpus)} files)")
    print(f"After dedup (unique chunks)  : {raw:>12,} bytes  "
          f"({len(chunks)} chunks)")
    print("-" * 64)
    rows = [
        ("raw (dedup only)", raw),
        ("+ zlib (old)", zlib_total),
        ("+ best-of (lzma)", best_total),
        ("+ best-of & shared dict", dict_total),
    ]
    for label, size in rows:
        vs_logical = logical / size if size else 0
        print(f"{label:<26}: {size:>12,} bytes   {vs_logical:5.2f}x smaller than logical")
    print("-" * 64)
    print(f"best-of vs old zlib          : {zlib_total / best_total:.2f}x smaller")
    print(f"best-of+dict vs old zlib     : {zlib_total / dict_total:.2f}x smaller")
    print(f"per-chunk winners            : {winners}")


if __name__ == "__main__":
    main()
