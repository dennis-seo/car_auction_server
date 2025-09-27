from __future__ import annotations

import csv
import io
import json
import logging
import os
import tempfile
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.core.config import settings


logger = logging.getLogger("spanner_repo")
_CLIENT = None
_DATABASE = None
_TEMP_CRED_PATH: Optional[str] = None

_ITEM_COLUMNS = (
    "date",
    "row_order",
    "sell_number",
    "car_number",
    "post_title",
    "title",
    "color",
    "fuel",
    "image",
    "km",
    "price",
    "trans",
    "year",
    "auction_name",
    "vin",
    "score",
    "created_at",
)

_HEADER_ORDER = [
    "Post Title",
    "sell_number",
    "car_number",
    "color",
    "fuel",
    "image",
    "km",
    "price",
    "title",
    "trans",
    "year",
    "auction_name",
    "vin",
    "score",
]

_FIELD_MAP = {
    "Post Title": "post_title",
    "sell_number": "sell_number",
    "car_number": "car_number",
    "color": "color",
    "fuel": "fuel",
    "image": "image",
    "km": "km",
    "price": "price",
    "title": "title",
    "trans": "trans",
    "year": "year",
    "auction_name": "auction_name",
    "vin": "vin",
    "score": "score",
}


def _running_on_gcp() -> bool:
    env = os.environ
    return bool(
        env.get("K_SERVICE")
        or env.get("GOOGLE_CLOUD_PROJECT")
        or env.get("GAE_ENV")
    )


def _ensure_database():
    global _CLIENT, _DATABASE
    if _DATABASE is not None:
        return _DATABASE
    if not settings.SPANNER_ENABLED:
        raise RuntimeError("Spanner is not enabled")

    if not settings.SPANNER_INSTANCE or not settings.SPANNER_DATABASE:
        raise RuntimeError("SPANNER_INSTANCE or SPANNER_DATABASE not configured")

    _ensure_credentials_env()

    project_hint = settings.GCP_PROJECT or settings.GCP_PROJECT_ID or "<auto>"
    instance_id = settings.SPANNER_INSTANCE
    database_id = settings.SPANNER_DATABASE
    on_gcp = _running_on_gcp()

    logger.info(
        "Initializing Spanner: enabled=%s, project=%s, instance=%s, database=%s, on_gcp=%s",
        settings.SPANNER_ENABLED,
        project_hint,
        instance_id,
        database_id,
        on_gcp,
    )

    try:
        from google.cloud import spanner  # type: ignore
    except Exception as exc:  # pragma: no cover
        logger.exception("Failed to import google-cloud-spanner: %s", exc)
        raise RuntimeError("google-cloud-spanner is not installed or import failed") from exc

    try:
        restore_env = None
        cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if on_gcp and cred_path:
            restore_env = cred_path
            try:
                del os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
                logger.info("Ignoring GOOGLE_APPLICATION_CREDENTIALS on GCP to use ADC")
            except KeyError:
                restore_env = None

        try:
            project_to_use = settings.GCP_PROJECT or settings.GCP_PROJECT_ID
            _CLIENT = spanner.Client(project=project_to_use) if project_to_use else spanner.Client()
            instance = _CLIENT.instance(instance_id)
            _DATABASE = instance.database(database_id)
        finally:
            if restore_env is not None:
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = restore_env

        logger.info(
            "Spanner client ready. project=%s instance=%s database=%s",
            getattr(_CLIENT, "project", None),
            instance_id,
            database_id,
        )
    except Exception as exc:
        logger.exception("Failed to create Spanner client/database: %s", exc)
        raise
    return _DATABASE


def save_csv(date: str, filename: str, content: bytes) -> int:
    database = _ensure_database()
    rows = _parse_csv_rows(content)
    row_count = len(rows)

    if row_count == 0:
        logger.warning("No rows parsed from CSV for date=%s filename=%s", date, filename)

    from google.cloud import spanner  # type: ignore

    with database.batch() as batch:
        # Use a range so older google-cloud-spanner versions (no prefixes arg) delete the whole date partition.
        keyset = spanner.KeySet(
            ranges=[
                spanner.KeyRange(
                    start_closed=(date,),
                    end_open=(date + "\uffff",),
                )
            ]
        )
        batch.delete(settings.SPANNER_ITEMS_TABLE, keyset)

        for chunk in _chunked(rows, 200):
            values = [
                (
                    date,
                    item["row_order"],
                    item.get("sell_number"),
                    item.get("car_number"),
                    item.get("post_title"),
                    item.get("title"),
                    item.get("color"),
                    item.get("fuel"),
                    item.get("image"),
                    item.get("km"),
                    item.get("price"),
                    item.get("trans"),
                    item.get("year"),
                    item.get("auction_name"),
                    item.get("vin"),
                    item.get("score"),
                    spanner.COMMIT_TIMESTAMP,
                )
                for item in chunk
            ]
            batch.insert_or_update(
                table=settings.SPANNER_ITEMS_TABLE,
                columns=_ITEM_COLUMNS,
                values=values,
            )

        batch.insert_or_update(
            table=settings.SPANNER_METADATA_TABLE,
            columns=(
                "date",
                "source_filename",
                "row_count",
                "updated_at",
            ),
            values=[
                (
                    date,
                    filename,
                    row_count,
                    spanner.COMMIT_TIMESTAMP,
                )
            ],
        )

    logger.info(
        "Saved %d rows to Spanner (date=%s, filename=%s)",
        row_count,
        date,
        filename,
    )
    return row_count


