"""
Templates for real cloud providers.

Starling ships with two *working* backends (local directory, in-memory) so the
whole system runs end-to-end with zero credentials. To pool real free-tier
accounts you add a backend per provider. The contract is tiny -- five methods
from :class:`~starling.backends.base.Backend` -- so an adapter is usually well
under 100 lines.

Below are two illustrative adapters:

  * ``S3Backend`` -- works against any S3-compatible object store. Several have
    genuinely useful free tiers you can pool: Cloudflare R2 (10 GB), Backblaze
    B2 (10 GB), Storj, Idrive e2, and so on. Requires ``boto3``.
  * ``WebDAVBackend`` -- a sketch for WebDAV shares (many free hosts speak it),
    using only the standard library.

Neither is imported by default and neither is exercised by the test suite (they
need live credentials), so treat them as starting points, not turnkey code.
Register your own in ``starling/backends/registry.py``.
"""

from __future__ import annotations

from typing import Iterator

from .base import Backend, BlobNotFound


class S3Backend(Backend):
    """Any S3-compatible bucket (AWS, Cloudflare R2, Backblaze B2, MinIO...).

    Example free-tier pooling: one R2 bucket + one B2 bucket + one Storj bucket
    each become a provider; Starling stripes erasure-coded shards across them so
    no single provider holds a recoverable copy of anything.
    """

    kind = "s3"

    def __init__(
        self,
        id: str,
        bucket: str,
        *,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        prefix: str = "starling/",
        capacity: int = 0,
    ) -> None:
        try:
            import boto3  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("S3Backend needs 'boto3' (pip install boto3)") from exc
        self.id = id
        self.capacity = capacity
        self._bucket = bucket
        self._prefix = prefix
        self._s3 = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    def _k(self, key: str) -> str:
        return self._prefix + key

    def put(self, key: str, blob: bytes) -> None:  # pragma: no cover
        self._s3.put_object(Bucket=self._bucket, Key=self._k(key), Body=blob)

    def get(self, key: str) -> bytes:  # pragma: no cover
        try:
            obj = self._s3.get_object(Bucket=self._bucket, Key=self._k(key))
            return obj["Body"].read()
        except self._s3.exceptions.NoSuchKey:
            raise BlobNotFound(key) from None

    def delete(self, key: str) -> None:  # pragma: no cover
        self._s3.delete_object(Bucket=self._bucket, Key=self._k(key))

    def exists(self, key: str) -> bool:  # pragma: no cover
        try:
            self._s3.head_object(Bucket=self._bucket, Key=self._k(key))
            return True
        except Exception:
            return False

    def list_keys(self) -> Iterator[str]:  # pragma: no cover
        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=self._prefix):
            for obj in page.get("Contents", []):
                yield obj["Key"][len(self._prefix):]

    def used_bytes(self) -> int:  # pragma: no cover
        total = 0
        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=self._prefix):
            for obj in page.get("Contents", []):
                total += obj["Size"]
        return total


class WebDAVBackend(Backend):
    """Sketch adapter for a WebDAV share (stdlib-only, via urllib).

    Fill in auth to taste. Left deliberately minimal; it exists to show the
    contract really is just five HTTP verbs behind the Backend interface.
    """

    kind = "webdav"

    def __init__(self, id: str, base_url: str, *, auth_header: str | None = None,
                 capacity: int = 0) -> None:
        self.id = id
        self.capacity = capacity
        self._base = base_url.rstrip("/") + "/"
        self._auth = auth_header

    def _req(self, method: str, key: str, data: bytes | None = None):  # pragma: no cover
        import urllib.request

        req = urllib.request.Request(self._base + key, data=data, method=method)
        if self._auth:
            req.add_header("Authorization", self._auth)
        return urllib.request.urlopen(req)

    def put(self, key: str, blob: bytes) -> None:  # pragma: no cover
        self._req("PUT", key, blob).read()

    def get(self, key: str) -> bytes:  # pragma: no cover
        import urllib.error

        try:
            return self._req("GET", key).read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise BlobNotFound(key) from None
            raise

    def delete(self, key: str) -> None:  # pragma: no cover
        import urllib.error

        try:
            self._req("DELETE", key).read()
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise

    def exists(self, key: str) -> bool:  # pragma: no cover
        import urllib.error

        try:
            self._req("HEAD", key).read()
            return True
        except urllib.error.HTTPError:
            return False

    def list_keys(self) -> Iterator[str]:  # pragma: no cover
        raise NotImplementedError("implement via PROPFIND for your server")

    def used_bytes(self) -> int:  # pragma: no cover
        return 0
