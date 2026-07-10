# Architecture

Starling is a small stack of independent layers. Each does one job and knows
nothing about the layers above it. Data flows down on write and up on read.

```
        ┌─────────────────────────────────────────────┐
  CLI   │  cli.py  ──  python3 -m starling ...          │
        └───────────────────────┬─────────────────────┘
        ┌───────────────────────▼─────────────────────┐
 Engine │  engine.Vault   put / get / rm / ls / df /   │
        │                 fsck / sync   (+ manifest)   │
        └──┬──────────┬──────────┬──────────┬──────────┘
           │          │          │          │
   chunker.py   crypto.py   placement.py  reedsolomon.py
   (dedup)      (encrypt)   (where?)      (erasure code)
           │          │          │          │
        ┌──▼──────────▼──────────▼──────────▼──────────┐
Backends│  base.Backend   local · memory · s3 · webdav  │
        └───────────────────────────────────────────────┘
                 one dumb blob store per provider
```

## The write path (`put`)

1. **Chunk** (`chunker.py`). The file is split by a FastCDC gear-hash rolling
   window into variable-size chunks (~2 KB–64 KB, ~16 KB average). Boundaries
   depend on content, not offset, so inserting bytes near the start of a file
   re-chunks only the region around the edit — everything else keeps its old
   boundaries and dedups.

2. **Deduplicate** (`engine.py` + `manifest.py`). Each chunk is addressed by
   `SHA-256(plaintext)`. If the manifest already has that hash, we just bump a
   reference count and move on — nothing is re-uploaded.

3. **Compress** (`compression.py`). Each new chunk is run through a *best-of*
   codec: zlib, LZMA, and — if a shared dictionary has been trained — zlib primed
   with that dictionary. The smallest result wins, and a tag in the manifest
   records which codec was used so reads can reverse it. If nothing beats the raw
   bytes (already-compressed or random data), the chunk is stored as-is. A
   shared dictionary is a vault-wide codebook of common blocks, letting many
   small similar files reference shared structure instead of each carrying a
   copy; dictionaries are content-addressed and immutable, so retraining never
   breaks chunks written against an older one. `starling optimize` /
   `dict train --recompress` re-encode existing chunks in place.

4. **Encrypt** (`crypto.py`). The payload is sealed with AES-256-GCM under a key
   derived from your passphrase. Output is `alg-byte ‖ nonce ‖ ciphertext‖tag`.
   Providers only ever receive this.

5. **Place** (`placement.py`). Weighted rendezvous hashing picks the distinct
   providers for this chunk — spread in proportion to free space, deterministic
   per (chunk, provider set), and stable when providers come and go.

6. **Make redundant** (`engine.py` + `reedsolomon.py`).
   - *Replication:* the whole encrypted blob is written to each chosen provider.
   - *Erasure coding:* the blob is split into `k` data + `m` parity shards via
     Reed–Solomon; one shard per provider. Any `k` of the `k+m` rebuild it.

7. **Record** (`manifest.py`). The manifest maps the file to its ordered chunk
   hashes, and each chunk hash to its physical locations (provider id + opaque
   storage key, plus per-shard hashes for erasure). It's saved locally,
   encrypted.

## Delta compression (`optimize --delta`)

Deduplication only removes *identical* chunks. Backups, snapshots, and edited
files are full of chunks that are *nearly* identical — a few bytes changed. A
compaction pass (modelled on `git gc`) squeezes those:

1. **Sketch** every whole chunk (`delta.sketch`) — a min-hash of its 16-byte
   windows. Similar chunks share sketch features, so a similarity index maps
   feature → candidate base without comparing every pair.
2. For each whole chunk, find a similar base and compute a **copy/literal diff**
   (`delta.make_delta`, rsync/bsdiff-style, unbounded by any window). If the diff
   is meaningfully smaller than compressing the chunk standalone, rewrite the
   chunk's stored blob as that patch and record `delta → base` in the manifest.

Correctness is guarded by three invariants:

- **Bases stay whole.** A chunk chosen as a base is never itself turned into a
  diff, so decoding a delta is always exactly one hop (read base, apply patch,
  verify hash). No chains.
- **Bases are pinned.** Making a diff bumps the base's reference count, so
  garbage collection can't drop a base while any diff still needs it — even if
  the file that originally introduced the base is deleted.
- **GC cascades.** Deleting the last file that references a diff frees the diff's
  blobs and releases its hold on the base, which is then collected if nothing
  else needs it.

Because a diff still depends on its base being available, a delta chunk is only
as durable as its base — but the base is a normal chunk with the same redundancy,
so losing providers is survivable up to the policy's tolerance for both.

## The read path (`get`)

For each chunk hash in the file:

- **Replication:** try each recorded replica provider until one returns the blob.
- **Erasure:** fetch shards until `k` valid ones are in hand (each shard is hash-
  checked; a corrupt one is treated as missing), then Reed–Solomon-decode.

Then decrypt → decompress → verify `SHA-256(plaintext)` equals the chunk hash.
Finally the whole file's hash is checked against the manifest. Any mismatch is a
hard error, never silent corruption.

## Naming and privacy

A chunk's storage key on a provider is `HMAC(naming_key, plaintext_hash ‖ shard)`
— deterministic (so re-writes are idempotent and dedup works) but keyed, so a
provider can't tell which of your blobs are related, can't recognize a blob it
has seen elsewhere, and learns nothing from the key. The naming key and the
encryption key are independent HKDF sub-keys of the master key.

## The manifest

The manifest is the single source of truth and the only stateful thing that
must survive. It is:

- **Small** — kilobytes per GB of data.
- **Encrypted at rest** — JSON → zlib → AES-GCM. A stolen `manifest.enc` reveals
  nothing.
- **Recoverable** — `sync push` mirrors the encrypted manifest to every provider
  under a well-known keyed name. After a total loss of your machine,
  `sync pull` + your passphrase rebuilds the index, and then every file is
  readable again. Passphrase + providers = your data.

It also drives **garbage collection**: chunks are reference-counted, so deleting
a file frees only the chunks no surviving file still needs.

## Durability and self-healing

`fsck` walks every chunk and checks that its copies/shards are still present
(`--deep` also re-hashes each stored blob). A chunk is:

- **healthy** — all copies/shards present;
- **degraded** — some missing but still enough to recover (`≥1` replica, or
  `≥k` shards);
- **lost** — not enough to recover.

`fsck --repair` reconstructs degraded chunks: it reads what survives, regenerates
the missing replicas/shards, and writes them to healthy providers not already
holding a copy — restoring full redundancy without re-uploading everything.

## Failure model

| Failure | Outcome |
| --- | --- |
| A provider is temporarily unreachable | Reads fail over to other copies/shards; writes route around it |
| A provider permanently dies / deletes your account | Survivable up to the policy's tolerance (`replicas-1`, or `m`); `fsck --repair` heals |
| Your local machine dies | `sync pull` + passphrase restores the manifest; data is intact on providers |
| A provider is malicious/curious | Sees only opaque-named ciphertext; can't read, correlate, or forge (GCM auth) |
| Wrong passphrase | Vault refuses to open; no garbage output |
| Bit-rot in a stored blob | Detected by per-chunk/per-shard hashing; treated as missing and healed |

## Deliberate limits

- Pure-Python throughput; great for personal use, not tuned for TB-scale.
- The manifest is authoritative and lives with you — keep your passphrase safe
  and run `sync push` periodically.
- Cross-user/global dedup is intentionally *not* done: it would leak which
  chunks you hold. Dedup is within a vault only.
