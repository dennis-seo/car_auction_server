import csv
import io
from typing import List, Optional, Tuple

from app.core.config import settings
from app.repositories.file_repo import list_auction_csv_files, resolve_csv_filepath
from app.utils.bizdate import next_business_day, previous_source_candidates_for_mapped
from app.schemas.auction import AuctionItem, AuctionResponse
from app.utils.model_matcher import match_car_model

try:
    # Optional import; only used when enabled
    from app.repositories import supabase_repo  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    supabase_repo = None  # type: ignore


def _supabase_enabled() -> bool:
    return settings.SUPABASE_ENABLED and supabase_repo is not None


def list_available_dates() -> list[str]:
    if _supabase_enabled():
        try:
            return supabase_repo.list_dates()  # type: ignore[attr-defined]
        except Exception:
            # Fallback to local listing on failure
            pass
    files = list_auction_csv_files()
    mapped: set[str] = set()
    for name in files:
        # Expecting pattern: auction_data_YYMMDD.csv (original source date)
        if name.startswith("auction_data_") and name.endswith(".csv"):
            src_date = name.replace("auction_data_", "").replace(".csv", "")
            if len(src_date) == 6 and src_date.isdigit():
                try:
                    mapped.add(next_business_day(src_date))
                except Exception:
                    continue
    result = sorted(mapped, reverse=True)
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
        except Exception:
            return None, filename
    # Local mode: read file content
    path, actual_filename = get_csv_path_for_date(date)
    if not path:
        return None, filename
    try:
        with open(path, "rb") as f:
            return f.read(), actual_filename
    except Exception:
        return None, filename


def _parse_csv_to_items(content: bytes) -> List[AuctionItem]:
    """CSV 바이트를 AuctionItem 리스트로 파싱"""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("cp949", errors="replace")

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


def get_auction_data_for_date(date: str) -> Optional[AuctionResponse]:
    """날짜별 경매 데이터를 JSON 형식으로 반환"""
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
