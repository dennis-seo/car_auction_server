import csv
import io
import logging
from typing import Dict, List, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)
from app.repositories.file_repo import list_auction_csv_files, resolve_csv_filepath
from app.utils.bizdate import next_business_day, previous_source_candidates_for_mapped
from app.schemas.auction import AuctionItem, AuctionResponse
from app.utils.model_matcher import match_car_model
from app.utils.encoding import decode_csv_bytes

try:
    # Optional import; only used when enabled
    from app.repositories import supabase_repo  # type: ignore
    from app.repositories import auction_records_repo  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    supabase_repo = None  # type: ignore
    auction_records_repo = None  # type: ignore


def _supabase_enabled() -> bool:
    return settings.SUPABASE_ENABLED and supabase_repo is not None


def _auction_records_enabled() -> bool:
    return settings.SUPABASE_ENABLED and auction_records_repo is not None


def list_available_dates(limit: Optional[int] = None) -> list[str]:
    """사용 가능한 날짜 목록 조회 (YYYY-MM-DD 형식)

    Args:
        limit: 반환할 최대 날짜 수 (None이면 전체)

    Returns:
        날짜 목록 (최신순 정렬)
    """
    # auction_records 테이블에서 날짜 조회 (우선)
    if _auction_records_enabled():
        try:
            return auction_records_repo.list_dates(limit=limit)  # type: ignore[attr-defined]
        except Exception as e:
            logger.warning("auction_records에서 날짜 목록 조회 실패, fallback 진행: %s", e)

    # auction_data 테이블에서 날짜 조회
    if _supabase_enabled():
        try:
            result = supabase_repo.list_dates()  # type: ignore[attr-defined]
            if limit and len(result) > limit:
                result = result[:limit]
            return result
        except Exception as e:
            logger.warning("supabase에서 날짜 목록 조회 실패, 로컬 파일로 fallback: %s", e)

    # Fallback: 로컬 파일
    files = list_auction_csv_files()
    mapped: set[str] = set()
    for name in files:
        # Expecting pattern: auction_data_YYMMDD.csv (original source date)
        if name.startswith("auction_data_") and name.endswith(".csv"):
            src_date = name.replace("auction_data_", "").replace(".csv", "")
            if len(src_date) == 6 and src_date.isdigit():
                try:
                    mapped.add(next_business_day(src_date))
                except Exception as e:
                    logger.debug("날짜 변환 실패 (src_date=%s): %s", src_date, e)
                    continue
    result = sorted(mapped, reverse=True)

    if limit and len(result) > limit:
        result = result[:limit]

    return result


def get_csv_path_for_date(date: str) -> Tuple[Optional[str], str]:
    filename = f"auction_data_{date}.csv"
    # When Supabase is enabled, we return (None, filename) to indicate remote fetch
    if _supabase_enabled():
        return None, filename
    # Local mode: requested date is mapped business date. Find source file by candidates.
    for src in previous_source_candidates_for_mapped(date):
        fname = f"auction_data_{src}.csv"
        path = resolve_csv_filepath(fname)
        if path:
            return path, fname
    # Fallback: try exact name if present
    path = resolve_csv_filepath(filename)
    return path, filename


def get_csv_content_for_date(date: str) -> Tuple[Optional[bytes], str]:
    """Fetch CSV content bytes (Supabase) or None with filename for context."""
    filename = f"auction_data_{date}.csv"
    if _supabase_enabled():
        try:
            res = supabase_repo.get_csv(date)  # type: ignore[attr-defined]
            if res is None:
                return None, filename
            content, fname = res
            return content, fname or filename
        except Exception as e:
            logger.warning("supabase에서 CSV 조회 실패 (date=%s): %s", date, e)
            return None, filename
    # Local mode: read file content
    path, actual_filename = get_csv_path_for_date(date)
    if not path:
        return None, filename
    try:
        with open(path, "rb") as f:
            return f.read(), actual_filename
    except Exception as e:
        logger.warning("로컬 CSV 파일 읽기 실패 (path=%s): %s", path, e)
        return None, filename


