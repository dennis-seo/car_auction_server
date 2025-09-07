from typing import Optional, Tuple

from app.repositories.file_repo import list_auction_csv_files, resolve_csv_filepath


def list_available_dates() -> list[str]:
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
    path = resolve_csv_filepath(filename)
    return path, filename

