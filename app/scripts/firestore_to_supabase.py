from __future__ import annotations

import argparse
import base64
import logging
import os
import sys
from contextlib import contextmanager
from typing import Optional

# Allow running this file directly (e.g., `python app/scripts/firestore_to_supabase.py`)
if __package__ is None or __package__ == "":
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.core.config import settings
from app.repositories import supabase_repo  # type: ignore


logger = logging.getLogger("firestore_to_supabase")


def _decode_content(value) -> Optional[bytes]:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    if isinstance(value, str):
        try:
            return base64.b64decode(value, validate=True)
        except Exception:
            return value.encode("utf-8")
    if isinstance(value, dict):
        for key in ("bytes", "bytesValue", "content"):
            if key in value:
                return _decode_content(value[key])
    return None


@contextmanager
def _override_tables(table: Optional[str], history_table: Optional[str]):
    orig_table = settings.SUPABASE_TABLE
    orig_history = settings.SUPABASE_HISTORY_TABLE
    if table:
        settings.SUPABASE_TABLE = table
    if history_table is not None:
        settings.SUPABASE_HISTORY_TABLE = history_table
    try:
        yield
    finally:
        settings.SUPABASE_TABLE = orig_table
        settings.SUPABASE_HISTORY_TABLE = orig_history


def _ensure_google_credentials() -> None:
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        return
    cred_path = (settings.GOOGLE_APPLICATION_CREDENTIALS or "").strip()
    if cred_path:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path


def migrate(
    collection: str,
    *,
    firestore_project: Optional[str],
    content_field: str,
    filename_field: str,
    date_field: str,
    filename_prefix: str,
    filename_ext: str,
    limit: int,
    skip_existing: bool,
    dry_run: bool,
    target_table: Optional[str],
    target_history_table: Optional[str],
):
    if not settings.SUPABASE_ENABLED:
        raise RuntimeError("SUPABASE_ENABLED must be true")

    _ensure_google_credentials()

    from google.cloud import firestore  # type: ignore

    client = firestore.Client(project=firestore_project)
    docs = client.collection(collection).stream()

    processed = 0
    uploaded = 0
    skipped_exists = 0
    skipped_missing = 0

    with _override_tables(target_table, target_history_table):
        for doc in docs:
            if limit and processed >= limit:
                break
            processed += 1
            data = doc.to_dict() or {}

            date_value = data.get(date_field)
            if not isinstance(date_value, str) or not date_value:
                logger.warning("Skip doc=%s (missing %s)", doc.id, date_field)
                skipped_missing += 1
                continue

            filename = data.get(filename_field)
            if not isinstance(filename, str) or not filename:
                filename = f"{filename_prefix}{date_value}.{filename_ext}"

            content_raw = data.get(content_field)
            content = _decode_content(content_raw)
            if content is None:
                logger.warning("Skip doc=%s (missing %s)", doc.id, content_field)
                skipped_missing += 1
                continue

            if skip_existing and not dry_run:
                try:
                    exists = supabase_repo.get_csv(date_value)  # type: ignore[attr-defined]
                except Exception:
                    exists = None
                if exists is not None:
                    skipped_exists += 1
                    logger.info("Skip (exists) doc=%s date=%s", doc.id, date_value)
                    continue

            logger.info(
                "%s -> date=%s filename=%s size=%.3f MB",
                doc.id,
                date_value,
                filename,
                len(content) / 1_000_000,
            )

            if dry_run:
                continue

            supabase_repo.save_csv(date_value, filename, content)  # type: ignore[attr-defined]
            uploaded += 1

    logger.info(
        "Done. processed=%d uploaded=%d skipped_exists=%d skipped_missing=%d",
        processed,
        uploaded,
        skipped_exists,
        skipped_missing,
    )
    return uploaded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Copy Firestore CSV documents into Supabase tables")
    parser.add_argument("--collection", default="auction_data", help="Firestore collection name")
    parser.add_argument("--firestore-project", default=None, help="Override Firestore project id")
    parser.add_argument("--content-field", default="content", help="Field name for CSV blob")
    parser.add_argument("--filename-field", default="filename", help="Field name for filename")
    parser.add_argument("--date-field", default="date", help="Field name for YYMMDD/row id")
    parser.add_argument("--filename-prefix", default="auction_data_", help="Filename prefix fallback")
    parser.add_argument("--filename-ext", default="csv", help="Filename extension fallback")
    parser.add_argument("--limit", type=int, default=0, help="Process at most N docs (0=no limit)")
    parser.add_argument("--skip-existing", action="store_true", help="Do not overwrite existing Supabase rows")
    parser.add_argument("--dry-run", action="store_true", help="Log actions without writing to Supabase")
    parser.add_argument("--target-table", default=None, help="Override SUPABASE_TABLE during this run")
    parser.add_argument(
        "--target-history-table",
        default=None,
        help="Override SUPABASE_HISTORY_TABLE (use empty string to disable history writes)",
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    try:
        migrate(
            args.collection,
            firestore_project=args.firestore_project,
            content_field=args.content_field,
            filename_field=args.filename_field,
            date_field=args.date_field,
            filename_prefix=args.filename_prefix,
            filename_ext=args.filename_ext,
            limit=args.limit,
            skip_existing=args.skip_existing,
            dry_run=args.dry_run,
            target_table=args.target_table,
            target_history_table=args.target_history_table,
        )
        return 0
    except Exception as exc:
        logger.exception("Migration failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
