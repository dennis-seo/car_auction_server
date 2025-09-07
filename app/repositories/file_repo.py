import os
from typing import List, Optional

from app.core.config import settings


def list_auction_csv_files() -> List[str]:
    try:
        return os.listdir(settings.SOURCES_DIR)
    except FileNotFoundError:
        return []


def resolve_csv_filepath(filename: str) -> Optional[str]:
    path = os.path.join(settings.SOURCES_DIR, filename)
    if os.path.exists(path):
        return path
    return None

