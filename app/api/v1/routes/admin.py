from typing import Optional

from fastapi import APIRouter, HTTPException, Header

from app.core.config import settings
from app.crawler.downloader import download_if_changed
from app.services.csv_service import list_available_dates
from app.utils.bizdate import next_business_day, previous_source_candidates_for_mapped
from app.repositories.file_repo import resolve_csv_filepath

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
        # Decide the original/source date we intend to fetch/save for
        src_date = date
        if not src_date:
            from datetime import datetime as _dt
            src_date = _dt.now().strftime("%y%m%d")

        # Target Firestore doc id is next business day of the source date
        target_date = next_business_day(src_date)

        # Perform download/check (always), so we can decide overwrite based on change
        result = download_if_changed(
            settings.CRAWL_URL,
            file_ext=ext,
            filename_prefix=prefix,
            date_override=src_date,
            return_bytes_on_no_change=True,
        )
        # If Firestore is enabled, upload when changed, or when doc doesn't exist yet
        if settings.FIRESTORE_ENABLED and firestore_repo is not None and (result.get("path") or result.get("content")):
            try:
                # Determine whether target already exists
                try:
                    exists = firestore_repo.get_csv(target_date)  # type: ignore[attr-defined]
                except Exception:
                    exists = None
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
                    filename = result.get("filename") or f"{prefix}{src_date}.{ext}"

                should_upload = bool(result.get("changed")) or (exists is None) or force
                if should_upload and content and filename:
                    firestore_repo.save_csv(target_date, filename, content)  # type: ignore[attr-defined]
                    result["uploaded_to_firestore"] = True
                    result["firestore_doc_id"] = target_date
                else:
                    result["uploaded_to_firestore"] = False
                    result["firestore_doc_id"] = target_date
            except Exception as fe:
                result["uploaded_to_firestore"] = False
                result["firestore_error"] = str(fe)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"crawl failed: {exc}") from exc


@router.post("/admin/ensure/{date}")
def admin_ensure_date(
    date: str,
    authorization: Optional[str] = Header(default=None),
    x_admin_token: Optional[str] = Header(default=None),
):
    """
    Ensure a specific date's CSV exists in Firestore. If missing, try to upload it.
    Order:
      1) If document exists in Firestore -> return exists=true
      2) If local file exists in `sources` -> upload to Firestore
      3) Else attempt to download from CRAWL_URL with date override -> upload
    """
    token = _extract_bearer_token(authorization) or x_admin_token
    if not settings.ADMIN_TOKEN or token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not settings.FIRESTORE_ENABLED or firestore_repo is None:
        raise HTTPException(status_code=400, detail="Firestore is not enabled/configured")

    try:
        # Treat the path parameter as the source/original date
        src_date = date
        target_date = next_business_day(src_date)

        # 1) Check Firestore existence for target date first
        try:
            exists = firestore_repo.get_csv(target_date)  # type: ignore[attr-defined]
        except Exception:
            exists = None
        if exists is not None:
            return {
                "date": target_date,
                "exists_before": True,
                "uploaded_to_firestore": False,
                "source": None,
            }

        # 2) Try local file from sources using source date
        filename = f"auction_data_{src_date}.csv"
        path = resolve_csv_filepath(filename)
        last_error = None
        if path:
            try:
                with open(path, "rb") as f:
                    content = f.read()
                firestore_repo.save_csv(target_date, filename, content)  # type: ignore[attr-defined]
                return {
                    "date": target_date,
                    "exists_before": False,
                    "uploaded_to_firestore": True,
                    "source": "local",
                }
            except Exception as fe:
                # Fall through to downloader attempt with error context
                last_error = f"local_upload_failed: {fe}"

        # 3) Attempt download using configured CRAWL_URL with src_date override
        if not settings.CRAWL_URL:
            raise HTTPException(status_code=400, detail="CRAWL_URL not configured")
        result = download_if_changed(
            settings.CRAWL_URL,
            file_ext="csv",
            filename_prefix="auction_data_",
            date_override=src_date,
            return_bytes_on_no_change=True,
        )
        content = None
        filename = result.get("filename") or filename
        if result.get("path"):
            import os
            p = result["path"]
            filename = os.path.basename(p) or filename
            try:
                with open(p, "rb") as f:
                    content = f.read()
            except Exception as fe:
                # Could not read the downloaded file path; rely on 'content' if present
                content = result.get("content")
                last_error = f"read_download_path_failed: {fe}"
        else:
            content = result.get("content")

        if not content:
            raise HTTPException(
                status_code=404,
                detail=(
                    "CSV not found locally or via download"
                    + (f" ({last_error})" if last_error else "")
                ),
            )

        try:
            firestore_repo.save_csv(target_date, filename or f"auction_data_{src_date}.csv", content)  # type: ignore[attr-defined]
            return {
                "date": target_date,
                "exists_before": False,
                "uploaded_to_firestore": True,
                "source": "download",
            }
        except Exception as fe:
            raise HTTPException(status_code=500, detail=f"firestore_upload_failed: {fe}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"ensure failed: {exc}") from exc
