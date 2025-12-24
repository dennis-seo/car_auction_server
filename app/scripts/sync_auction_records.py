"""
auction_data 테이블에서 auction_records 테이블로 동기화하는 스크립트

auction_data에는 있지만 auction_records에는 없는 데이터를 백필합니다.

Usage:
  # Dry run (확인만)
  python -m app.scripts.sync_auction_records --dry-run

  # 실제 실행
  python -m app.scripts.sync_auction_records

  # 특정 날짜 범위만 실행 (YYMMDD 형식)
  python -m app.scripts.sync_auction_records --from 251216 --to 251224

  # 강제 덮어쓰기
  python -m app.scripts.sync_auction_records --overwrite
"""

from __future__ import annotations

import argparse
import logging
import sys
import os

# Allow running this file directly
if __package__ is None or __package__ == "":
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.core.config import settings
from app.utils.bizdate import yymmdd_to_iso, iso_to_yymmdd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync auction_data to auction_records table"
    )
    parser.add_argument(
        "--from",
        dest="date_from",
        help="Start date (YYMMDD format, e.g., 251216)",
    )
    parser.add_argument(
        "--to",
        dest="date_to",
        help="End date (YYMMDD format, e.g., 251224)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing records in auction_records",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logger = logging.getLogger("sync_auction_records")

    # Validate configuration
    if not settings.SUPABASE_ENABLED:
        logger.error("SUPABASE_ENABLED is false. Enable it in .env or environment.")
        return 2

    try:
        from app.repositories import supabase_repo
        from app.repositories import auction_records_repo
    except Exception as exc:
        logger.error("Failed to import repositories: %s", exc)
        return 2

    # Get all dates from auction_data
    try:
        all_dates = supabase_repo.list_dates()
        logger.info("Found %d dates in auction_data", len(all_dates))
    except Exception as exc:
        logger.error("Failed to list dates from auction_data: %s", exc)
        return 2

    # Filter by date range if specified
    if args.date_from or args.date_to:
        filtered_dates = []
        date_from_iso = yymmdd_to_iso(args.date_from) if args.date_from else None
        date_to_iso = yymmdd_to_iso(args.date_to) if args.date_to else None

        for date in all_dates:
            # date is in YYMMDD format from supabase_repo.list_dates()
            date_iso = yymmdd_to_iso(date)
            if date_from_iso and date_iso < date_from_iso:
                continue
            if date_to_iso and date_iso > date_to_iso:
                continue
            filtered_dates.append(date)

        all_dates = filtered_dates
        logger.info("Filtered to %d dates in range", len(all_dates))

    # Process each date
    synced = 0
    skipped = 0
    errors = 0

    for date in sorted(all_dates):
        # Check if already exists in auction_records
        if not args.overwrite:
            try:
                if auction_records_repo.exists(date):
                    logger.debug("Skip (exists): %s", date)
                    skipped += 1
                    continue
            except Exception:
                pass  # Proceed with sync

        # Get CSV content from auction_data
        try:
            result = supabase_repo.get_csv(date)
            if result is None:
                logger.warning("No content found in auction_data for date=%s", date)
                skipped += 1
                continue
            content, filename = result
        except Exception as exc:
            logger.error("Failed to get CSV for date=%s: %s", date, exc)
            errors += 1
            continue

        if args.dry_run:
            logger.info("[DRY-RUN] Would sync: date=%s, filename=%s, size=%d bytes",
                       date, filename, len(content))
            synced += 1
            continue

        # Save to auction_records
        try:
            record_count = auction_records_repo.save_csv(date, filename, content)
            logger.info("Synced: date=%s, records=%d", date, record_count)
            synced += 1
        except Exception as exc:
            logger.error("Failed to save to auction_records for date=%s: %s", date, exc)
            errors += 1

    logger.info(
        "Done. synced=%d, skipped=%d, errors=%d",
        synced, skipped, errors
    )

    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
