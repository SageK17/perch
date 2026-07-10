"""
A native S3-compatible backend -- dependency-free (stdlib only).

Works against any S3 API: AWS S3, Cloudflare R2 (10 GB free), Backblaze B2
(10 GB free), Storj, iDrive e2, MinIO. Pool several of them and Starling stripes
encrypted, erasure-coded shards across all of them, so the data lives on remote
servers -- not on your device -- and no single provider holds a recoverable copy.

Authentication is AWS Signature Version 4, implemented here with ``hashlib`` /
``hmac`` so there is no ``boto3`` dependency. Requests go over ``urllib`` (which
honours the environment's HTTPS proxy transparently). Uses path-style addressing
(``endpoint/bucket/key``), which every S3-compatible service supports.

Credentials are passed in at construction; the registry reads them from
environment variables, never from the vault config on disk.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Iterator, List, Optional
from xml.etree import ElementTree as ET

from .base import Backend, BlobNotFound

_TIMEOUT = 60
_RETRIES = 4          # attempts for transient (5xx / network) failures
_EMPTY_HASH = hashlib.sha256(b"").hexdigest()


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def signing_key(secret: str, datestamp: str, region: str, service: str) -> bytes:
    """Derive the SigV4 signing key (exposed for testing against AWS vectors)."""
    k = _sign(("AWS4" + secret).encode("utf-8"), datestamp)
    k = _sign(k, region)
    k = _sign(k, service)
    return _sign(k, "aws4_request")


class S3Backend(Backend):
    kind = "s3"

    def __init__(
        self,
        id: str,
        bucket: str,
        *,
        access_key: str,
        secret_key: str,
        endpoint_url: Optional[str] = None,
        region: str = "us-east-1",
        session_token: Optional[str] = None,
        prefix: str = "starling/",
        capacity: int = 0,
    ) -> None:
        self.id = id
        self.capacity = capacity
        self.bucket = bucket
        self.region = region
        self.prefix = prefix
        self._access = access_key
        self._secret = secret_key
        self._token = session_token
        base = (endpoint_url or f"https://s3.{region}.amazonaws.com").rstrip("/")
        self._base = base
        self._host = urllib.parse.urlsplit(base).netloc

    # -- signing --------------------------------------------------------------
    def _canonical_uri(self, key: str = "") -> str:
        path = self.bucket if not key else f"{self.bucket}/{self.prefix}{key}"
        return "/" + urllib.parse.quote(path, safe="/~")

    @staticmethod
    def _canonical_query(query: Optional[Dict[str, str]]) -> str:
        if not query:
            return ""
        items = sorted(
            (urllib.parse.quote(k, safe="~"), urllib.parse.quote(v, safe="~"))
            for k, v in query.items()
        )
        return "&".join(f"{k}={v}" for k, v in items)

    def _send(self, method: str, key: str = "", query: Optional[Dict[str, str]] = None,
              body: bytes = b"") -> bytes:
        """Sign and send, retrying transient failures (5xx, timeouts) with backoff.

        Each attempt is re-signed with a fresh timestamp so a retry can't be
        rejected for clock skew. 4xx (404, 403, ...) are not retried.
        """
        delay = 0.5
        for attempt in range(_RETRIES):
            try:
                return self._send_once(method, key, query, body)
            except urllib.error.HTTPError as exc:
                if exc.code < 500 or attempt == _RETRIES - 1:
                    raise
            except (urllib.error.URLError, socket.timeout, ConnectionError, TimeoutError):
                if attempt == _RETRIES - 1:
                    raise
            time.sleep(delay)
            delay *= 2
        raise RuntimeError("unreachable")

    def _send_once(self, method: str, key: str = "", query: Optional[Dict[str, str]] = None,
                   body: bytes = b"") -> bytes:
        now = datetime.datetime.now(datetime.timezone.utc)
        amzdate = now.strftime("%Y%m%dT%H%M%SZ")
        datestamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(body).hexdigest() if body else _EMPTY_HASH

        headers = {
            "host": self._host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amzdate,
        }
        if self._token:
            headers["x-amz-security-token"] = self._token
        signed = ";".join(sorted(headers))
        canon_headers = "".join(f"{h}:{headers[h]}\n" for h in sorted(headers))
        canon_req = "\n".join([
            method, self._canonical_uri(key), self._canonical_query(query),
            canon_headers, signed, payload_hash,
        ])
        scope = f"{datestamp}/{self.region}/s3/aws4_request"
        sts = "\n".join([
            "AWS4-HMAC-SHA256", amzdate, scope,
            hashlib.sha256(canon_req.encode("utf-8")).hexdigest(),
        ])
        sig = hmac.new(signing_key(self._secret, datestamp, self.region, "s3"),
                       sts.encode("utf-8"), hashlib.sha256).hexdigest()
        auth = (f"AWS4-HMAC-SHA256 Credential={self._access}/{scope}, "
                f"SignedHeaders={signed}, Signature={sig}")

        qs = self._canonical_query(query)
        url = self._base + self._canonical_uri(key) + (("?" + qs) if qs else "")
        req = urllib.request.Request(
            url, data=(body if method in ("PUT", "POST") else None), method=method
        )
        req.add_header("Authorization", auth)
        for h, v in headers.items():
            if h != "host":  # urllib sets Host from the URL
                req.add_header(h, v)
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.read()

    # -- Backend API ----------------------------------------------------------
    def put(self, key: str, blob: bytes) -> None:
        self._send("PUT", key, body=blob)

    def get(self, key: str) -> bytes:
        try:
            return self._send("GET", key)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise BlobNotFound(key) from None
            raise

    def delete(self, key: str) -> None:
        try:
            self._send("DELETE", key)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise

    def exists(self, key: str) -> bool:
        try:
            self._send("HEAD", key)
            return True
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False
            raise

    def _list(self):
        """Yield (key_without_prefix, size) across all pages."""
        token = None
        while True:
            query = {"list-type": "2", "prefix": self.prefix}
            if token:
                query["continuation-token"] = token
            xml = self._send("GET", "", query=query)
            root = ET.fromstring(xml)
            for el in root:
                tag = el.tag.split("}")[-1]
                if tag == "Contents":
                    key = size = None
                    for child in el:
                        ctag = child.tag.split("}")[-1]
                        if ctag == "Key":
                            key = child.text
                        elif ctag == "Size":
                            size = int(child.text or 0)
                    if key is not None:
                        yield key[len(self.prefix):], size or 0
            truncated = next(
                (e.text for e in root if e.tag.split("}")[-1] == "IsTruncated"), "false"
            )
            token = next(
                (e.text for e in root if e.tag.split("}")[-1] == "NextContinuationToken"),
                None,
            )
            if truncated != "true" or not token:
                break

    def list_keys(self) -> Iterator[str]:
        return (k for k, _ in self._list())

    def used_bytes(self) -> int:
        return sum(size for _, size in self._list())
