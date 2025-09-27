import csv
import io
from typing import Any, Dict, Optional, Tuple

from app.core.config import settings
from app.repositories.file_repo import list_auction_csv_files, resolve_csv_filepath
from app.utils.bizdate import next_business_day, previous_source_candidates_for_mapped

try:
    # Optional import; only used when enabled
    from app.repositories import spanner_repo  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    spanner_repo = None  # type: ignore


def list_available_dates() -> list[str]:
    if settings.SPANNER_ENABLED and spanner_repo is not None:
        # 스패너 모드에서는 예외를 숨기지 않고 그대로 노출해 연결 상태를 확인한다.
        return spanner_repo.list_dates()  # type: ignore[attr-defined]
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
    # When Spanner is enabled, we return (None, filename) to indicate remote fetch
    if settings.SPANNER_ENABLED and spanner_repo is not None:
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
    """Fetch CSV content bytes (Spanner) or None with filename for context."""
    filename = f"auction_data_{date}.csv"
    if settings.SPANNER_ENABLED and spanner_repo is not None:
        try:
            res = spanner_repo.get_csv(date)  # type: ignore[attr-defined]
            if res is None:
                return None, filename
            content, fname = res
            return content, fname or filename
        except Exception:
            return None, filename
    # Local mode: read file content
    path = resolve_csv_filepath(filename)
    if not path:
        return None, filename
    try:
        with open(path, "rb") as f:
            return f.read(), filename
    except Exception:
        return None, filename


def get_auction_data_for_date(date: str) -> Optional[Dict[str, Any]]:
    if settings.SPANNER_ENABLED and spanner_repo is not None:
        return spanner_repo.get_items(date)  # type: ignore[attr-defined]

    content, filename = get_csv_content_for_date(date)
    if content is None:
        return None

    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    items: list[Dict[str, Any]] = []

    for idx, row in enumerate(reader, start=1):
        if not row:
            continue
        items.append(
            {
                "row_order": idx,
                "sell_number": _safe_int(row.get("sell_number")),
                "car_number": _safe_str(row.get("car_number")),
                "post_title": _safe_str(row.get("Post Title")),
                "title": _safe_str(row.get("title")),
                "color": _safe_str(row.get("color")),
                "fuel": _safe_str(row.get("fuel")),
                "image": _safe_str(row.get("image")),
                "km": _safe_int(row.get("km")),
                "price": _safe_int(row.get("price")),
                "trans": _safe_str(row.get("trans")),
                "year": _safe_int(row.get("year")),
                "auction_name": _safe_str(row.get("auction_name")),
                "vin": _safe_str(row.get("vin")),
                "score": _safe_str(row.get("score")),
                "created_at": None,
            }
        )

    return {
        "date": date,
        "source_filename": filename,
        "row_count": len(items),
        "updated_at": None,
        "items": items,
    }


def _safe_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        return int(value.replace(",", ""))
    except ValueError:
        return None


def _safe_str(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None
