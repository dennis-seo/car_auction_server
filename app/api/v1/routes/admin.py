from typing import Optional

from fastapi import APIRouter, HTTPException, Header

from app.core.config import settings
from app.crawler.downloader import download_if_changed
from app.services.csv_service import list_available_dates
from app.utils.bizdate import next_business_day, previous_source_candidates_for_mapped
from app.repositories.file_repo import resolve_csv_filepath

try:
    from app.repositories import spanner_repo  # type: ignore
except Exception:
    spanner_repo = None  # type: ignore

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

        # Target Spanner row id is next business day of the source date
        target_date = next_business_day(src_date)

        # Perform download/check (always), so we can decide overwrite based on change
        result = download_if_changed(
            settings.CRAWL_URL,
            file_ext=ext,
            filename_prefix=prefix,
            date_override=src_date,
            return_bytes_on_no_change=True,
        )
        import os
        content = None
        filename = None
        if result.get("path"):
            try:
                path = result["path"]
                filename = os.path.basename(path)
                with open(path, "rb") as f:
                    content = f.read()
            except Exception as fe:
                result["read_error"] = str(fe)
                content = result.get("content")
                filename = filename or result.get("filename") or f"{prefix}{src_date}.{ext}"
        else:
            content = result.get("content")
            filename = result.get("filename") or f"{prefix}{src_date}.{ext}"

        # If Spanner is enabled, upload when changed, or when row doesn't exist yet
        if settings.SPANNER_ENABLED and spanner_repo is not None and content:
            try:
                try:
                    exists = spanner_repo.get_csv(target_date)  # type: ignore[attr-defined]
                except Exception:
                    exists = None
                should_upload_spanner = bool(result.get("changed")) or (exists is None) or force
                if should_upload_spanner and filename:
                    spanner_repo.save_csv(target_date, filename, content)  # type: ignore[attr-defined]
                    result["uploaded_to_spanner"] = True
                else:
                    result["uploaded_to_spanner"] = False
                result["spanner_row_id"] = target_date
            except Exception as fe:
                result["uploaded_to_spanner"] = False
                result["spanner_error"] = str(fe)

        if settings.FIRESTORE_ENABLED and firestore_repo is not None and content:
            try:
                try:
                    exists_fs = firestore_repo.get_csv(target_date)  # type: ignore[attr-defined]
                except Exception:
                    exists_fs = None
                should_upload_fs = bool(result.get("changed")) or (exists_fs is None) or force
                if should_upload_fs and filename:
                    firestore_repo.save_csv(target_date, filename, content)  # type: ignore[attr-defined]
                    result["uploaded_to_firestore"] = True
                else:
                    result["uploaded_to_firestore"] = False
                result["firestore_doc_id"] = target_date
            except Exception as fe:
                result["uploaded_to_firestore"] = False
                result["firestore_error"] = str(fe)
        if settings.SPANNER_ENABLED and spanner_repo is not None and "spanner_row_id" not in result:
            result["spanner_row_id"] = target_date
        if settings.SPANNER_ENABLED and spanner_repo is not None and "uploaded_to_spanner" not in result:
            result["uploaded_to_spanner"] = False
        if settings.FIRESTORE_ENABLED and firestore_repo is not None and "firestore_doc_id" not in result:
            result["firestore_doc_id"] = target_date
        if settings.FIRESTORE_ENABLED and firestore_repo is not None and "uploaded_to_firestore" not in result:
            result["uploaded_to_firestore"] = False
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
    Ensure a specific date's CSV exists in Spanner. If missing, try to upload it.
    Order:
      1) If record exists in Spanner -> return exists=true
      2) If local file exists in `sources` -> upload to Spanner
      3) Else attempt to download from CRAWL_URL with date override -> upload
    """
    token = _extract_bearer_token(authorization) or x_admin_token
    if not settings.ADMIN_TOKEN or token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    spanner_enabled = settings.SPANNER_ENABLED and spanner_repo is not None
    firestore_enabled = settings.FIRESTORE_ENABLED and firestore_repo is not None

    if not (spanner_enabled or firestore_enabled):
        raise HTTPException(status_code=400, detail="No storage backend is enabled")

    try:
        # Treat the path parameter as the source/original date
        src_date = date
        target_date = next_business_day(src_date)

        filename = f"auction_data_{src_date}.csv"

        spanner_exists_before = None
        firestore_exists_before = None
        spanner_needs_upload = False
        firestore_needs_upload = False
        spanner_error = None
        firestore_error = None

        if spanner_enabled:
            try:
                exists = spanner_repo.get_csv(target_date)  # type: ignore[attr-defined]
            except Exception as exc:
                exists = None
                spanner_error = f"check_failed: {exc}"
            spanner_exists_before = exists is not None
            spanner_needs_upload = not spanner_exists_before

        if firestore_enabled:
            try:
                exists_fs = firestore_repo.get_csv(target_date)  # type: ignore[attr-defined]
            except Exception as exc:
                exists_fs = None
                firestore_error = f"check_failed: {exc}"
            firestore_exists_before = exists_fs is not None
            firestore_needs_upload = not firestore_exists_before

        if not spanner_needs_upload and not firestore_needs_upload:
            response = {
                "date": target_date,
                "exists_before": spanner_exists_before if spanner_enabled else firestore_exists_before,
                "uploaded_to_spanner": False,
                "uploaded_to_firestore": False,
                "source": None,
            }
            if spanner_exists_before is not None:
                response["spanner_exists_before"] = spanner_exists_before
            if firestore_exists_before is not None:
                response["firestore_exists_before"] = firestore_exists_before
            if spanner_error:
                response["spanner_error"] = spanner_error
            if firestore_error:
                response["firestore_error"] = firestore_error
            return response

        content = None
        source_used = None
        last_error = None

        if spanner_needs_upload or firestore_needs_upload:
            path = resolve_csv_filepath(filename)
            if path:
                try:
                    with open(path, "rb") as f:
                        content = f.read()
                    source_used = "local"
                except Exception as exc:
                    last_error = f"local_read_failed: {exc}"

        if content is None:
            if not settings.CRAWL_URL:
                raise HTTPException(status_code=400, detail="CRAWL_URL not configured")
            result = download_if_changed(
                settings.CRAWL_URL,
                file_ext="csv",
                filename_prefix="auction_data_",
                date_override=src_date,
                return_bytes_on_no_change=True,
            )
            filename = result.get("filename") or filename
            if result.get("path"):
                import os

                p = result["path"]
                filename = os.path.basename(p) or filename
                try:
                    with open(p, "rb") as f:
                        content = f.read()
                    source_used = "download"
                except Exception as exc:
                    content = result.get("content")
                    last_error = f"read_download_path_failed: {exc}"
            else:
                content = result.get("content")
                if content is not None:
                    source_used = "download"

        if not content:
            raise HTTPException(
                status_code=404,
                detail=(
                    "CSV not found locally or via download"
                    + (f" ({last_error})" if last_error else "")
                ),
            )

        uploaded_to_spanner = False
        uploaded_to_firestore = False

        if spanner_needs_upload and spanner_enabled:
            try:
                spanner_repo.save_csv(target_date, filename or f"auction_data_{src_date}.csv", content)  # type: ignore[attr-defined]
                uploaded_to_spanner = True
                spanner_exists_before = False
            except Exception as exc:
                spanner_error = f"upload_failed: {exc}"

        if firestore_needs_upload and firestore_enabled:
            try:
                firestore_repo.save_csv(target_date, filename or f"auction_data_{src_date}.csv", content)  # type: ignore[attr-defined]
                uploaded_to_firestore = True
                firestore_exists_before = False
            except Exception as exc:
                firestore_error = f"upload_failed: {exc}"

        response = {
            "date": target_date,
            "exists_before": spanner_exists_before if spanner_enabled else firestore_exists_before,
            "uploaded_to_spanner": uploaded_to_spanner if spanner_enabled else False,
            "uploaded_to_firestore": uploaded_to_firestore if firestore_enabled else False,
            "source": source_used,
        }
        if spanner_exists_before is not None:
            response["spanner_exists_before"] = spanner_exists_before
        if firestore_exists_before is not None:
            response["firestore_exists_before"] = firestore_exists_before
        if spanner_error:
            response["spanner_error"] = spanner_error
        if firestore_error:
            response["firestore_error"] = firestore_error
        return response
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"ensure failed: {exc}") from exc
