import hashlib
import logging
import json
import os
from datetime import datetime
from typing import Optional, Tuple

import requests

from app.core.config import settings


logger = logging.getLogger("crawler")


_CACHE_FILE = os.path.join(settings.SOURCES_DIR, ".crawl_cache.json")


def _ensure_dirs() -> None:
    os.makedirs(settings.SOURCES_DIR, exist_ok=True)


def _load_cache() -> dict:
    if not os.path.exists(_CACHE_FILE):
        return {}
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    tmp = _CACHE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _CACHE_FILE)


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _date_stamp() -> str:
    # YYMMDD to match existing naming convention
    return datetime.now().strftime("%y%m%d")


def download_if_changed(
    url: str,
    *,
    filename_prefix: str = "auction_data_",
    file_ext: str = "csv",
    date_override: Optional[str] = None,
    timeout: Tuple[float, float] = (3.0, 15.0),
    return_bytes_on_no_change: bool = False,
) -> dict:
    """
    Download URL only if server/content changed.
    Saves into `settings.SOURCES_DIR` using pattern `{prefix}{YYMMDD}.{ext}`.

    Returns a dict with keys: {"changed": bool, "status": int, "path": Optional[str]}.
    """
    _ensure_dirs()
    cache = _load_cache()
    entry = cache.get(url, {})

    headers = {
        "User-Agent": f"{settings.APP_NAME}/{settings.APP_VERSION}",
    }
    if etag := entry.get("etag"):
        headers["If-None-Match"] = etag
    if last_mod := entry.get("last_modified"):
        headers["If-Modified-Since"] = last_mod

    try:
        logger.info("Fetching: %s", url)
        resp = requests.get(url, headers=headers, timeout=timeout)
    except Exception as exc:
        logger.error("Request failed: %s", exc)
        return {"changed": False, "status": 0, "path": None}

    if resp.status_code == 304:
        if not return_bytes_on_no_change:
            return {"changed": False, "status": 304, "path": None}
        # Re-fetch without validators to obtain content bytes
        try:
            logger.info("Re-fetching without validators to obtain content bytes")
            resp2 = requests.get(url, timeout=timeout)
            if resp2.status_code != 200:
                return {"changed": False, "status": resp2.status_code, "path": None}
            resp = resp2
        except Exception as exc:
            logger.error("Refetch failed: %s", exc)
            return {"changed": False, "status": 0, "path": None}

    if resp.status_code != 200:
        logger.error("Unexpected status: %s %s", resp.status_code, getattr(resp, "reason", ""))
        return {"changed": False, "status": resp.status_code, "path": None}

    content = resp.content
    content_hash = _hash_bytes(content)
    if entry.get("hash") == content_hash:
        # No byte-level change
        if not return_bytes_on_no_change:
            return {"changed": False, "status": 200, "path": None}
        date_part = date_override or _date_stamp()
        filename = f"{filename_prefix}{date_part}.{file_ext}"
        return {
            "changed": False,
            "status": 200,
            "path": None,
            "content": content,
            "filename": filename,
        }

    # Build destination filename
    date_part = date_override or _date_stamp()
    filename = f"{filename_prefix}{date_part}.{file_ext}"
    dest_path = os.path.join(settings.SOURCES_DIR, filename)

    abs_dest = os.path.abspath(dest_path)
    with open(abs_dest, "wb") as f:
        f.write(content)

    # Update cache with new validators/hash
    cache[url] = {
        "etag": resp.headers.get("ETag"),
        "last_modified": resp.headers.get("Last-Modified"),
        "hash": content_hash,
        "saved_as": filename,
        "saved_at": datetime.now().isoformat(),
    }
    _save_cache(cache)

    # Log only when something actually changed and was saved
    ext_lower = (file_ext or "").lower()
    if ext_lower == "csv":
        logger.info("New CSV saved: %s (size=%d bytes)", abs_dest, len(content))
    else:
        logger.info("New file saved: %s (size=%d bytes)", abs_dest, len(content))

    result: dict = {"changed": True, "status": 200, "path": abs_dest}
    return result
