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
from typing import Dict, List, Optional, Tuple

from app.repositories.supabase_common import (
    require_enabled,
    base_url,
    session,
    rest_headers,
    chunk,
)
from app.utils.bizdate import yymmdd_to_iso
from app.utils.encoding import decode_csv_bytes
from app.utils.title_parser import (
    parse_title,
    normalize_fuel,
    normalize_transmission,
    normalize_usage_type,
    normalize_score,
)


logger = logging.getLogger("auction_records")

_TABLE_NAME = "auction_records"


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
    auction_name = row.get("auction_name", "").strip()

    # 오토허브 경매장: color/trans 컬럼이 뒤바뀌어 내려옴
    is_autohub = auction_name == "오토허브 경매장"
    if is_autohub:
        # trans -> color, color -> trans 스왑
        actual_color = raw_trans
        actual_trans = raw_color
    else:
        actual_color = raw_color
        actual_trans = raw_trans

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
    auction_date = yymmdd_to_iso(date)

    record: Dict[str, object] = {
        # 식별 정보
        "vin": row.get("vin", "").strip() or None,
        "car_number": row.get("car_number", "").strip(),

        # 경매 정보
        "auction_date": auction_date,
        "sell_number": _safe_int(row.get("sell_number", "")),
        "auction_house": auction_name or None,

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
        "transmission": normalize_transmission(actual_trans),
        "engine_cc": parsed.engine_cc,
        "usage_type": usage_type,

        # 상태 정보
        "km": _safe_int(row.get("km", "")),
        "price": _safe_int(row.get("price", "")),
        "score": normalize_score(raw_score),
        "color": actual_color or None,
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
    """CSV 바이트 내용을 파싱하여 레코드 리스트 반환 (중복 제거)"""
    text = decode_csv_bytes(content)
    reader = csv.DictReader(io.StringIO(text))
    rows: List[Dict[str, object]] = []
    seen_keys: set[tuple[object, ...]] = set()

    for raw_row in reader:
        if not isinstance(raw_row, dict):
            continue
        record = _parse_csv_row(raw_row, date, filename)

        # unique constraint: (auction_date, sell_number, auction_house)
        key = (record.get("auction_date"), record.get("sell_number"), record.get("auction_house"))
        if key in seen_keys:
            continue  # 중복 스킵
        seen_keys.add(key)

        rows.append(record)

    return rows


def _delete_by_date(date: str) -> None:
    """특정 날짜의 레코드 삭제"""
    sess = session()
    # YYMMDD -> YYYY-MM-DD 변환
    auction_date = yymmdd_to_iso(date)

    url = f"{base_url()}/rest/v1/{_TABLE_NAME}"
    params = {"auction_date": f"eq.{auction_date}"}
    headers = rest_headers(use_service=True, extra={"Prefer": "count=exact"})

    resp = sess.delete(url, headers=headers, params=params, timeout=30)
    if resp.status_code not in (200, 204):
        logger.error("Delete failed (status=%s): %s", resp.status_code, resp.text)
        resp.raise_for_status()


def _insert_rows(rows: List[Dict[str, object]]) -> None:
    """레코드 삽입"""
    if not rows:
        return

    sess = session()
    headers = rest_headers(use_service=True, json_body=True, extra={"Prefer": "resolution=merge-duplicates"})
    url = f"{base_url()}/rest/v1/{_TABLE_NAME}"

    for batch in chunk(rows, 500):
        resp = sess.post(url, headers=headers, json=batch, timeout=60)
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
    require_enabled()

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


def list_dates(limit: Optional[int] = None) -> List[str]:
    """
    저장된 날짜 목록 조회 (YYYY-MM-DD 형식)

    Args:
        limit: 반환할 최대 날짜 수 (None이면 전체)

    Returns:
        날짜 목록 (최신순 정렬)
    """
    require_enabled()

    sess = session()

    # RPC 함수를 통한 DISTINCT 쿼리 시도
    # Supabase에서 distinct_auction_dates 함수가 있으면 사용
    rpc_url = f"{base_url()}/rest/v1/rpc/distinct_auction_dates"
    try:
        rpc_params: Dict[str, str] = {}
        if limit:
            rpc_params["p_limit"] = str(limit)

        resp = sess.post(
            rpc_url,
            headers=rest_headers(json_body=True),
            json={"p_limit": limit} if limit else {},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                dates = [row.get("auction_date") if isinstance(row, dict) else row for row in data]
                return [d for d in dates if isinstance(d, str)]
    except Exception:
        pass  # RPC 함수가 없으면 기존 방식으로 폴백

    # 폴백: 기존 페이지네이션 방식
    url = f"{base_url()}/rest/v1/{_TABLE_NAME}"

    seen: set[str] = set()
    offset = 0
    page_size = 1000

    while True:
        params = {
            "select": "auction_date",
            "order": "auction_date.desc",
            "limit": str(page_size),
            "offset": str(offset),
        }

        resp = sess.get(url, headers=rest_headers(), params=params, timeout=30)
        if resp.status_code == 404:
            break
        resp.raise_for_status()

        payload = resp.json()
        if not isinstance(payload, list) or not payload:
            break

        for row in payload:
            if not isinstance(row, dict):
                continue
            value = row.get("auction_date")
            if isinstance(value, str):
                seen.add(value)

        # limit이 지정되고 충분한 날짜를 수집했으면 조기 종료
        if limit and len(seen) >= limit:
            break

        if len(payload) < page_size:
            break
        offset += page_size

    result = sorted(seen, reverse=True)

    # limit 적용
    if limit and len(result) > limit:
        result = result[:limit]

    return result


def get_records_by_date(date: str) -> List[Dict[str, object]]:
    """
    특정 날짜의 경매 레코드 조회

    Args:
        date: YYMMDD 또는 YYYY-MM-DD 형식

    Returns:
        레코드 리스트
    """
    require_enabled()

    # YYMMDD -> YYYY-MM-DD 변환
    auction_date = yymmdd_to_iso(date)

    sess = session()
    url = f"{base_url()}/rest/v1/{_TABLE_NAME}"
    params = {
        "select": "*",
        "auction_date": f"eq.{auction_date}",
        "order": "sell_number.asc",
    }

    resp = sess.get(url, headers=rest_headers(), params=params, timeout=60)
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
    require_enabled()

    sess = session()
    api_url = f"{base_url()}/rest/v1/{_TABLE_NAME}"

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
    # 연식 필터 - and 조건으로 처리
    and_conditions = []
    if year_from:
        and_conditions.append(f"year.gte.{year_from}")
    if year_to:
        and_conditions.append(f"year.lte.{year_to}")
    if date_from:
        and_conditions.append(f"auction_date.gte.{date_from}")
    if date_to:
        and_conditions.append(f"auction_date.lte.{date_to}")

    if and_conditions:
        params["and"] = f"({','.join(and_conditions)})"

    # 전체 개수 조회
    count_params = {**params, "select": "count"}
    count_headers = rest_headers(extra={"Prefer": "count=exact"})
    count_resp = sess.head(api_url, headers=count_headers, params=count_params, timeout=30)

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

    resp = sess.get(api_url, headers=rest_headers(extra={"Prefer": "count=exact"}), params=data_params, timeout=60)
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
    require_enabled()

    sess = session()
    url = f"{base_url()}/rest/v1/{_TABLE_NAME}"
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

    resp = sess.get(url, headers=rest_headers(), params=params, timeout=60)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()

    data = resp.json()
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def get_by_id(record_id: int) -> Optional[Dict[str, object]]:
    """
    ID로 단일 레코드 조회

    Args:
        record_id: 레코드 ID

    Returns:
        레코드 딕셔너리 또는 None
    """
    require_enabled()

    sess = session()
    url = f"{base_url()}/rest/v1/{_TABLE_NAME}"
    params = {
        "id": f"eq.{record_id}",
        "select": "*",
    }

    resp = sess.get(url, headers=rest_headers(), params=params, timeout=30)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()

    data = resp.json()
    if isinstance(data, list) and data:
        return data[0] if isinstance(data[0], dict) else None
    return None


def get_aggregated_history(
    manufacturer_id: str,
    model_id: str,
    trim_id: Optional[str] = None,
    min_dates: int = 5,
    max_per_date: int = 10,
    max_total: int = 100,
    months: int = 12,
    exclude_date: Optional[str] = None,
) -> Dict[str, object]:
    """
    차량 시세 히스토리 집계 조회

    날짜별로 분산된 데이터를 제공하여 그래프가 제대로 그려지도록 합니다.
    인기 모델의 경우 특정 날짜에 데이터가 집중되는 문제를 해결합니다.

    Args:
        manufacturer_id: 제조사 ID (필수)
        model_id: 모델 ID (필수)
        trim_id: 트림 ID (선택, 없으면 모델 전체)
        min_dates: 최소 확보할 날짜 수 (기본값 5)
        max_per_date: 날짜별 최대 거래 건수 (기본값 10)
        max_total: 전체 최대 거래 건수 (기본값 100)
        months: 조회 기간 개월 수 (기본값 12)
        exclude_date: 제외할 날짜 (현재 경매일, YYYY-MM-DD 형식)

    Returns:
        {
            "summary": { ... },
            "data": [ ... ]
        }
    """
    require_enabled()

    from datetime import timedelta
    from dateutil.relativedelta import relativedelta

    sess = session()
    url = f"{base_url()}/rest/v1/{_TABLE_NAME}"

    # 조회 기간 계산
    today = datetime.now(timezone.utc).date()
    date_from = (today - relativedelta(months=months)).isoformat()

    # 필터 조건 구성
    params: Dict[str, str] = {
        "select": "auction_date,price,km,year,score",
        "manufacturer_id": f"eq.{manufacturer_id}",
        "model_id": f"eq.{model_id}",
        "order": "auction_date.desc,price.asc",
        "limit": "2000",  # 충분한 데이터 확보
    }

    # 트림 필터
    if trim_id:
        params["trim_id"] = f"eq.{trim_id}"

    # 날짜 범위 및 제외 조건
    and_conditions = [f"auction_date.gte.{date_from}"]
    if exclude_date:
        and_conditions.append(f"auction_date.neq.{exclude_date}")
    # price가 null이 아닌 레코드만
    and_conditions.append("price.not.is.null")

    params["and"] = f"({','.join(and_conditions)})"

    # 데이터 조회
    resp = sess.get(url, headers=rest_headers(), params=params, timeout=60)
    if resp.status_code == 404:
        return _empty_aggregated_response()
    resp.raise_for_status()

    raw_data = resp.json()
    if not isinstance(raw_data, list) or not raw_data:
        return _empty_aggregated_response()

    # 날짜별 그룹화
    date_groups: Dict[str, List[Dict[str, object]]] = {}
    for row in raw_data:
        if not isinstance(row, dict):
            continue
        date = row.get("auction_date")
        if not date:
            continue
        if date not in date_groups:
            date_groups[date] = []
        date_groups[date].append(row)

    if not date_groups:
        return _empty_aggregated_response()

    # 날짜 역순 정렬 (최신 날짜부터)
    sorted_dates = sorted(date_groups.keys(), reverse=True)

    # 날짜별 샘플링 및 집계
    result_data: List[Dict[str, object]] = []
    total_trades_count = 0
    all_prices: List[int] = []

    for date in sorted_dates:
        # 최소 날짜 수 확보 전까지는 계속 수집
        # 최소 날짜 수 확보 후에는 max_total 체크
        if len(result_data) >= min_dates and total_trades_count >= max_total:
            break

        trades = date_groups[date]
        original_count = len(trades)

        # 가격이 있는 거래만 필터
        valid_trades = [t for t in trades if t.get("price") is not None]
        if not valid_trades:
            continue

        # 날짜별 통계 계산 (원본 기준)
        prices = [t["price"] for t in valid_trades]
        date_min = min(prices)
        date_max = max(prices)
        date_avg = sum(prices) / len(prices)

        # 균등 샘플링 (가격 기준)
        sampled_trades = _sample_trades_by_price(valid_trades, max_per_date)

        # 남은 허용량 계산
        remaining = max_total - total_trades_count
        if remaining < len(sampled_trades) and len(result_data) >= min_dates:
            sampled_trades = sampled_trades[:remaining]

        # 결과에 추가
        trade_items = [
            {
                "price": t.get("price"),
                "km": t.get("km"),
                "year": t.get("year"),
                "score": t.get("score"),
            }
            for t in sampled_trades
        ]

        result_data.append({
            "date": date,
            "count": original_count,
            "avg_price": round(date_avg, 1),
            "min_price": date_min,
            "max_price": date_max,
            "trades": trade_items,
        })

        total_trades_count += len(sampled_trades)
        all_prices.extend([t.get("price") for t in sampled_trades if t.get("price")])

    # 날짜 오름차순 정렬 (그래프 X축 순서)
    result_data.sort(key=lambda x: x["date"])

    # 전체 통계 계산
    summary = {
        "total_count": total_trades_count,
        "date_count": len(result_data),
        "min_price": min(all_prices) if all_prices else None,
        "max_price": max(all_prices) if all_prices else None,
        "avg_price": round(sum(all_prices) / len(all_prices), 1) if all_prices else None,
    }

    return {
        "summary": summary,
        "data": result_data,
    }


def _sample_trades_by_price(
    trades: List[Dict[str, object]],
    max_count: int
) -> List[Dict[str, object]]:
    """
    가격 기준 균등 샘플링

    최저~최고 가격 범위에서 대표성 있는 샘플을 선택합니다.
    """
    if len(trades) <= max_count:
        return trades

    # 가격 기준 정렬
    sorted_trades = sorted(trades, key=lambda x: x.get("price") or 0)

    # 균등 간격으로 샘플링
    step = len(sorted_trades) / max_count
    sampled = []
    for i in range(max_count):
        idx = int(i * step)
        sampled.append(sorted_trades[idx])

    return sampled


def _empty_aggregated_response() -> Dict[str, object]:
    """빈 집계 응답 반환"""
    return {
        "summary": {
            "total_count": 0,
            "date_count": 0,
            "min_price": None,
            "max_price": None,
            "avg_price": None,
        },
        "data": [],
    }
