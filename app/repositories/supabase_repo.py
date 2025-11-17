from __future__ import annotations

import csv
import io
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple

import requests

from app.core.config import settings


logger = logging.getLogger("supabase")
_SESSION: Optional[requests.Session] = None


CSV_FIELDS: List[Tuple[str, str]] = [
    ("Post Title", "post_title"),
    ("sell_number", "sell_number"),
    ("car_number", "car_number"),
    ("color", "color"),
    ("fuel", "fuel"),
    ("image", "image"),
    ("km", "km"),
    ("price", "price"),
    ("title", "title"),
    ("trans", "trans"),
    ("year", "year"),
    ("auction_name", "auction_name"),
    ("vin", "vin"),
    ("score", "score"),
]


def _require_enabled() -> None:
    if not settings.SUPABASE_ENABLED:
        raise RuntimeError("Supabase integration is disabled")


def _base_url() -> str:
    url = (settings.SUPABASE_URL or "").strip().rstrip("/")
    if not url:
        raise RuntimeError("SUPABASE_URL must be configured")
    return url


def _table_name() -> str:
    table = (settings.SUPABASE_TABLE or "").strip()
    if not table:
        raise RuntimeError("SUPABASE_TABLE must be configured")
    return table


def _history_table_name() -> Optional[str]:
    table = (settings.SUPABASE_HISTORY_TABLE or "").strip()
    return table or None


def _read_key() -> str:
    key = (settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY or "").strip()
    if not key:
        raise RuntimeError("Supabase API key is not configured")
    return key


def _service_key() -> str:
    key = (settings.SUPABASE_SERVICE_ROLE_KEY or "").strip()
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY must be configured for write operations")
    return key


def _session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
    return _SESSION


def _rest_headers(use_service: bool = False, extra: Optional[Dict[str, str]] = None, json_body: bool = False) -> Dict[str, str]:
    key = _service_key() if use_service else _read_key()
    headers: Dict[str, str] = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
    if json_body:
        headers["Content-Type"] = "application/json"
    if extra:
        headers.update(extra)
    return headers


def _delete_existing(date: str) -> None:
    session = _session()
    url = f"{_base_url()}/rest/v1/{_table_name()}"
    params = {"date": f"eq.{date}"}
    headers = _rest_headers(use_service=True, extra={"Prefer": "count=exact"})
    resp = session.delete(url, headers=headers, params=params, timeout=30)
    if resp.status_code not in (200, 204):
        logger.error("Supabase delete failed (status=%s): %s", resp.status_code, resp.text)
        resp.raise_for_status()


def _chunk(iterable: List[Dict[str, object]], size: int) -> Iterable[List[Dict[str, object]]]:
    for i in range(0, len(iterable), size):
        yield iterable[i : i + size]


def list_dates() -> List[str]:
    _require_enabled()
    session = _session()
    url = f"{_base_url()}/rest/v1/{_table_name()}"
    params = {
        "select": "date",
        "order": "date.desc",
    }
    resp = session.get(url, headers=_rest_headers(), params=params, timeout=20)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    payload = resp.json()
    seen: set[str] = set()
    dates: List[str] = []
    if isinstance(payload, list):
        for row in payload:
            if not isinstance(row, dict):
                continue
            value = row.get("date")
            if isinstance(value, str) and value not in seen:
                seen.add(value)
                dates.append(value)
    return dates


def _fetch_rows(date: str) -> List[Dict[str, object]]:
    session = _session()
    url = f"{_base_url()}/rest/v1/{_table_name()}"
    select_cols = ["row_index", "date", "source_filename", "filename"] + [field for _, field in CSV_FIELDS]
    params = {
        "select": ",".join(select_cols),
        "date": f"eq.{date}",
        "order": "row_index.asc",
    }
    resp = session.get(url, headers=_rest_headers(), params=params, timeout=60)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def get_csv(date: str) -> Optional[Tuple[bytes, str]]:
    _require_enabled()
    rows = _fetch_rows(date)
    if not rows:
        return None

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([header for header, _ in CSV_FIELDS])
    for row in rows:
        writer.writerow([row.get(field, "") or "" for _, field in CSV_FIELDS])

    content = output.getvalue().encode("utf-8")
    filename = rows[0].get("filename") or rows[0].get("source_filename") or f"auction_data_{date}.csv"
    return content, str(filename)


def _parse_csv_content(date: str, filename: str, content: bytes) -> List[Dict[str, object]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("cp949", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows: List[Dict[str, object]] = []
    updated_at = datetime.now(timezone.utc).isoformat()
    base_filename = os.path.basename(filename)
    for idx, raw_row in enumerate(reader, 1):
        if not isinstance(raw_row, dict):
            continue
        record: Dict[str, object] = {
            "date": date,
            "row_index": idx,
            "source_filename": base_filename,
            "filename": base_filename,
            "updated_at": updated_at,
        }
        for header, field in CSV_FIELDS:
            value = raw_row.get(header)
            if value is None:
                record[field] = ""
            else:
                record[field] = value.strip() if isinstance(value, str) else str(value)
        rows.append(record)
    return rows


def _insert_rows(table: str, rows: List[Dict[str, object]]) -> None:
    if not rows:
        return
    session = _session()
    headers = _rest_headers(use_service=True, json_body=True)
    url = f"{_base_url()}/rest/v1/{table}"
    for chunk in _chunk(rows, 500):
        resp = session.post(url, headers=headers, json=chunk, timeout=60)
        if resp.status_code not in (200, 201, 204):
            logger.error("Supabase insert failed (status=%s): %s", resp.status_code, resp.text)
            resp.raise_for_status()


def save_csv(date: str, filename: str, content: bytes) -> None:
    _require_enabled()
    if not content:
        raise ValueError("content is empty")

    rows = _parse_csv_content(date, filename, content)
    if not rows:
        logger.warning("CSV parsed with 0 rows date=%s filename=%s (skipping insert)", date, filename)
        _delete_existing(date)
        return

    _delete_existing(date)
    _insert_rows(_table_name(), rows)

    history_table = _history_table_name()
    if history_table:
        history_rows = []
        ingested_at = datetime.now(timezone.utc).isoformat()
        for row in rows:
            history_row = dict(row)
            history_row["history_ingested_at"] = ingested_at
            history_rows.append(history_row)
        _insert_rows(history_table, history_rows)
