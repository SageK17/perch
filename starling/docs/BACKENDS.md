# Backends: pooling real providers

A **backend** is a dumb blob store. Starling does all the intelligence
(chunking, encryption, dedup, redundancy) on top, so a backend only has to
implement five operations. That's the entire contract:

```python
class Backend:
    id: str            # stable identifier used in the manifest
    kind: str          # "local", "s3", "gdrive", ...
    capacity: int      # advertised free-tier size in bytes (0 = unknown)

    def put(self, key: str, blob: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...          # raise BlobNotFound if absent
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def list_keys(self) -> Iterator[str]: ...
    def used_bytes(self) -> int: ...
```

Everything handed to `put` is already encrypted ciphertext under an opaque key,
so a backend never needs to know — and never learns — anything about your data.

## Built-in, zero-credential backends

| kind | class | use |
| --- | --- | --- |
| `local` | `LocalDirBackend` | a directory (a mounted cloud drive, a NAS share, a spare disk) |
| `memory` | `MemoryBackend` | tests and dry-runs |

The simplest way to pool a real cloud today is to **mount it as a folder** and
point a `local` backend at it:

- Google Drive / OneDrive / Dropbox desktop clients expose a synced folder.
- [`rclone mount`](https://rclone.org/) exposes 70+ providers as a filesystem.
- Any WebDAV/SFTP share can be FUSE-mounted.

```bash
rclone mount gdrive: ~/mnt/gdrive --daemon
rclone mount onedrive: ~/mnt/onedrive --daemon
python3 -m starling provider add --id gdrive   --root ~/mnt/gdrive   --capacity 15GB
python3 -m starling provider add --id onedrive --root ~/mnt/onedrive --capacity 5GB
```

That already gives you pooling + encryption + dedup + erasure coding across real
free accounts, with no code.

## Native S3 adapter (built in, no dependencies)

For direct API access with **no mount and no `boto3`**, Starling ships a real
S3-compatible backend: [`starling/backends/s3.py`](../starling/backends/s3.py).
It implements AWS Signature Version 4 with `hashlib`/`hmac` (the signing is
verified against AWS's published test vector) and talks over `urllib`, so it
works against any S3 API — **Cloudflare R2 (10 GB free), Backblaze B2 (10 GB
free), Storj, iDrive e2, AWS S3, MinIO** — with zero extra installs.

Credentials come from **environment variables**, never the config file. Add a
provider from the CLI:

```bash
export R2_KEY=...           # your Cloudflare R2 access key id
export R2_SECRET=...        # your R2 secret

python3 -m starling provider add \
    --id r2 --kind s3 \
    --bucket my-starling-bucket \
    --endpoint https://<accountid>.r2.cloudflarestorage.com \
    --region auto \
    --access-key-env R2_KEY --secret-key-env R2_SECRET \
    --capacity 10GB
```

Backblaze B2 (its S3 endpoint), Storj, MinIO, etc. are the same call with a
different `--endpoint`. For AWS S3 you can omit `--endpoint` and just pass
`--region`. Pool several and Starling stripes erasure-coded, encrypted shards
across all of them — the data lives on those remote servers, not your device.

The vault's `config.json` stores only non-secret fields (bucket, endpoint,
region, and the *names* of the env vars holding the keys). The keys themselves
are read from the environment at runtime.

### Other adapters / templates

[`starling/backends/cloud_template.py`](../starling/backends/cloud_template.py)
has a `WebDAVBackend` sketch and a `boto3`-based S3 alternative, as starting
points for writing your own.

## Writing your own

1. Subclass `starling.backends.base.Backend`, implement the five methods, raise
   `BlobNotFound` from `get` on a miss.
2. Set `id`, `kind`, and (optionally) `capacity`.
3. Add a branch to `build_backend()` for your `kind`.
4. Sanity-check it: `Backend.health_check()` does a put/get/delete round-trip.

Because the interface is so small, a working adapter is usually well under 100
lines — see `S3Backend` for a complete example.

## How capacity is used

`capacity` feeds two things: the pooled/usable-space figures in `starling df`
and the dashboard, and the weighting in provider selection — chunks are spread
in rough proportion to each provider's free space, so a 20 GB account naturally
takes more than a 2 GB one. It's advisory; Starling won't exceed a provider's
real quota if you set it accurately, but it doesn't enforce the provider's limit
for you.
