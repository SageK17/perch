# Starling

**A murmuration of free clouds acting as one giant, encrypted drive.**

Starling pools storage you already have for free — the free tiers of cloud
accounts you own, or any folders/drives lying around — into a *single*
deduplicated, client-side-encrypted, redundant vault. A watchdog of starlings
is a murmuration: hundreds of small birds moving as one. Same idea here —
several small free accounts, coordinated into one big drive.

The "huge storage for free" comes from three honest wins stacked together, not
from cheating any provider:

1. **Pooling** — 6 free accounts of 10–20 GB become one ~90 GB drive.
2. **Deduplication** — identical data is stored once, no matter how many times
   or files it appears in (content-defined chunking, so it even survives edits).
3. **Compression** — every chunk is compressed before it's stored.

On top of that you choose your durability: **N× replication** or
**Reed–Solomon erasure coding** ("RAID across free clouds"), so a provider
disappearing — or deleting your account — doesn't lose your data.

> **What this is not.** Starling never creates throwaway accounts, evades quotas,
> or smuggles data into a service that forbids it. It uses accounts *you own*,
> within their terms. The cleverness is in the storage engine, not in tricking
> anyone. See [docs/SECURITY.md](docs/SECURITY.md).

---

## Why it's interesting

| Property | How |
| --- | --- |
| Providers never see your data | Everything is AES-256-GCM encrypted **before** it leaves your machine |
| Providers can't even correlate your chunks | Blobs are stored under opaque, HMAC-keyed names |
| Survives providers going down | Replication or Reed–Solomon erasure coding, one shard per provider |
| Survives *account loss* | The encrypted manifest is mirrored to the providers; passphrase + providers = full recovery |
| Doesn't store the same bytes twice | Content-defined (FastCDC) chunking + content addressing |
| Shrinks the data | Per-chunk best-of compression (zlib / LZMA) + optional shared vault dictionary + delta compression of near-duplicate chunks |
| Self-healing | `fsck --repair` rebuilds missing copies/shards onto healthy providers |
| No lock-in, no dependencies | Pure Python standard library (uses `cryptography` for AES if present, falls back to a stdlib cipher otherwise) |

## Install

No dependencies required.

```bash
git clone <this repo> && cd starling
python3 -m starling --help            # run in place, or:
pip install -e .                      # installs the `starling` command
```

## Quick start

```bash
export STARLING_PASSPHRASE="something long you'll remember"
export STARLING_VAULT=./myvault

# 1. Create a vault. Erasure code 4+2 = survives any 2 providers dying, 1.5x space.
python3 -m starling init --policy erasure -k 4 -m 2

# 2. Pool your free accounts.
#    Native S3 works with any S3-compatible free tier (R2, B2, Storj, ...):
export R2_KEY=... R2_SECRET=...
python3 -m starling provider add --id r2 --kind s3 --bucket my-bucket \
    --endpoint https://<acct>.r2.cloudflarestorage.com --region auto \
    --access-key-env R2_KEY --secret-key-env R2_SECRET --capacity 10GB
#    Or mount any cloud as a folder with rclone and use a local provider:
python3 -m starling provider add --id gdrive --root ~/mnt/gdrive --capacity 15GB
# ...add as many as you like (see docs/BACKENDS.md)

# 3. Use it like a drive.
python3 -m starling put ~/Videos/trip.mp4 videos/trip.mp4
python3 -m starling ls
python3 -m starling get videos/trip.mp4 ./trip.mp4
python3 -m starling df                 # pooled capacity, dedup + redundancy stats

# 4. Durability.
python3 -m starling fsck --repair      # verify and self-heal redundancy
python3 -m starling sync push          # back the encrypted index up to providers
python3 -m starling dashboard -o status.html

# 5. Shrink the data further.
python3 -m starling dict train ~/samples/   # learn a shared dictionary (or omit path to learn from the vault)
python3 -m starling optimize                # recompress everything with the best codec
python3 -m starling optimize --delta        # also store near-duplicate chunks as diffs (backups/versions)
```

See the whole thing run — pool 8 accounts, kill 2, recover, self-heal:

```bash
bash examples/demo.sh
```

## How it works (30 seconds)

**Writing a file:** split it into content-defined chunks → for each *new* chunk
(dedup skips ones already stored), compress → encrypt → either replicate or
erasure-code it across distinct providers picked by weighted rendezvous hashing.
Record where every piece landed in the manifest.

