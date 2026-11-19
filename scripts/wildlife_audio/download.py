"""Explicitly approved, bounded NPS/Zenodo acquisition through Inventory.put."""

import hashlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from scripts.wildlife_audio.storage import InventoryError

SOURCE_HOSTS = {
    "nps_sound_gallery": {"www.nps.gov"},
    "yellowstone_sound_library": {"www.nps.gov"},
    "pnw_cnet_v5": {"zenodo.org"},
}


def check_url(url, hosts):
    parsed = urllib.parse.urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in hosts
        or parsed.username
        or parsed.password
        or parsed.port not in {None, 443}
        or parsed.fragment
    ):
        raise ValueError("URL is outside the source HTTPS allowlist")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_https(url, hosts, headers=None):
    """Validate every redirect before contacting its destination."""
    opener = urllib.request.build_opener(NoRedirect())
    for _ in range(4):
        check_url(url, hosts)
        try:
            return opener.open(
                urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "WildGuard-dataset-review/1.0",
                        "Accept-Encoding": "identity",
                        **(headers or {}),
                    },
                ),
                timeout=20,
            )
        except urllib.error.HTTPError as exc:
            if exc.code not in {301, 302, 303, 307, 308}:
                raise
            location = exc.headers.get("Location")
            exc.close()
            if not location:
                raise InventoryError("redirect has no location") from exc
            url = urllib.parse.urljoin(url, location)
    raise InventoryError("too many redirects")


@dataclass(frozen=True)
class DownloadSpec:
    source_id: str
    source_recording_id: str
    url: str
    path: str
    expected_bytes: int
    sha256: str | None = None
    md5: str | None = None
    etag: str | None = None

    def validate(self):
        if self.source_id not in SOURCE_HOSTS:
            raise ValueError("source needs a reviewed adapter")
        check_url(self.url, SOURCE_HOSTS[self.source_id])
        if (
            type(self.expected_bytes) is not int
            or not 0 < self.expected_bytes <= 30_000_000_000
        ):
            raise ValueError("positive exact expected bytes required")
        if not self.source_recording_id:
            raise ValueError("source recording ID required")
        for checksum, length in ((self.sha256, 64), (self.md5, 32)):
            if checksum is not None and not re.fullmatch(
                f"[0-9a-f]{{{length}}}", checksum
            ):
                raise ValueError("invalid checksum")


def acquire(spec, inventory, approval, rights, transport=open_https):
    """Require explicit exact-file approval plus a separately evidenced access review.

    Rights here authorize acquisition only. Commercial redistribution still uses
    the exact-asset rights gate after acquisition. Never infer approval from open
    access, a registry license flag, or a personal-use purpose.
    """
    spec.validate()
    binding = {"url": spec.url, "expected_bytes": spec.expected_bytes}
    if approval != {**binding, "approved": True}:
        raise PermissionError("exact URL and byte-count acquisition approval required")
    if not isinstance(rights, dict):
        raise PermissionError("rights review must be an object")
    if (
        rights.get("source_id") != spec.source_id
        or rights.get("source_recording_id") != spec.source_recording_id
        or rights.get("url") != spec.url
        or rights.get("download_permitted") is not True
        or not rights.get("reviewed_by")
        or not rights.get("evidence")
    ):
        raise PermissionError("recording-specific evidenced download review required")
    # Evidence is itself retained and hash-verified under the same byte ledger.
    measured = {r["path"]: r for r in inventory.audit()["assets"]}
    for evidence in rights["evidence"]:
        if not isinstance(evidence, dict):
            raise PermissionError("invalid retained evidence reference")
        row = measured.get(evidence.get("path"))
        if (
            not row
            or row["state"] != "ready"
            or row["sha256"] != evidence.get("sha256")
        ):
            raise PermissionError("rights evidence not verified in inventory")

    def chunks():
        total = 0
        md5 = hashlib.md5(usedforsecurity=False)
        started = time.monotonic()
        headers = {"If-Match": spec.etag} if spec.etag else {}
        with transport(spec.url, SOURCE_HOSTS[spec.source_id], headers) as response:
            if response.status != 200:
                raise InventoryError("expected complete HTTP 200 response")
            if (
                response.headers.get("Content-Encoding", "identity").lower()
                != "identity"
            ):
                raise InventoryError("unexpected content encoding")
            length = response.headers.get("Content-Length")
            if length is not None and int(length) != spec.expected_bytes:
                raise InventoryError("server length differs from approved size")
            if spec.etag and response.headers.get("ETag") != spec.etag:
                raise InventoryError("source ETag changed; review again")
            while True:
                if time.monotonic() - started > 600:
                    raise InventoryError("transfer deadline exceeded")
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                md5.update(chunk)
                yield chunk
        if total != spec.expected_bytes:
            raise InventoryError("incomplete or changed source size")
        if spec.md5 and md5.hexdigest() != spec.md5:
            raise InventoryError("source MD5 mismatch")

    return inventory.put(
        spec.path,
        chunks(),
        spec.expected_bytes,
        {
            "source_id": spec.source_id,
            "source_recording_id": spec.source_recording_id,
            "url": spec.url,
            "rights_review": rights,
            "acquisition_approval": approval,
            "expected_bytes": spec.expected_bytes,
            "publisher_md5": spec.md5,
            "expected_sha256": spec.sha256,
            "etag": spec.etag,
        },
        spec.sha256,
    )
