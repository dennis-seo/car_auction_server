from typing import Optional, Tuple

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
        try:
            return spanner_repo.list_dates()  # type: ignore[attr-defined]
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
