import hashlib
import logging
import os
import secrets
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


def _validate_admin_token(token: Optional[str]) -> None:
    """
    Admin 토큰 검증 (타이밍 공격 방지)

    Args:
        token: 클라이언트에서 전달받은 토큰

    Raises:
        HTTPException: 토큰이 없거나 유효하지 않은 경우
    """
    if not settings.ADMIN_TOKEN:
        raise HTTPException(status_code=500, detail="ADMIN_TOKEN not configured")
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    # secrets.compare_digest로 타이밍 공격 방지
    if not secrets.compare_digest(token, settings.ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _save_to_auction_records(
    target_date: str,
    filename: str,
    content: bytes,
    result_data: dict,
    source: str = ""
) -> None:
    """
    auction_records 테이블에 CSV 데이터 저장 (공통 함수)

    Args:
        target_date: 저장할 날짜 (YYMMDD)
        filename: 파일명
        content: CSV 바이트 내용
        result_data: 결과를 저장할 딕셔너리
        source: 로그용 소스 표시 (예: "ensure/local", "ensure/download")
    """
    if auction_records_repo is None:
        return

    source_suffix = f" ({source})" if source else ""
    try:
        record_count = auction_records_repo.save_csv(target_date, filename, content)  # type: ignore[attr-defined]
        result_data["uploaded_to_auction_records"] = True
        result_data["auction_records_count"] = record_count
        logger.info(
            "auction_records 저장 성공%s: date=%s, records=%d",
            source_suffix, target_date, record_count
        )
    except Exception as ar_err:
        result_data["uploaded_to_auction_records"] = False
        result_data["auction_records_error"] = str(ar_err)
        logger.error(
            "auction_records 저장 실패%s: date=%s, filename=%s, content_size=%d, error=%s\n%s",
            source_suffix,
            target_date,
            filename,
            len(content) if content else 0,
            str(ar_err),
            traceback.format_exc()
        )


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
    _validate_admin_token(token)

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
                latest_hash = None
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

                    # 가장 최근 저장된 데이터의 해시도 조회 (중복 데이터 방지)
                    try:
                        latest_hash = supabase_repo.get_latest_file_hash()  # type: ignore[attr-defined]
                        result["latest_file_hash"] = latest_hash
                    except Exception:
                        latest_hash = None

                    # auction_records 테이블에도 데이터가 있는지 확인
                    if auction_records_repo is not None:
                        try:
                            auction_records_exists = auction_records_repo.exists(target_date)  # type: ignore[attr-defined]
                            result["auction_records_exists"] = auction_records_exists
                        except Exception:
                            auction_records_exists = False
                            result["auction_records_exists"] = False

                # 해시 비교: 해당 날짜 해시 또는 최근 해시와 동일하면 변경 없음
                hash_changed = (existing_hash is None) or (new_hash != existing_hash)
                is_duplicate_of_latest = (latest_hash is not None) and (new_hash == latest_hash)
                needs_auction_records = not auction_records_exists
                result["hash_changed"] = hash_changed
                result["is_duplicate_of_latest"] = is_duplicate_of_latest
                result["needs_auction_records"] = needs_auction_records

                # 최근 데이터와 동일하면 저장하지 않음 (원본 사이트 미업데이트)
                if is_duplicate_of_latest and not force:
                    result["uploaded_to_supabase"] = False
                    result["uploaded_to_auction_records"] = False
                    result["skip_reason"] = "duplicate_of_latest_data"
                    logger.info(
                        "크롤링 스킵: 원본 데이터 미업데이트 (latest_hash와 동일), target_date=%s",
                        target_date
                    )
                    return result

                # auction_data 저장 (해시가 변경된 경우만)
                should_upload_auction_data = (hash_changed or force) and content and filename
                if should_upload_auction_data:
                    try:
                        supabase_repo.save_csv(target_date, filename, content)  # type: ignore[attr-defined]
                        result["uploaded_to_supabase"] = True
                        result["supabase_row_id"] = target_date
                    except Exception as ad_err:
                        result["uploaded_to_supabase"] = False
                        result["supabase_error"] = str(ad_err)
                        logger.error(
                            "auction_data 저장 실패: date=%s, error=%s",
                            target_date, str(ad_err)
                        )
                else:
                    result["uploaded_to_supabase"] = False
                    result["supabase_row_id"] = target_date
                    if not hash_changed:
                        result["auction_data_skip_reason"] = "hash_unchanged"

                # auction_records 저장 (해시 변경 또는 레코드 없는 경우)
                should_upload_auction_records = (hash_changed or needs_auction_records or force) and content and filename
                if should_upload_auction_records:
                    _save_to_auction_records(target_date, filename, content, result)
                elif not should_upload_auction_records:
                    if not content:
                        result["skip_reason"] = "no_content"
                    elif not needs_auction_records and not hash_changed:
                        result["skip_reason"] = "hash_unchanged_and_records_exist"
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
    _validate_admin_token(token)

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
                _save_to_auction_records(target_date, filename, content, result_data, "ensure/local")

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
            _save_to_auction_records(target_date, final_filename, content, result_data, "ensure/download")

            return result_data
        except Exception as fe:
            raise HTTPException(status_code=500, detail=f"supabase_upload_failed: {fe}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"ensure failed: {exc}") from exc
