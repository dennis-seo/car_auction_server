import hashlib
import logging
import os
import traceback
from typing import Optional

from fastapi import APIRouter, HTTPException, Header

from app.core.config import settings
from app.crawler.downloader import download_if_changed
from app.utils.bizdate import next_business_day
from app.repositories.file_repo import resolve_csv_filepath


logger = logging.getLogger("admin")


def _hash_content(content: bytes) -> str:
    """SHA256 해시 생성"""
    return hashlib.sha256(content).hexdigest()

try:
    from app.repositories import supabase_repo  # type: ignore
except Exception:
    supabase_repo = None  # type: ignore

try:
    from app.repositories import auction_records_repo  # type: ignore
except Exception:
    auction_records_repo = None  # type: ignore


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

        # Target Supabase row id is next business day of the source date
        target_date = next_business_day(src_date)

        # Perform download/check (always), so we can decide overwrite based on change
        result = download_if_changed(
            settings.CRAWL_URL,
            file_ext=ext,
            filename_prefix=prefix,
            date_override=src_date,
            return_bytes_on_no_change=True,
        )
        # If Supabase is enabled, upload when changed, or when doc doesn't exist yet
        if settings.SUPABASE_ENABLED and supabase_repo is not None and (result.get("path") or result.get("content")):
            try:
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

                # 기존 파일 해시와 새 파일 해시 비교
                existing_hash = None
                new_hash = None
                auction_records_exists = False

                if content:
                    new_hash = _hash_content(content)
                    result["new_file_hash"] = new_hash
                    try:
                        existing_hash = supabase_repo.get_file_hash(target_date)  # type: ignore[attr-defined]
                        result["existing_file_hash"] = existing_hash
                    except Exception:
                        existing_hash = None

                    # auction_records 테이블에도 데이터가 있는지 확인
                    if auction_records_repo is not None:
                        try:
                            auction_records_exists = auction_records_repo.exists(target_date)  # type: ignore[attr-defined]
                            result["auction_records_exists"] = auction_records_exists
                        except Exception:
                            auction_records_exists = False
                            result["auction_records_exists"] = False

                # 해시가 같아도 auction_records에 데이터가 없으면 저장 진행
                hash_changed = (existing_hash is None) or (new_hash != existing_hash)
                needs_auction_records = not auction_records_exists
                result["hash_changed"] = hash_changed
                result["needs_auction_records"] = needs_auction_records

                should_upload = (hash_changed or needs_auction_records or force) and content and filename
                if should_upload:
                    supabase_repo.save_csv(target_date, filename, content)  # type: ignore[attr-defined]
                    result["uploaded_to_supabase"] = True
                    result["supabase_row_id"] = target_date

                    # 새 auction_records 테이블에도 저장
                    if auction_records_repo is not None:
                        try:
                            record_count = auction_records_repo.save_csv(target_date, filename, content)
                            result["uploaded_to_auction_records"] = True
                            result["auction_records_count"] = record_count
                            logger.info(
                                "auction_records 저장 성공: date=%s, records=%d",
                                target_date, record_count
                            )
                        except Exception as ar_err:
                            result["uploaded_to_auction_records"] = False
                            result["auction_records_error"] = str(ar_err)
                            # 상세 로그 출력 (traceback 포함)
                            logger.error(
                                "auction_records 저장 실패: date=%s, filename=%s, "
                                "content_size=%d, error=%s\n%s",
                                target_date,
                                filename,
                                len(content) if content else 0,
                                str(ar_err),
                                traceback.format_exc()
                            )
                else:
                    result["uploaded_to_supabase"] = False
                    result["supabase_row_id"] = target_date
                    if not hash_changed and auction_records_exists:
                        result["skip_reason"] = "hash_unchanged_and_records_exist"
                    elif not content:
                        result["skip_reason"] = "no_content"
                    else:
                        result["skip_reason"] = "unknown"
            except Exception as fe:
                result["uploaded_to_supabase"] = False
                result["supabase_error"] = str(fe)
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
    Ensure a specific date's CSV exists in Supabase. If missing, try to upload it.
    Order:
      1) If document exists in Supabase -> return exists=true
      2) If local file exists in `sources` -> upload to Supabase
      3) Else attempt to download from CRAWL_URL with date override -> upload
    """

    token = _extract_bearer_token(authorization) or x_admin_token
    if not settings.ADMIN_TOKEN or token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not settings.SUPABASE_ENABLED or supabase_repo is None:
        raise HTTPException(status_code=400, detail="Supabase is not enabled/configured")

    try:
        # Treat the path parameter as the source/original date
        src_date = date
        target_date = next_business_day(src_date)

        # 1) Check Supabase existence for target date first
        try:
            exists = supabase_repo.get_csv(target_date)  # type: ignore[attr-defined]
        except Exception:
            exists = None
        if exists is not None:
            return {
                "date": target_date,
                "exists_before": True,
                "uploaded_to_supabase": False,
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
                supabase_repo.save_csv(target_date, filename, content)  # type: ignore[attr-defined]

                result_data = {
                    "date": target_date,
                    "exists_before": False,
                    "uploaded_to_supabase": True,
                    "source": "local",
                }

                # 새 auction_records 테이블에도 저장
                if auction_records_repo is not None:
                    try:
                        record_count = auction_records_repo.save_csv(target_date, filename, content)
                        result_data["uploaded_to_auction_records"] = True
                        result_data["auction_records_count"] = record_count
                        logger.info(
                            "auction_records 저장 성공 (ensure/local): date=%s, records=%d",
                            target_date, record_count
                        )
                    except Exception as ar_err:
                        result_data["uploaded_to_auction_records"] = False
                        result_data["auction_records_error"] = str(ar_err)
                        logger.error(
                            "auction_records 저장 실패 (ensure/local): date=%s, filename=%s, "
                            "content_size=%d, error=%s\n%s",
                            target_date,
                            filename,
                            len(content) if content else 0,
                            str(ar_err),
                            traceback.format_exc()
                        )

                return result_data
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
            final_filename = filename or f"auction_data_{src_date}.csv"
            supabase_repo.save_csv(target_date, final_filename, content)  # type: ignore[attr-defined]

            result_data = {
                "date": target_date,
                "exists_before": False,
                "uploaded_to_supabase": True,
                "source": "download",
            }

            # 새 auction_records 테이블에도 저장
            if auction_records_repo is not None:
                try:
                    record_count = auction_records_repo.save_csv(target_date, final_filename, content)
                    result_data["uploaded_to_auction_records"] = True
                    result_data["auction_records_count"] = record_count
                    logger.info(
                        "auction_records 저장 성공 (ensure/download): date=%s, records=%d",
                        target_date, record_count
                    )
                except Exception as ar_err:
                    result_data["uploaded_to_auction_records"] = False
                    result_data["auction_records_error"] = str(ar_err)
                    logger.error(
                        "auction_records 저장 실패 (ensure/download): date=%s, filename=%s, "
                        "content_size=%d, error=%s\n%s",
                        target_date,
                        final_filename,
                        len(content) if content else 0,
                        str(ar_err),
                        traceback.format_exc()
                    )

            return result_data
        except Exception as fe:
            raise HTTPException(status_code=500, detail=f"supabase_upload_failed: {fe}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"ensure failed: {exc}") from exc