**Reading it back:** for each chunk, pull one replica (trying providers in turn)
or enough erasure shards to reconstruct → decrypt → decompress → verify the
plaintext hash. A dead provider or a corrupt shard is survivable within your
redundancy budget.

```
file ─▶ chunk ─▶ dedup ─▶ compress ─▶ encrypt ─▶ ┬─ replicate ─▶ provider A,B,C
                                                 └─ or erasure ─▶ shard→A shard→B … parity→F
```

Full details in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Shrinking the data

Beyond deduplication, each new chunk is compressed with a **best-of codec**:
Starling tries zlib and LZMA (and a shared dictionary, if trained) and keeps
whichever is smallest — already-compressed data (JPEG/MP4/ZIP) simply falls
through to raw rather than wasting space.

For **lots of small, similar files** (logs, JSON records, templated documents),
train a **shared dictionary**: one vault-wide codebook of common blocks that
every chunk can reference instead of each carrying its own copy.

For **backups, snapshots, and edited versions**, run **delta compression**:
exact dedup already removes identical chunks, and `optimize --delta` stores the
*near*-duplicate ones (a chunk that changed by a few bytes) as a small diff
against a similar chunk instead of a whole second copy. On five near-identical
1.5 MB snapshots it cuts stored size ~47% beyond dedup — every snapshot still
restores byte-for-byte. It works like `git gc`: a compaction pass, not the write
path. Bases are pinned so garbage collection never drops a chunk a diff needs,
and a diff is never itself a base (one hop to decode, always).

```bash
python3 -m starling dict train ./my-json-records/   # or no path: learn from the vault
python3 -m starling dict show
python3 -m starling optimize                         # recompress existing data
python3 -m starling optimize --delta                 # + delta-compress near-duplicates
python3 examples/benchmark.py                        # honest before/after on a sample corpus
```

Honest limits: compression only shrinks data that has structure. Text, logs,
code, documents, and similar files win; already-compressed media and random
bytes don't (that's the entropy floor, not a tuning knob). Dictionaries are
content-addressed and never mutated, so retraining never breaks old chunks.

## Replication vs. erasure coding

| | Replication `--policy replicate --replicas 3` | Erasure `--policy erasure -k 4 -m 2` |
| --- | --- | --- |
| Survives | 2 lost providers | 2 lost providers |
| Space cost | 3.00× | 1.50× |
| Providers touched per chunk | 3 | 6 |
| Best when | few providers, simplicity | several providers, capacity matters |

With erasure coding, 120 GB of pooled free space holds ~80 GB of data while
tolerating two providers vanishing. That's the "RAID across free clouds" trick.

## Layout

```
starling/
  crypto.py        client-side AES-256-GCM (+ stdlib fallback), key derivation
  chunker.py       FastCDC content-defined chunking (dedup that survives edits)
  reedsolomon.py   GF(256) Reed–Solomon erasure coding
  placement.py     redundancy policy + weighted-rendezvous provider selection
  manifest.py      the encrypted index (files → chunks → locations)
  engine.py        the Vault: put/get/rm/ls/df/fsck/sync
  delta.py         similarity sketch + copy/literal diff for near-duplicates
  backends/        provider SPI + local/memory + native S3 (s3.py) + templates
  dashboard.py     self-contained HTML status page
  cli.py           the command line
tests/             end-to-end tests (run: python3 tests/test_starling.py)
examples/demo.sh   the whole story, start to finish
docs/              ARCHITECTURE, SECURITY, BACKENDS
```

## Tests

```bash
python3 tests/test_starling.py     # no dependencies; pytest also works
```

Covers dedup, authenticated encryption, Reed–Solomon reconstruction, surviving
provider outages, self-heal, garbage collection, manifest recovery, delta
compression, and the native S3 backend (SigV4 + a full engine→S3→HTTP round-trip
against an in-process S3 server).

## Status & honesty

This is a working prototype with a real, tested storage engine. Local-directory
and in-memory backends run with zero credentials so the whole system is
exercisable end-to-end, and a **native S3 backend** ([`backends/s3.py`](starling/backends/s3.py))
talks to any S3-compatible free tier (R2, B2, Storj, AWS, MinIO) with no
dependencies — its SigV4 signing is verified against AWS's published test
vector, and the full engine→S3→HTTP path is covered by tests against an
in-process S3 server. The provider contract is just five methods, so more
adapters are small. Performance is pure-Python and fine for personal use (tens
of MB/s with AES available); it is not tuned for terabyte workloads.

## License

MIT — see [LICENSE.txt](LICENSE.txt).
