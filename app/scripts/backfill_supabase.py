from __future__ import annotations

"""
Supabase backfill script from local sources directory.

Usage examples:
  - Dry run (no writes):
      python -m app.scripts.backfill_supabase --dry-run
  - Real run with overwrite disabled (default):
      python -m app.scripts.backfill_supabase
  - Overwrite existing rows in Supabase:
      python -m app.scripts.backfill_supabase --overwrite
  - Limit number of files processed:
      python -m app.scripts.backfill_supabase --limit 50
  - Backfill only auction_records table:
      python -m app.scripts.backfill_supabase --target records --overwrite
  - Backfill only auction_data table:
      python -m app.scripts.backfill_supabase --target data --overwrite
  - Backfill both tables (default):
      python -m app.scripts.backfill_supabase --target both --overwrite

Prerequisites:
  - SUPABASE_ENABLED=true in environment or .env
  - SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_TABLE configured
  - (Optional) SUPABASE_HISTORY_TABLE if you append to a history table
"""

import argparse
import glob
import logging
import os
import sys
from typing import Iterable, Tuple


# Allow running this file directly (e.g., `python app/scripts/backfill_supabase.py`)
if __package__ is None or __package__ == "":
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))

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
    ok = len(date_part) == 6 and date_part.isdigit()
    return date_part, ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill Supabase from local sources directory")
    parser.add_argument(
        "--dir",
        default=settings.SOURCES_DIR,
        help=f"Directory containing CSV files (default: {settings.SOURCES_DIR})",
    )
    parser.add_argument(
        "--pattern",
        default="auction_data_*.csv",
        help="Glob pattern for input files (default: auction_data_*.csv)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite Supabase row even if it exists",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List actions without writing to Supabase",
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
    parser.add_argument(
        "--target",
        default="both",
        choices=["data", "records", "both"],
        help="Target table(s): data=auction_data, records=auction_records, both=both tables (default: both)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logger = logging.getLogger("backfill")

    # Determine which tables to backfill
    backfill_data = args.target in ("data", "both")
    backfill_records = args.target in ("records", "both")

    # Validate Supabase configuration early unless dry-run
    supabase_repo = None  # type: ignore
    auction_records_repo = None  # type: ignore

    if not args.dry_run:
        if not settings.SUPABASE_ENABLED:
            logger.error("SUPABASE_ENABLED is false. Enable it in .env or environment.")
            return 2

        if backfill_data:
            try:
                from app.repositories import supabase_repo  # type: ignore

                # Probe client initialization early to fail fast on config errors
                try:
                    supabase_repo.list_dates()  # type: ignore[attr-defined]
                except Exception as exc:  # pragma: no cover - environment dependent
                    logger.error("Failed to initialize Supabase client: %s", exc)
                    return 2
            except Exception as exc:  # pragma: no cover - optional dep import
                logger.error("Failed to import Supabase repo or dependency: %s", exc)
                return 2

        if backfill_records:
            try:
                from app.repositories import auction_records_repo  # type: ignore

                # Probe client initialization early to fail fast on config errors
                try:
                    auction_records_repo.list_dates()  # type: ignore[attr-defined]
                except Exception as exc:  # pragma: no cover - environment dependent
                    logger.error("Failed to initialize auction_records_repo: %s", exc)
                    return 2
            except Exception as exc:  # pragma: no cover - optional dep import
                logger.error("Failed to import auction_records_repo: %s", exc)
                return 2

    directory = args.dir
    pattern = args.pattern
    if not os.path.isdir(directory):
        logger.error("Directory not found: %s", directory)
        return 1

    processed = 0
    skipped_exists = 0
    skipped_badname = 0
    uploaded = 0

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

        # Show what would happen
        logger.info(
            "%s -> row=%s size=%.3f MB%s",
            os.path.basename(path),
            target_date,
            size_bytes / 1_000_000,
            " [overwrite]" if args.overwrite else "",
        )

        if args.dry_run:
            continue

        # Read file content
        try:
            with open(path, "rb") as f:
                content = f.read()
            filename = os.path.basename(path)
        except Exception as exc:
            logger.error("Failed to read file %s: %s", os.path.basename(path), exc)
            continue

        # Upload to auction_data table
        if backfill_data and supabase_repo is not None:
            # If not overwriting, check existence
            if not args.overwrite:
                try:
                    exists = supabase_repo.get_csv(target_date)  # type: ignore[attr-defined]
                except Exception:
                    exists = None
                if exists is not None:
                    logger.info("Skip auction_data (exists): row=%s", target_date)
                else:
                    try:
                        supabase_repo.save_csv(target_date, filename, content)  # type: ignore[attr-defined]
                        logger.info("Uploaded to auction_data: %s", target_date)
                    except Exception as exc:
                        logger.error("auction_data upload failed for %s: %s", os.path.basename(path), exc)
            else:
                try:
                    supabase_repo.save_csv(target_date, filename, content)  # type: ignore[attr-defined]
                    logger.info("Uploaded to auction_data: %s", target_date)
                except Exception as exc:
                    logger.error("auction_data upload failed for %s: %s", os.path.basename(path), exc)

        # Upload to auction_records table
        if backfill_records and auction_records_repo is not None:
            # If not overwriting, check existence
            if not args.overwrite:
                try:
                    exists = auction_records_repo.get_records_by_date(target_date)  # type: ignore[attr-defined]
                except Exception:
                    exists = []
                if exists:
                    logger.info("Skip auction_records (exists): row=%s", target_date)
                else:
                    try:
                        count = auction_records_repo.save_csv(target_date, filename, content)  # type: ignore[attr-defined]
                        logger.info("Uploaded to auction_records: %s (%d records)", target_date, count)
                    except Exception as exc:
                        logger.error("auction_records upload failed for %s: %s", os.path.basename(path), exc)
            else:
                try:
                    count = auction_records_repo.save_csv(target_date, filename, content)  # type: ignore[attr-defined]
                    logger.info("Uploaded to auction_records: %s (%d records)", target_date, count)
                except Exception as exc:
                    logger.error("auction_records upload failed for %s: %s", os.path.basename(path), exc)

        uploaded += 1

    logger.info(
        "Done. processed=%d, uploaded=%d, skipped_exists=%d, skipped_badname=%d",
        processed,
        uploaded,
        skipped_exists,
        skipped_badname,
    )
    # Non-zero exit code if nothing uploaded and not dry-run
    if not args.dry_run and uploaded == 0:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
