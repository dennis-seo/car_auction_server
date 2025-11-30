"""
auction_data 테이블 Repository (단순화된 버전)

CSV 파일 원본을 저장하고 조회하는 모듈.
실제 데이터 조회는 auction_records_repo.py를 사용.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import requests

from app.core.config import settings


logger = logging.getLogger("supabase")
_SESSION: Optional[requests.Session] = None


def _require_enabled() -> None:
    if not settings.SUPABASE_ENABLED:
        raise RuntimeError("Supabase integration is disabled")


def _base_url() -> str:
    url = (settings.SUPABASE_URL or "").strip().rstrip("/")
    if not url:
        raise RuntimeError("SUPABASE_URL must be configured")
    return url


def _table_name() -> str:
    table = (settings.SUPABASE_TABLE or "").strip()
    if not table:
        raise RuntimeError("SUPABASE_TABLE must be configured")
    return table


def _read_key() -> str:
    key = (settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY or "").strip()
    if not key:
        raise RuntimeError("Supabase API key is not configured")
    return key


def _service_key() -> str:
    key = (settings.SUPABASE_SERVICE_ROLE_KEY or "").strip()
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY must be configured for write operations")
    return key


def _session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
    return _SESSION


def _rest_headers(use_service: bool = False, extra: Optional[Dict[str, str]] = None, json_body: bool = False) -> Dict[str, str]:
    key = _service_key() if use_service else _read_key()
    headers: Dict[str, str] = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
    if json_body:
        headers["Content-Type"] = "application/json"
    if extra:
        headers.update(extra)
    return headers


def _hash_content(content: bytes) -> str:
    """SHA256 해시 생성"""
    return hashlib.sha256(content).hexdigest()


def _count_csv_rows(content: bytes) -> int:
    """CSV 행 수 계산"""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("cp949", errors="replace")

    reader = csv.reader(io.StringIO(text))
    # 헤더 제외
    next(reader, None)
    return sum(1 for _ in reader)


def list_dates() -> List[str]:
    """저장된 모든 날짜 목록 조회 (YYMMDD 형식)"""
    _require_enabled()
    session = _session()
    url = f"{_base_url()}/rest/v1/{_table_name()}"

    params = {
        "select": "date",
        "order": "date.desc",
    }
    resp = session.get(url, headers=_rest_headers(), params=params, timeout=30)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()

    payload = resp.json()
    dates: List[str] = []
    if isinstance(payload, list):
        for row in payload:
            if isinstance(row, dict):
                value = row.get("date")
                if isinstance(value, str):
                    dates.append(value)

    return dates


def get_csv(date: str) -> Optional[Tuple[bytes, str]]:
    """
    날짜별 CSV 파일 조회

    Args:
        date: YYMMDD 형식 날짜

    Returns:
        (CSV 바이트 내용, 파일명) 또는 None
    """
    _require_enabled()
    session = _session()
    url = f"{_base_url()}/rest/v1/{_table_name()}"

    params = {
        "select": "content,filename",
        "date": f"eq.{date}",
    }
    resp = session.get(url, headers=_rest_headers(), params=params, timeout=60)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()

    data = resp.json()
    if not isinstance(data, list) or not data:
        return None

    row = data[0]
    content = row.get("content")
    filename = row.get("filename") or f"auction_data_{date}.csv"

    if not content:
        return None

    # TEXT로 저장된 내용을 bytes로 변환
    content_bytes = content.encode("utf-8") if isinstance(content, str) else content
    return content_bytes, filename


def save_csv(date: str, filename: str, content: bytes) -> None:
    """
    CSV 파일 저장 (upsert)

    Args:
        date: YYMMDD 형식 날짜
        filename: 원본 파일명
        content: CSV 파일 바이트 내용
    """
    _require_enabled()
    if not content:
        raise ValueError("content is empty")

    session = _session()

    # CSV 내용을 TEXT로 변환
    try:
        content_text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        content_text = content.decode("cp949", errors="replace")

    # 레코드 생성
    record = {
        "date": date,
        "filename": os.path.basename(filename),
        "content": content_text,
        "row_count": _count_csv_rows(content),
        "file_hash": _hash_content(content),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Upsert (date가 unique key)
    url = f"{_base_url()}/rest/v1/{_table_name()}"
    headers = _rest_headers(
        use_service=True,
        json_body=True,
        extra={"Prefer": "resolution=merge-duplicates"}
    )

    resp = session.post(url, headers=headers, json=record, timeout=60)
    if resp.status_code not in (200, 201, 204):
        logger.error("Supabase upsert failed (status=%s): %s", resp.status_code, resp.text)
        resp.raise_for_status()

    logger.info("Saved CSV to auction_data: date=%s filename=%s rows=%d",
                date, filename, record["row_count"])


def exists(date: str) -> bool:
    """해당 날짜의 데이터 존재 여부 확인"""
    _require_enabled()
    session = _session()
    url = f"{_base_url()}/rest/v1/{_table_name()}"

    params = {
        "select": "date",
        "date": f"eq.{date}",
    }
    resp = session.get(url, headers=_rest_headers(), params=params, timeout=30)
    if resp.status_code == 404:
        return False
    resp.raise_for_status()

    data = resp.json()
    return isinstance(data, list) and len(data) > 0


def get_file_hash(date: str) -> Optional[str]:
    """해당 날짜의 파일 해시 조회 (중복 체크용)"""
    _require_enabled()
    session = _session()
    url = f"{_base_url()}/rest/v1/{_table_name()}"

    params = {
        "select": "file_hash",
        "date": f"eq.{date}",
    }
    resp = session.get(url, headers=_rest_headers(), params=params, timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()

    data = resp.json()
    if isinstance(data, list) and data:
        return data[0].get("file_hash")
    return None