def list_dates() -> List[str]:
    database = _ensure_database()
    query = f"SELECT date FROM {settings.SPANNER_METADATA_TABLE} ORDER BY date DESC"
    dates: List[str] = []
    with database.snapshot() as snapshot:
        results = snapshot.execute_sql(query)
        for row in results:
            value = row[0]
            if isinstance(value, bytes):
                try:
                    value = value.decode("utf-8")
                except Exception:
                    continue
            if isinstance(value, str):
                dates.append(value)
    return dates


def get_csv(date: str) -> Optional[Tuple[bytes, str]]:
    database = _ensure_database()
    params = {"date": date}
    param_types = {"date": _spanner_param_string()}

    # Fetch metadata for filename hint
    metadata_query = (
        f"SELECT source_filename FROM {settings.SPANNER_METADATA_TABLE} "
        "WHERE date = @date"
    )
    filename_hint: Optional[str] = None
    with database.snapshot() as snapshot:
        meta_rows = list(
            snapshot.execute_sql(metadata_query, params=params, param_types=param_types)
        )
        if not meta_rows:
            return None
        filename_value = meta_rows[0][0]
        if isinstance(filename_value, bytes):
            try:
                filename_hint = filename_value.decode("utf-8")
            except Exception:
                filename_hint = None
        elif isinstance(filename_value, str):
            filename_hint = filename_value

        columns = (
            "sell_number",
            "car_number",
            "post_title",
            "title",
            "color",
            "fuel",
            "image",
            "km",
            "price",
            "trans",
            "year",
            "auction_name",
            "vin",
            "score",
        )
        select_list = ", ".join(columns)
        items_query = (
            f"SELECT {select_list} FROM {settings.SPANNER_ITEMS_TABLE} "
            "WHERE date = @date ORDER BY row_order"
        )
        rows = list(
            snapshot.execute_sql(items_query, params=params, param_types=param_types)
        )

    if not rows:
        return None

    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(_HEADER_ORDER)

    for row in rows:
        record = _row_to_csv_values(row)
        writer.writerow(record)

    filename = filename_hint or f"auction_data_{date}.csv"
    return output.getvalue().encode("utf-8"), filename


def _row_to_csv_values(row: Sequence[Any]) -> List[str]:
    sell_number,
    car_number,
    post_title,
    title,
    color,
    fuel,
    image,
    km,
    price,
    trans,
    year,
    auction_name,
    vin,
    score = row

    def _fmt(value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    return [
        _fmt(post_title),
        _fmt(sell_number),
        _fmt(car_number),
        _fmt(color),
        _fmt(fuel),
        _fmt(image),
        _fmt(km),
        _fmt(price),
        _fmt(title),
        _fmt(trans),
        _fmt(year),
        _fmt(auction_name),
        _fmt(vin),
        _fmt(score),
    ]


def _parse_csv_rows(content: bytes) -> List[Dict[str, Any]]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows: List[Dict[str, Any]] = []
    row_order = 0
    for raw in reader:
        if not raw:
            continue
        row_order += 1
        normalized = _normalize_row(raw)
        normalized["row_order"] = row_order
        rows.append(normalized)
    return rows


def _normalize_row(raw: Dict[str, Any]) -> Dict[str, Any]:
    def _to_int(value: Optional[str]) -> Optional[int]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        try:
            return int(value.replace(",", ""))
        except ValueError:
            return None

    normalized: Dict[str, Any] = {}
    for header, key in _FIELD_MAP.items():
        value = raw.get(header)
        if isinstance(value, str):
            normalized[key] = value.strip()
        else:
            normalized[key] = value

    normalized["sell_number"] = _to_int(raw.get("sell_number"))
    normalized["km"] = _to_int(raw.get("km"))
    normalized["price"] = _to_int(raw.get("price"))
    normalized["year"] = _to_int(raw.get("year"))

    # Ensure string fields are at least empty string instead of None for CSV compatibility
    for field in ("post_title", "title", "color", "fuel", "image", "trans", "auction_name", "vin", "score", "car_number"):
        value = normalized.get(field)
        if value is None:
            normalized[field] = ""
        elif isinstance(value, str):
            normalized[field] = value.strip()

    return normalized


def _chunked(items: Sequence[Dict[str, Any]], size: int) -> Iterable[Sequence[Dict[str, Any]]]:
    for idx in range(0, len(items), size):
        yield items[idx : idx + size]


def _spanner_param_string():
    from google.cloud import spanner  # type: ignore

    return spanner.param_types.STRING


def _ensure_credentials_env() -> Optional[str]:
    global _TEMP_CRED_PATH
    existing = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if existing:
        return existing

    path_hint = getattr(settings, "GOOGLE_APPLICATION_CREDENTIALS", "") or ""
    path_hint = path_hint.strip()
    if path_hint:
        expanded = os.path.expanduser(path_hint)
        if os.path.isfile(expanded):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = expanded
            return expanded

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
            import base64

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
    with os.fdopen(fd, "w", encoding="utf-8") as fp:
        fp.write(json_text)
    _TEMP_CRED_PATH = tmp_path
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp_path
    return tmp_path
