"""
auction_records 테이블 백필 스크립트

기존 sources/ 디렉토리의 CSV 파일을 새 auction_records 테이블로 마이그레이션합니다.

Usage examples:
  - Dry run (no writes):
      python -m app.scripts.backfill_auction_records --dry-run

  - Real run with overwrite disabled (default):
      python -m app.scripts.backfill_auction_records

  - Overwrite existing rows:
      python -m app.scripts.backfill_auction_records --overwrite

  - Limit number of files processed:
      python -m app.scripts.backfill_auction_records --limit 10

  - Specific directory:
      python -m app.scripts.backfill_auction_records --dir sources

Prerequisites:
  - SUPABASE_ENABLED=true in environment or .env
  - SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY configured
  - auction_records 테이블이 Supabase에 생성되어 있어야 함
"""

from __future__ import annotations

import argparse
import glob
import logging
import os
import sys
from typing import Iterable, Tuple


# Allow running this file directly
if __package__ is None or __package__ == "":
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.core.config import settings
from app.utils.bizdate import next_business_day


def _iter_source_files(directory: str, pattern: str) -> Iterable[str]:
    """Yield matching file paths sorted by filename ascending for determinism."""
    glob_pattern = os.path.join(directory, pattern)
    files = sorted(glob.glob(glob_pattern))
    for path in files:
        if os.path.isfile(path):
            yield path


def _extract_src_date(filename: str) -> Tuple[str, bool]:
    """Extract source date (YYMMDD) from filename 'auction_data_YYMMDD.csv'.

    Returns (date_str, ok).
    """
    base = os.path.basename(filename)
    if not base.startswith("auction_data_") or not base.endswith(".csv"):
        return "", False
    date_part = base[len("auction_data_") : -len(".csv")]
    # Handle space in filename like "auction_data 250911.csv"
    date_part = date_part.replace(" ", "")
    ok = len(date_part) == 6 and date_part.isdigit()
    return date_part, ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill auction_records table from local sources directory"
    )
    parser.add_argument(
        "--dir",
        default=settings.SOURCES_DIR,
        help=f"Directory containing CSV files (default: {settings.SOURCES_DIR})",
    )
    parser.add_argument(
        "--pattern",
        default="auction_data*.csv",
        help="Glob pattern for input files (default: auction_data*.csv)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing rows even if they exist",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List actions without writing to database",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process at most N files (0 means no limit)",
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
    logger = logging.getLogger("backfill_auction_records")

    # Validate configuration
    if not args.dry_run:
        if not settings.SUPABASE_ENABLED:
            logger.error("SUPABASE_ENABLED is false. Enable it in .env or environment.")
            return 2
        try:
            from app.repositories import auction_records_repo

            # Test connection
            try:
                auction_records_repo.list_dates()
            except Exception as exc:
                logger.error("Failed to initialize auction_records_repo: %s", exc)
                return 2
        except Exception as exc:
            logger.error("Failed to import auction_records_repo: %s", exc)
            return 2
    else:
        auction_records_repo = None  # type: ignore

    directory = args.dir
    pattern = args.pattern
    if not os.path.isdir(directory):
        logger.error("Directory not found: %s", directory)
        return 1

    processed = 0
    skipped_exists = 0
    skipped_badname = 0
    uploaded = 0
    total_records = 0

    for path in _iter_source_files(directory, pattern):
        if args.limit and processed >= args.limit:
            break
        processed += 1

        src_date, ok = _extract_src_date(path)
        if not ok:
            logger.warning("Skip (name pattern mismatch): %s", os.path.basename(path))
            skipped_badname += 1
            continue

        try:
            target_date = next_business_day(src_date)
        except Exception as exc:
            logger.warning("Skip (invalid date: %s): %s", exc, os.path.basename(path))
            skipped_badname += 1
            continue

        size_bytes = os.path.getsize(path)

        logger.info(
            "%s -> date=%s size=%.3f MB%s",
            os.path.basename(path),
            target_date,
            size_bytes / 1_000_000,
            " [overwrite]" if args.overwrite else "",
        )

        if args.dry_run:
            continue

        from app.repositories import auction_records_repo

        # Check if data exists for this date
        if not args.overwrite:
            try:
                existing = auction_records_repo.get_records_by_date(target_date)
                if existing:
                    skipped_exists += 1
                    logger.info("Skip (exists): date=%s (%d records)", target_date, len(existing))
                    continue
            except Exception:
                pass  # Proceed with upload

        # Upload
        try:
            with open(path, "rb") as f:
                content = f.read()
            filename = os.path.basename(path)
            record_count = auction_records_repo.save_csv(target_date, filename, content)
            uploaded += 1
            total_records += record_count
            logger.info("Uploaded: date=%s, records=%d", target_date, record_count)
        except Exception as exc:
            logger.error("Upload failed for %s: %s", os.path.basename(path), exc)

    logger.info(
        "Done. processed=%d, uploaded=%d, total_records=%d, skipped_exists=%d, skipped_badname=%d",
        processed,
        uploaded,
        total_records,
        skipped_exists,
        skipped_badname,
    )

    if not args.dry_run and uploaded == 0:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
