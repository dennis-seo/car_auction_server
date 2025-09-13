from typing import Optional

from fastapi import APIRouter, HTTPException, Header

from app.core.config import settings
from app.crawler.downloader import download_if_changed
from app.services.csv_service import list_available_dates

try:
    from app.repositories import firestore_repo  # type: ignore
except Exception:
    firestore_repo = None  # type: ignore


router = APIRouter()


def _extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


@router.post("/admin/crawl")
def admin_crawl(
    authorization: Optional[str] = Header(default=None),
    x_admin_token: Optional[str] = Header(default=None),
    ext: str = "csv",
    prefix: str = "auction_data_",
    date: Optional[str] = None,
    force: bool = False,
):
    token = _extract_bearer_token(authorization) or x_admin_token
    if not settings.ADMIN_TOKEN or token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not settings.CRAWL_URL:
        raise HTTPException(status_code=400, detail="CRAWL_URL not configured")

    try:
        # If Firestore is enabled, pre-check existence of the target date document
        date_key = date
        if not date_key:
            from datetime import datetime as _dt

            date_key = _dt.now().strftime("%y%m%d")

        if settings.FIRESTORE_ENABLED and firestore_repo is not None and not force:
            try:
                exists = firestore_repo.get_csv(date_key)  # type: ignore[attr-defined]
            except Exception:
                exists = None
            if exists is not None:
                return {
                    "skipped": True,
                    "reason": "already_exists_in_firestore",
                    "date": date_key,
                }

        result = download_if_changed(
            settings.CRAWL_URL,
            file_ext=ext,
            filename_prefix=prefix,
            date_override=date_key,
            return_bytes_on_no_change=True,
        )
        # If Firestore is enabled and a new file was saved, upload it
        if settings.FIRESTORE_ENABLED and firestore_repo is not None and (result.get("path") or result.get("content")):
            try:
                import os
                content = None
                filename = None
                if result.get("path"):
                    path = result["path"]
                    filename = os.path.basename(path)
                    with open(path, "rb") as f:
                        content = f.read()
                else:
                    content = result.get("content")
                    filename = result.get("filename") or f"{prefix}{date_key}.{ext}"
                # Try to parse date from filename
                if filename and not date_key and filename.startswith(prefix) and filename.endswith(f".{ext}"):
                    date_key = filename[len(prefix) : -len(f".{ext}")]
                if not date_key:
                    date_key = filename or date_key
                firestore_repo.save_csv(date_key, filename, content)  # type: ignore[attr-defined]
                result["uploaded_to_firestore"] = True
            except Exception as fe:
                result["uploaded_to_firestore"] = False
                result["firestore_error"] = str(fe)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"crawl failed: {exc}") from exc
