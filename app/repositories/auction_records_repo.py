"""
auction_records 테이블 Repository

새로운 정규화된 테이블에 데이터를 저장하고 조회하는 모듈.
기존 supabase_repo.py와 병행하여 사용.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple

import requests

from app.core.config import settings
from app.utils.title_parser import (
    parse_title,
    normalize_fuel,
    normalize_transmission,
    normalize_usage_type,
    normalize_score,
)


logger = logging.getLogger("auction_records")

_SESSION: Optional[requests.Session] = None
_TABLE_NAME = "auction_records"


def _require_enabled() -> None:
    """Supabase가 활성화되어 있는지 확인"""
    if not settings.SUPABASE_ENABLED:
        raise RuntimeError("Supabase integration is disabled")


def _base_url() -> str:
    url = (settings.SUPABASE_URL or "").strip().rstrip("/")
    if not url:
        raise RuntimeError("SUPABASE_URL must be configured")
    return url


def _service_key() -> str:
    key = (settings.SUPABASE_SERVICE_ROLE_KEY or "").strip()
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY must be configured for write operations")
    return key


def _read_key() -> str:
    key = (settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY or "").strip()
    if not key:
        raise RuntimeError("Supabase API key is not configured")
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


def _chunk(iterable: List[Dict[str, object]], size: int) -> Iterable[List[Dict[str, object]]]:
    """리스트를 청크로 분할"""
    for i in range(0, len(iterable), size):
        yield iterable[i : i + size]


def _safe_int(value: str) -> Optional[int]:
    """문자열을 정수로 안전하게 변환"""
    if not value:
        return None
    try:
        # 콤마 제거 후 변환
        cleaned = value.replace(",", "").strip()
        return int(cleaned) if cleaned else None
    except (ValueError, TypeError):
        return None


def _parse_csv_row(row: Dict[str, str], date: str, filename: str) -> Dict[str, object]:
    """
    CSV 행을 auction_records 테이블 레코드로 변환

    Args:
        row: CSV DictReader에서 읽은 행
        date: 경매 날짜 (YYMMDD 형식)
        filename: 원본 파일명

    Returns:
        auction_records 테이블에 저장할 딕셔너리
    """
    # 원본 필드 추출
    raw_post_title = row.get("Post Title", "").strip()
    raw_title = row.get("title", "").strip()
    raw_color = row.get("color", "").strip()
    raw_fuel = row.get("fuel", "").strip()
    raw_trans = row.get("trans", "").strip()
    raw_score = row.get("score", "").strip()

    # Title 파싱 (JSON 기준 ID 포함)
    parsed = parse_title(raw_post_title or raw_title)

    # 연료 타입 결정 (파싱 결과 우선, 없으면 raw_fuel에서 추출)
    fuel_type = parsed.fuel_type
    if not fuel_type:
        fuel_type = normalize_fuel(raw_fuel)
        # raw_fuel이 용도(자가용, 렌터카)인 경우 title에서 재추출 시도
        if not fuel_type and raw_title:
            parsed_from_title = parse_title(raw_title)
            fuel_type = parsed_from_title.fuel_type

    # 용도 타입 결정
    usage_type = normalize_usage_type(raw_fuel)

    # 날짜 변환 (YYMMDD -> YYYY-MM-DD)
    try:
        auction_date = f"20{date[:2]}-{date[2:4]}-{date[4:6]}"
    except (IndexError, ValueError):
        auction_date = date

    record: Dict[str, object] = {
        # 식별 정보
        "vin": row.get("vin", "").strip() or None,
        "car_number": row.get("car_number", "").strip(),

        # 경매 정보
        "auction_date": auction_date,
        "sell_number": _safe_int(row.get("sell_number", "")),
        "auction_house": row.get("auction_name", "").strip() or None,

        # JSON 기준 ID (car_models.json 기준)
        "manufacturer_id": parsed.manufacturer_id,
        "model_id": parsed.model_id,
        "trim_id": parsed.trim_id,

        # 정규화된 필드 (분석용)
        "manufacturer": parsed.manufacturer,
        "model": parsed.model,
        "sub_model": parsed.sub_model,
        "trim": parsed.trim,
        "year": _safe_int(row.get("year", "")),
        "fuel_type": fuel_type,
        "transmission": normalize_transmission(raw_trans),
        "engine_cc": parsed.engine_cc,
        "usage_type": usage_type,

        # 상태 정보
        "km": _safe_int(row.get("km", "")),
        "price": _safe_int(row.get("price", "")),
        "score": normalize_score(raw_score),
        "color": raw_color or None,
        "image_url": row.get("image", "").strip() or None,

        # 원본 필드 보존
        "raw_post_title": raw_post_title or None,
        "raw_title": raw_title or None,
        "raw_color": raw_color or None,
        "raw_fuel": raw_fuel or None,
        "raw_trans": raw_trans or None,
        "raw_score": raw_score or None,

        # 메타 정보
        "source_filename": filename,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    return record


def _parse_csv_content(date: str, filename: str, content: bytes) -> List[Dict[str, object]]:
    """CSV 바이트 내용을 파싱하여 레코드 리스트 반환"""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("cp949", errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    rows: List[Dict[str, object]] = []

    for raw_row in reader:
        if not isinstance(raw_row, dict):
            continue
        record = _parse_csv_row(raw_row, date, filename)
        rows.append(record)

    return rows


def _delete_by_date(date: str) -> None:
    """특정 날짜의 레코드 삭제"""
    session = _session()
    # YYMMDD -> YYYY-MM-DD 변환
    try:
        auction_date = f"20{date[:2]}-{date[2:4]}-{date[4:6]}"
    except (IndexError, ValueError):
        auction_date = date

    url = f"{_base_url()}/rest/v1/{_TABLE_NAME}"
    params = {"auction_date": f"eq.{auction_date}"}
    headers = _rest_headers(use_service=True, extra={"Prefer": "count=exact"})

    resp = session.delete(url, headers=headers, params=params, timeout=30)
    if resp.status_code not in (200, 204):
        logger.error("Delete failed (status=%s): %s", resp.status_code, resp.text)
        resp.raise_for_status()


def _insert_rows(rows: List[Dict[str, object]]) -> None:
    """레코드 삽입"""
    if not rows:
        return

    session = _session()
    headers = _rest_headers(use_service=True, json_body=True, extra={"Prefer": "resolution=merge-duplicates"})
    url = f"{_base_url()}/rest/v1/{_TABLE_NAME}"

    for chunk in _chunk(rows, 500):
        resp = session.post(url, headers=headers, json=chunk, timeout=60)
        if resp.status_code not in (200, 201, 204):
            logger.error("Insert failed (status=%s): %s", resp.status_code, resp.text)
            resp.raise_for_status()


def save_csv(date: str, filename: str, content: bytes) -> int:
    """
    CSV 데이터를 auction_records 테이블에 저장

    Args:
        date: 경매 날짜 (YYMMDD 형식)
        filename: 원본 파일명
        content: CSV 파일 바이트 내용

    Returns:
        저장된 레코드 수
    """
    _require_enabled()

    if not content:
        raise ValueError("content is empty")

    rows = _parse_csv_content(date, filename, content)
    if not rows:
        logger.warning("CSV parsed with 0 rows date=%s filename=%s (skipping)", date, filename)
        return 0

    # 기존 데이터 삭제 후 삽입
    _delete_by_date(date)
    _insert_rows(rows)

    logger.info("Saved %d records to auction_records for date=%s", len(rows), date)
    return len(rows)


def list_dates() -> List[str]:
    """저장된 모든 날짜 목록 조회 (YYYY-MM-DD 형식)"""
    _require_enabled()

    session = _session()
    url = f"{_base_url()}/rest/v1/{_TABLE_NAME}"
    params = {
        "select": "auction_date",
        "order": "auction_date.desc",
    }

    resp = session.get(url, headers=_rest_headers(), params=params, timeout=20)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()

    payload = resp.json()
    seen: set[str] = set()
    dates: List[str] = []

    if isinstance(payload, list):
        for row in payload:
            if not isinstance(row, dict):
                continue
            value = row.get("auction_date")
            if isinstance(value, str) and value not in seen:
                seen.add(value)
                dates.append(value)

    return dates


def get_records_by_date(date: str) -> List[Dict[str, object]]:
    """
    특정 날짜의 경매 레코드 조회

    Args:
        date: YYMMDD 또는 YYYY-MM-DD 형식

    Returns:
        레코드 리스트
    """
    _require_enabled()

    # YYMMDD -> YYYY-MM-DD 변환
    if len(date) == 6 and date.isdigit():
        auction_date = f"20{date[:2]}-{date[2:4]}-{date[4:6]}"
    else:
        auction_date = date

    session = _session()
    url = f"{_base_url()}/rest/v1/{_TABLE_NAME}"
    params = {
        "select": "*",
        "auction_date": f"eq.{auction_date}",
        "order": "sell_number.asc",
    }

    resp = session.get(url, headers=_rest_headers(), params=params, timeout=60)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()

    data = resp.json()
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def get_csv_format(date: str) -> Optional[Tuple[bytes, str]]:
    """
    기존 API 호환을 위해 CSV 형식으로 데이터 반환

    Args:
        date: YYMMDD 또는 YYYY-MM-DD 형식

    Returns:
        (CSV 바이트 내용, 파일명) 또는 None
    """
    records = get_records_by_date(date)
    if not records:
        return None

    # CSV 헤더 (기존 형식과 동일)
    headers = [
        "Post Title", "sell_number", "car_number", "color", "fuel",
        "image", "km", "price", "title", "trans", "year",
        "auction_name", "vin", "score"
    ]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)

    for row in records:
        writer.writerow([
            row.get("raw_post_title") or "",
            row.get("sell_number") or "",
            row.get("car_number") or "",
            row.get("raw_color") or "",
            row.get("raw_fuel") or "",
            row.get("image_url") or "",
            row.get("km") or "",
            row.get("price") or "",
            row.get("raw_title") or "",
            row.get("raw_trans") or "",
            row.get("year") or "",
            row.get("auction_house") or "",
            row.get("vin") or "",
            row.get("raw_score") or "",
        ])

    content = output.getvalue().encode("utf-8")
    filename = records[0].get("source_filename") or f"auction_data_{date}.csv"
    return content, str(filename)


def search_vehicles(
    manufacturer_id: Optional[str] = None,
    model_id: Optional[str] = None,
    trim_id: Optional[str] = None,
    manufacturer: Optional[str] = None,
    model: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> Tuple[List[Dict[str, object]], int]:
    """
    차량 검색 (필터링 지원)

    Args:
        manufacturer_id: 제조사 ID 필터
        model_id: 모델 ID 필터
        trim_id: 트림 ID 필터
        manufacturer: 제조사명 필터
        model: 모델명 필터 (부분 일치)
        year_from: 연식 시작
        year_to: 연식 끝
        date_from: 경매일 시작 (YYYY-MM-DD)
        date_to: 경매일 끝 (YYYY-MM-DD)
        limit: 최대 조회 수
        offset: 오프셋

    Returns:
        (레코드 리스트, 전체 개수)
    """
    _require_enabled()

    session = _session()
    base_url = f"{_base_url()}/rest/v1/{_TABLE_NAME}"

    # 필터 파라미터 구성
    params: Dict[str, str] = {}

    if manufacturer_id:
        params["manufacturer_id"] = f"eq.{manufacturer_id}"
    if model_id:
        params["model_id"] = f"eq.{model_id}"
    if trim_id:
        params["trim_id"] = f"eq.{trim_id}"
    if manufacturer:
        params["manufacturer"] = f"eq.{manufacturer}"
    if model:
        params["model"] = f"ilike.*{model}*"
    if year_from and year_to:
        params["year"] = f"gte.{year_from}&year=lte.{year_to}"
    elif year_from:
        params["year"] = f"gte.{year_from}"
    elif year_to:
        params["year"] = f"lte.{year_to}"
    if date_from and date_to:
        params["auction_date"] = f"gte.{date_from}&auction_date=lte.{date_to}"
    elif date_from:
        params["auction_date"] = f"gte.{date_from}"
    elif date_to:
        params["auction_date"] = f"lte.{date_to}"

    # 전체 개수 조회
    count_params = {**params, "select": "count"}
    count_headers = _rest_headers(extra={"Prefer": "count=exact"})
    count_resp = session.head(base_url, headers=count_headers, params=count_params, timeout=30)

    total = 0
    if "content-range" in count_resp.headers:
        # Format: "0-99/1234" or "*/0"
        range_header = count_resp.headers["content-range"]
        if "/" in range_header:
            total_str = range_header.split("/")[-1]
            if total_str != "*":
                total = int(total_str)

    # 데이터 조회
    data_params = {
        **params,
        "select": "*",
        "order": "auction_date.desc,sell_number.asc",
        "limit": str(limit),
        "offset": str(offset),
    }

    resp = session.get(base_url, headers=_rest_headers(extra={"Prefer": "count=exact"}), params=data_params, timeout=60)
    if resp.status_code == 404:
        return [], 0
    resp.raise_for_status()

    # content-range에서 total 가져오기
    if "content-range" in resp.headers:
        range_header = resp.headers["content-range"]
        if "/" in range_header:
            total_str = range_header.split("/")[-1]
            if total_str != "*":
                total = int(total_str)

    data = resp.json()
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)], total
    return [], total


def get_price_history(
    manufacturer: Optional[str] = None,
    model: Optional[str] = None,
    year: Optional[int] = None,
    limit: int = 1000
) -> List[Dict[str, object]]:
    """
    가격 히스토리 조회 (분석용)

    Args:
        manufacturer: 제조사 필터
        model: 모델명 필터
        year: 연식 필터
        limit: 최대 조회 수

    Returns:
        가격 히스토리 레코드 리스트
    """
    _require_enabled()

    session = _session()
    url = f"{_base_url()}/rest/v1/{_TABLE_NAME}"
    params: Dict[str, str] = {
        "select": "auction_date,manufacturer,model,sub_model,year,km,price,score,fuel_type",
        "order": "auction_date.desc",
        "limit": str(limit),
    }

    if manufacturer:
        params["manufacturer"] = f"eq.{manufacturer}"
    if model:
        params["model"] = f"ilike.*{model}*"
    if year:
        params["year"] = f"eq.{year}"

    resp = session.get(url, headers=_rest_headers(), params=params, timeout=60)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()

    data = resp.json()
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []
