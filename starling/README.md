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

# 2. Pool your free accounts. (Local folders here stand in for real clouds;
#    see docs/BACKENDS.md to wire up Google Drive / Dropbox / S3 / R2 / B2.)
python3 -m starling provider add --id gdrive  --root ~/mnt/gdrive  --capacity 15GB
python3 -m starling provider add --id dropbox --root ~/mnt/dropbox --capacity 2GB
python3 -m starling provider add --id r2      --root ~/mnt/r2      --capacity 10GB
# ...add as many as you like

# 3. Use it like a drive.
python3 -m starling put ~/Videos/trip.mp4 videos/trip.mp4
python3 -m starling ls
python3 -m starling get videos/trip.mp4 ./trip.mp4
python3 -m starling df                 # pooled capacity, dedup + redundancy stats

# 4. Durability.
python3 -m starling fsck --repair      # verify and self-heal redundancy
python3 -m starling sync push          # back the encrypted index up to providers
python3 -m starling dashboard -o status.html
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
  backends/        provider SPI + local/memory + cloud templates
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
provider outages, self-heal, garbage collection, and manifest recovery.

## Status & honesty

This is a working prototype with a real, tested storage engine. The two
included backends (local directory, in-memory) run with zero credentials so the
whole system is exercisable end-to-end. Real cloud adapters (S3-compatible,
WebDAV) are provided as documented templates in
[`backends/cloud_template.py`](starling/backends/cloud_template.py) — the
provider contract is five methods, so adding one is small. Performance is
pure-Python and fine for personal use (tens of MB/s with AES available); it is
not tuned for terabyte workloads.

## License

MIT — see [LICENSE.txt](LICENSE.txt).
