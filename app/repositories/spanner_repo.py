from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from app.core.config import settings


logger = logging.getLogger("spanner")
_DATABASE = None
_TEMP_CRED_PATH: Optional[str] = None


def _ensure_credentials_env() -> Optional[str]:
    """Populate GOOGLE_APPLICATION_CREDENTIALS from GCP_SA_KEY when needed."""
    global _TEMP_CRED_PATH
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        return os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    key = (settings.GCP_SA_KEY or "").strip()
    if not key:
        return None

    if os.path.isfile(key):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key
        return key

    json_text: Optional[str] = None
    try:
        obj = json.loads(key)
        if isinstance(obj, dict):
            json_text = json.dumps(obj)
    except Exception:
        try:
            decoded = base64.b64decode(key)
            obj = json.loads(decoded.decode("utf-8"))
            if isinstance(obj, dict):
                json_text = json.dumps(obj)
        except Exception:
            json_text = None

    if not json_text:
        return None

    if _TEMP_CRED_PATH and os.path.isfile(_TEMP_CRED_PATH):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _TEMP_CRED_PATH
        return _TEMP_CRED_PATH

    fd, tmp_path = tempfile.mkstemp(prefix="gcp_sa_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json_text)
    _TEMP_CRED_PATH = tmp_path
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp_path
    return tmp_path


def _table_name_raw() -> str:
    table = (settings.SPANNER_TABLE or "").strip()
    if not table:
        raise RuntimeError("SPANNER_TABLE must be configured")
    return table


def _table_name_escaped() -> str:
    # Avoid SQL injection by stripping backticks
    raw = _table_name_raw().replace("`", "")
    return f"`{raw}`"


def _ensure_database():
    global _DATABASE
    if _DATABASE is not None:
        return _DATABASE

    if not settings.SPANNER_ENABLED:
        raise RuntimeError("Spanner is not enabled")

    _ensure_credentials_env()

    emulator_host = (settings.SPANNER_EMULATOR_HOST or "").strip()
    if emulator_host:
        os.environ["SPANNER_EMULATOR_HOST"] = emulator_host
        logger.info("Using Spanner emulator host=%s", emulator_host)

    project_to_use = (
        settings.SPANNER_PROJECT
        or settings.GCP_PROJECT
        or settings.GCP_PROJECT_ID
        or os.getenv("GOOGLE_CLOUD_PROJECT")
    )
    if not project_to_use:
        raise RuntimeError("SPANNER_PROJECT (or GCP_PROJECT) must be configured")

    instance_id = settings.SPANNER_INSTANCE
    database_id = settings.SPANNER_DATABASE
    table = _table_name_raw()

    if not instance_id:
        raise RuntimeError("SPANNER_INSTANCE must be configured")
    if not database_id:
        raise RuntimeError("SPANNER_DATABASE must be configured")

    try:
        from google.cloud import spanner  # type: ignore
    except Exception as exc:  # pragma: no cover - import environment dependent
        logger.exception("Failed to import google-cloud-spanner: %s", exc)
        raise RuntimeError(
            "google-cloud-spanner is not installed or import failed"
        ) from exc

    try:
        client = spanner.Client(project=project_to_use)  # type: ignore[arg-type]
        instance = client.instance(instance_id)
        database = instance.database(database_id)
        _DATABASE = database
        logger.info(
            "Spanner client ready: project=%s instance=%s database=%s table=%s",
            project_to_use,
            instance_id,
            database_id,
            table,
        )
    except Exception as exc:
        logger.exception("Failed to create Spanner client: %s", exc)
        raise

    return _DATABASE


def list_dates() -> List[str]:
    database = _ensure_database()
    table_expr = _table_name_escaped()

    query = f"SELECT date FROM {table_expr} ORDER BY date DESC"
    dates: List[str] = []
    try:
        with database.snapshot() as snapshot:
            results = snapshot.execute_sql(query)
            for row in results:
                date_value = row[0]
                if isinstance(date_value, str):
                    dates.append(date_value)
    except Exception as exc:
        logger.exception("Spanner list_dates failed: %s", exc)
        raise
    return dates


def get_csv(date: str) -> Optional[Tuple[bytes, str]]:
    database = _ensure_database()
    table_expr = _table_name_escaped()

    try:
        from google.cloud import spanner  # type: ignore
    except Exception:
        raise RuntimeError("google-cloud-spanner is not installed")

    query = f"SELECT content, filename FROM {table_expr} WHERE date = @date LIMIT 1"
    params = {"date": date}
    param_types = {"date": spanner.param_types.STRING}

    try:
        with database.snapshot() as snapshot:
            results = snapshot.execute_sql(query, params=params, param_types=param_types)
            row = next(iter(results), None)
            if row is None:
                return None
            content = row[0]
            filename = row[1] or f"auction_data_{date}.csv"
            if content is None:
                return None
            if isinstance(content, memoryview):
                content = content.tobytes()
            return bytes(content), filename
    except StopIteration:
        return None
    except Exception as exc:
        logger.exception("Spanner get_csv failed: %s", exc)
        raise


def save_csv(date: str, filename: str, content: bytes) -> None:
    database = _ensure_database()
    table = _table_name_raw()

    size_bytes = len(content)
    size_mb = round(size_bytes / 1_000_000, 3)
    now = datetime.now(timezone.utc)

    try:
        with database.batch() as batch:
            batch.insert_or_update(
                table=table,
                columns=[
                    "date",
                    "filename",
                    "size_bytes",
                    "size_mb",
                    "size_unit",
                    "content",
                    "updated_at",
                ],
                values=[
                    (
                        date,
                        filename,
                        size_bytes,
                        float(size_mb),
                        "MB",
                        content,
                        now,
                    )
                ],
            )
    except Exception as exc:
        logger.exception("Spanner save_csv failed: %s", exc)
        raise
