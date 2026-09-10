"""Thin blob storage over a local directory (`MEDIA_ROOT`, the Docker `blobstore`
volume) — REBUILD_SPEC §3.1 ("accessed through a thin storage interface so it could
be swapped for S3/MinIO later").

Only what the app needs: `exists`, `save`, `read`. Paths are relative, `/`-separated,
and confined to the storage root.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings


class BlobStorage:
    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else Path(settings.MEDIA_ROOT)

    def _full(self, path: str) -> Path:
        root = self.root.resolve()
        full = (root / path).resolve()
        if root != full and root not in full.parents:
            raise ValueError(f"path escapes the storage root: {path!r}")
        return full

    def exists(self, path: str) -> bool:
        return self._full(path).is_file()

    def save(self, path: str, data: bytes) -> str:
        full = self._full(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(data)
        return path

    def read(self, path: str) -> bytes:
        return self._full(path).read_bytes()


def get_blob_storage() -> BlobStorage:
    """Fresh instance bound to the current `settings.MEDIA_ROOT` (so tests can
    `override_settings`)."""
    return BlobStorage()
