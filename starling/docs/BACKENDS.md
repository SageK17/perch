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

## Native cloud adapters

For direct API access (no mount), add a backend. Templates are in
[`starling/backends/cloud_template.py`](../starling/backends/cloud_template.py):

- **`S3Backend`** — any S3-compatible store. Several have real free tiers worth
  pooling: Cloudflare R2 (10 GB), Backblaze B2 (10 GB), Storj, iDrive e2, MinIO.
  Needs `boto3`.
- **`WebDAVBackend`** — a stdlib sketch for WebDAV shares.

To enable one, wire it into `build_backend()` in
[`starling/backends/registry.py`](../starling/backends/registry.py):

```python
if kind == "s3":
    from .cloud_template import S3Backend
    return S3Backend(
        bid, spec["bucket"],
        endpoint_url=spec.get("endpoint_url"),
        access_key=os.environ["R2_ACCESS_KEY"],   # keep secrets in env, not config
        secret_key=os.environ["R2_SECRET_KEY"],
        capacity=capacity,
    )
```

Provider specs live in the vault's `config.json`. **Never put credentials
there** — read them from environment variables or a secrets manager inside the
adapter, and keep only non-secret fields (bucket name, endpoint, capacity) in
the spec.

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
