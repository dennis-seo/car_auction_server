from typing import Optional, Tuple

from app.core.config import settings
from app.repositories.file_repo import list_auction_csv_files, resolve_csv_filepath

try:
    # Optional import; only used when enabled
    from app.repositories import firestore_repo  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    firestore_repo = None  # type: ignore


def list_available_dates() -> list[str]:
    if settings.FIRESTORE_ENABLED and firestore_repo is not None:
        try:
            return firestore_repo.list_dates()  # type: ignore[attr-defined]
        except Exception:
            # Fallback to local listing on failure
            pass
    files = list_auction_csv_files()
    dates: list[str] = []
    for name in files:
        # Expecting pattern: auction_data_YYMMDD.csv
        if name.startswith("auction_data_") and name.endswith(".csv"):
            date = name.replace("auction_data_", "").replace(".csv", "")
            if len(date) == 6 and date.isdigit():
                dates.append(date)
    dates.sort(reverse=True)
    return dates


def get_csv_path_for_date(date: str) -> Tuple[Optional[str], str]:
    filename = f"auction_data_{date}.csv"
    # When Firestore is enabled, we return (None, filename) to indicate remote fetch
    if settings.FIRESTORE_ENABLED and firestore_repo is not None:
        return None, filename
    path = resolve_csv_filepath(filename)
    return path, filename


def get_csv_content_for_date(date: str) -> Tuple[Optional[bytes], str]:
    """Fetch CSV content bytes (Firestore) or None with filename for context."""
    filename = f"auction_data_{date}.csv"
    if settings.FIRESTORE_ENABLED and firestore_repo is not None:
        try:
            res = firestore_repo.get_csv(date)  # type: ignore[attr-defined]
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
