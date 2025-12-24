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
from typing import List, Optional, Tuple

from app.core.config import settings
from app.repositories.supabase_common import (
    require_enabled,
    base_url,
    session,
    rest_headers,
)
from app.utils.encoding import decode_csv_bytes


logger = logging.getLogger("supabase")


def _table_name() -> str:
    table = (settings.SUPABASE_TABLE or "").strip()
    if not table:
        raise RuntimeError("SUPABASE_TABLE must be configured")
    return table


def _hash_content(content: bytes) -> str:
    """SHA256 해시 생성"""
    return hashlib.sha256(content).hexdigest()


def _count_csv_rows(content: bytes) -> int:
    """CSV 행 수 계산"""
    text = decode_csv_bytes(content)
    reader = csv.reader(io.StringIO(text))
    # 헤더 제외
    next(reader, None)
    return sum(1 for _ in reader)


def list_dates() -> List[str]:
    """저장된 모든 날짜 목록 조회 (YYMMDD 형식)"""
    require_enabled()
    sess = session()
    url = f"{base_url()}/rest/v1/{_table_name()}"

    params = {
        "select": "date",
        "order": "date.desc",
    }
    resp = sess.get(url, headers=rest_headers(), params=params, timeout=30)
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
    require_enabled()
    sess = session()
    url = f"{base_url()}/rest/v1/{_table_name()}"

    params = {
        "select": "content,filename",
        "date": f"eq.{date}",
    }
    resp = sess.get(url, headers=rest_headers(), params=params, timeout=60)
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
    require_enabled()
    if not content:
        raise ValueError("content is empty")

    sess = session()

    # CSV 내용을 TEXT로 변환
    content_text = decode_csv_bytes(content)

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
    url = f"{base_url()}/rest/v1/{_table_name()}"
    headers = rest_headers(
        use_service=True,
        json_body=True,
        extra={"Prefer": "resolution=merge-duplicates"}
    )

    resp = sess.post(url, headers=headers, json=record, timeout=60)
    if resp.status_code not in (200, 201, 204):
        logger.error("Supabase upsert failed (status=%s): %s", resp.status_code, resp.text)
        resp.raise_for_status()

    logger.info("Saved CSV to auction_data: date=%s filename=%s rows=%d",
                date, filename, record["row_count"])


def exists(date: str) -> bool:
    """해당 날짜의 데이터 존재 여부 확인"""
    require_enabled()
    sess = session()
    url = f"{base_url()}/rest/v1/{_table_name()}"

    params = {
        "select": "date",
        "date": f"eq.{date}",
    }
    resp = sess.get(url, headers=rest_headers(), params=params, timeout=30)
    if resp.status_code == 404:
        return False
    resp.raise_for_status()

    data = resp.json()
    return isinstance(data, list) and len(data) > 0


def get_file_hash(date: str) -> Optional[str]:
    """해당 날짜의 파일 해시 조회 (중복 체크용)"""
    require_enabled()
    sess = session()
    url = f"{base_url()}/rest/v1/{_table_name()}"

    params = {
        "select": "file_hash",
        "date": f"eq.{date}",
    }
    resp = sess.get(url, headers=rest_headers(), params=params, timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()

    data = resp.json()
    if isinstance(data, list) and data:
        return data[0].get("file_hash")
    return None


def get_latest_file_hash() -> Optional[str]:
    """가장 최근 저장된 데이터의 파일 해시 조회 (중복 데이터 방지용)"""
    require_enabled()
    sess = session()
    url = f"{base_url()}/rest/v1/{_table_name()}"

    params = {
        "select": "file_hash,date",
        "order": "date.desc",
        "limit": "1",
    }
    resp = sess.get(url, headers=rest_headers(), params=params, timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()

    data = resp.json()
    if isinstance(data, list) and data:
        return data[0].get("file_hash")
    return None