def _parse_csv_to_items(content: bytes) -> List[AuctionItem]:
    """CSV 바이트를 AuctionItem 리스트로 파싱"""
    text = decode_csv_bytes(content)
    reader = csv.DictReader(io.StringIO(text))
    items: List[AuctionItem] = []

    for row in reader:
        if not isinstance(row, dict):
            continue

        # Post Title에서 제조사/모델/트림 ID 파싱
        post_title = row.get("Post Title", "")
        match_result = match_car_model(post_title) if post_title else None

        item = AuctionItem(
            post_title=post_title,
            sell_number=row.get("sell_number", ""),
            car_number=row.get("car_number", ""),
            color=row.get("color", ""),
            fuel=row.get("fuel", ""),
            image=row.get("image", ""),
            km=row.get("km", ""),
            price=row.get("price", ""),
            title=row.get("title", ""),
            trans=row.get("trans", ""),
            year=row.get("year", ""),
            auction_name=row.get("auction_name", ""),
            vin=row.get("vin", ""),
            score=row.get("score", ""),
            # 파싱된 ID 값
            manufacturer_id=match_result.manufacturer_id if match_result else None,
            model_id=match_result.model_id if match_result else None,
            trim_id=match_result.trim_id if match_result else None,
            # 파싱된 정규화 값
            manufacturer=match_result.manufacturer_name if match_result else None,
            model=match_result.model_name if match_result else None,
            trim=match_result.trim_name if match_result else None,
        )
        items.append(item)

    return items


def _record_to_auction_item(record: Dict[str, object]) -> AuctionItem:
    """auction_records 레코드를 AuctionItem으로 변환"""
    return AuctionItem(
        post_title=str(record.get("raw_post_title") or ""),
        sell_number=str(record.get("sell_number") or ""),
        car_number=str(record.get("car_number") or ""),
        color=str(record.get("raw_color") or ""),
        fuel=str(record.get("raw_fuel") or ""),
        image=str(record.get("image_url") or ""),
        km=str(record.get("km") or ""),
        price=str(record.get("price") or ""),
        title=str(record.get("raw_title") or ""),
        trans=str(record.get("raw_trans") or ""),
        year=str(record.get("year") or ""),
        auction_name=str(record.get("auction_house") or ""),
        vin=str(record.get("vin") or ""),
        score=str(record.get("raw_score") or ""),
        # 정규화된 ID (auction_records에서 이미 파싱됨)
        manufacturer_id=record.get("manufacturer_id"),
        model_id=record.get("model_id"),
        trim_id=record.get("trim_id"),
        manufacturer=record.get("manufacturer"),
        model=record.get("model"),
        trim=record.get("trim"),
    )


def get_auction_data_for_date(date: str) -> Optional[AuctionResponse]:
    """날짜별 경매 데이터를 JSON 형식으로 반환"""
    # auction_records에서 조회 (우선)
    if _auction_records_enabled():
        try:
            records = auction_records_repo.get_records_by_date(date)  # type: ignore[attr-defined]
            if records:
                items = [_record_to_auction_item(r) for r in records]
                # source_filename 추출
                filename = records[0].get("source_filename") or f"auction_data_{date}.csv"
                return AuctionResponse(
                    date=date,
                    source_filename=str(filename),
                    row_count=len(items),
                    items=items,
                )
        except Exception as e:
            logger.warning("auction_records에서 데이터 조회 실패 (date=%s), CSV fallback: %s", date, e)

    # Fallback: CSV 파싱 방식
    content, filename = get_csv_content_for_date(date)
    if content is None:
        return None

    items = _parse_csv_to_items(content)

    return AuctionResponse(
        date=date,
        source_filename=filename,
        row_count=len(items),
        items=items,
    )
