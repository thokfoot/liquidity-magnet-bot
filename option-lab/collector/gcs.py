"""Google Cloud Storage sync (disabled gracefully until bucket+creds exist)."""
from __future__ import annotations

import logging
from pathlib import Path

from . import config as C

log = logging.getLogger(__name__)


def enabled() -> bool:
    return C.GCS_ENABLED


def _client():
    from google.cloud import storage
    return storage.Client()  # uses GOOGLE_APPLICATION_CREDENTIALS


def bucket():
    if not enabled():
        raise RuntimeError("GCS not configured")
    return _client().bucket(C.GCS_BUCKET)


def object_exists(object_name: str) -> bool:
    if not enabled():
        return False
    try:
        return bucket().blob(object_name).exists()
    except Exception as exc:  # noqa: BLE001 - transient GCS errors shouldn't kill the collector
        log.warning("GCS exists check failed for %s: %s", object_name, exc)
        return True  # conservatively skip re-upload on failure


def upload(path: Path, object_name: str, force: bool = False) -> bool:
    if not enabled():
        return False
    if not path.exists():
        return False
    try:
        blob = bucket().blob(object_name)
        if not force and blob.exists() and blob.size and blob.size == path.stat().st_size:
            return True
        blob.upload_from_filename(str(path), timeout=120)
        log.info("GCS up %s (%d B)", object_name, path.stat().st_size)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("GCS upload %s failed: %s", object_name, exc)
        return False


def sync_tree(root: Path) -> int:
    """Upload every file under local `root` that's missing or changed. Returns count."""
    if not enabled():
        return 0
    if not root.exists():
        return 0
    n = 0
    prefix = (C.GCS_PREFIX + "/").lstrip("/")
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        obj = prefix + p.relative_to(root).as_posix()
        if upload(p, obj):
            n += 1
    return n