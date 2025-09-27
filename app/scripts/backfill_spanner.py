from __future__ import annotations

"""
Cloud Spanner backfill script from local sources directory.

Usage examples:
  - Dry run (no writes):
      python -m app.scripts.backfill_spanner --dry-run
  - Real run with overwrite disabled (default):
      python -m app.scripts.backfill_spanner
  - Overwrite existing rows in Spanner:
      python -m app.scripts.backfill_spanner --overwrite
  - Limit number of files processed:
      python -m app.scripts.backfill_spanner --limit 50

Prerequisites:
  - SPANNER_ENABLED=true in environment or .env
  - SPANNER_INSTANCE, SPANNER_DATABASE, SPANNER_ITEMS_TABLE configured
  - GCP_PROJECT (or rely on Application Default Credentials)
  - GOOGLE_APPLICATION_CREDENTIALS pointing to a valid service account JSON (when not on GCP)
"""

import argparse
import glob
import logging
import os
import sys
from typing import Iterable, Tuple


# Allow running this file directly (e.g., `python app/scripts/backfill_spanner.py`)
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
    parser = argparse.ArgumentParser(description="Backfill Spanner from local sources directory")
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
        help="Overwrite Spanner rows for the date even if they exist",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List actions without writing to Spanner",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Process at most N files (0 means no limit)",
    )
    parser.add_argument(
        "--max-size-mb",
        type=float,
        default=5.0,
        help="Skip files larger than this size in MB (default: 5.0)",
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
    logger = logging.getLogger("backfill")

    firestore_enabled = False

    # Validate backend configuration early unless dry-run
    if not args.dry_run:
        if not settings.SPANNER_ENABLED:
            logger.error("SPANNER_ENABLED is false. Enable it in .env or environment.")
            return 2
        try:
            from app.repositories import spanner_repo  # type: ignore

            try:
                spanner_repo._ensure_database()  # type: ignore[attr-defined]
            except Exception as exc:  # pragma: no cover
                logger.error("Failed to initialize Spanner client: %s", exc)
                return 2
        except Exception as exc:  # pragma: no cover
            logger.error("Failed to import Spanner repo or dependency: %s", exc)
            return 2

        if settings.FIRESTORE_ENABLED:
            try:
                from app.repositories import firestore_repo  # type: ignore

                firestore_repo._ensure_client()  # type: ignore[attr-defined]
                firestore_enabled = True
            except Exception as exc:  # pragma: no cover
                logger.error("Failed to initialize Firestore client: %s", exc)
                return 2
    else:
        spanner_repo = None  # type: ignore

    directory = args.dir
    pattern = args.pattern
    if not os.path.isdir(directory):
        logger.error("Directory not found: %s", directory)
        return 1

    processed = 0
    skipped_exists = 0
    skipped_badname = 0
    skipped_large = 0
    uploaded = 0
    fs_uploaded = 0
    fs_skipped_exists = 0

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
        size_mb = size_bytes / 1_000_000
        if args.max_size_mb and size_mb > args.max_size_mb:
            logger.warning(
                "Skip (too large %.3f MB > %.3f MB): %s",
                size_mb,
                args.max_size_mb,
                os.path.basename(path),
            )
            skipped_large += 1
            continue

        logger.info(
            "%s -> row=%s size=%.3f MB%s",
            os.path.basename(path),
            target_date,
            size_mb,
            " [overwrite]" if args.overwrite else "",
        )

        if args.dry_run:
            continue

        from app.repositories import spanner_repo  # type: ignore
        firestore_repo = None
        if firestore_enabled:
            from app.repositories import firestore_repo as _firestore_repo  # type: ignore

            firestore_repo = _firestore_repo

        spanner_should_upload = True
        firestore_should_upload = firestore_repo is not None

        if not args.overwrite:
            try:
                exists = spanner_repo.get_csv(target_date)  # type: ignore[attr-defined]
            except Exception:
                exists = None
            if exists is not None:
                spanner_should_upload = False
                skipped_exists += 1
                logger.info("Skip (exists): row=%s", target_date)

            if firestore_repo is not None:
                try:
                    exists_fs = firestore_repo.get_csv(target_date)  # type: ignore[attr-defined]
                except Exception:
                    exists_fs = None
                if exists_fs is not None:
                    firestore_should_upload = False
                    fs_skipped_exists += 1
                    logger.info("Skip Firestore (exists): row=%s", target_date)

        if not spanner_should_upload and not firestore_should_upload:
            continue

        try:
            with open(path, "rb") as f:
                content = f.read()
            filename = os.path.basename(path)

            if spanner_should_upload:
                spanner_repo.save_csv(target_date, filename, content)  # type: ignore[attr-defined]
                uploaded += 1

            if firestore_should_upload and firestore_repo is not None:
                try:
                    firestore_repo.save_csv(target_date, filename, content)  # type: ignore[attr-defined]
                    fs_uploaded += 1
                except Exception as exc:
                    logger.error("Firestore upload failed for %s: %s", os.path.basename(path), exc)
        except Exception as exc:
            logger.error("Upload failed for %s: %s", os.path.basename(path), exc)

    logger.info(
        "Done. processed=%d, uploaded=%d, skipped_exists=%d, skipped_badname=%d, skipped_large=%d, firestore_uploaded=%d, firestore_skipped=%d",
        processed,
        uploaded,
        skipped_exists,
        skipped_badname,
        skipped_large,
        fs_uploaded,
        fs_skipped_exists,
    )
    if not args.dry_run and uploaded == 0:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
