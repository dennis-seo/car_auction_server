from __future__ import annotations

import base64
import json
import logging
import os
import tempfile
from typing import List, Optional, Tuple

from app.core.config import settings


logger = logging.getLogger("firestore")
_CLIENT = None
_TEMP_CRED_PATH: Optional[str] = None


def _running_on_gcp() -> bool:
    env = os.environ
    return bool(
        env.get("K_SERVICE")
        or env.get("GOOGLE_CLOUD_PROJECT")
        or env.get("GAE_ENV")
    )


def _ensure_client():
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    if not settings.FIRESTORE_ENABLED:
        raise RuntimeError("Firestore is not enabled")

    _ensure_credentials_env()

    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    cred_exists = bool(cred_path and os.path.isfile(cred_path))
    on_gcp = _running_on_gcp()
    project_hint = settings.GCP_PROJECT or settings.GCP_PROJECT_ID or "<auto>"
    logger.info(
        "Initializing Firestore: enabled=%s, project=%s, creds=%s (%s), on_gcp=%s",
        settings.FIRESTORE_ENABLED,
        project_hint,
        os.path.basename(cred_path) if cred_path else "<env-not-set>",
        "exists" if cred_exists else "missing",
        on_gcp,
    )

    try:
        from google.cloud import firestore  # type: ignore
    except Exception as exc:  # pragma: no cover
        logger.exception("Failed to import google-cloud-firestore: %s", exc)
        raise RuntimeError("google-cloud-firestore is not installed or import failed") from exc

    try:
        restore_env = None
        if on_gcp and cred_path:
            restore_env = cred_path
            try:
                del os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
                logger.info("Ignoring GOOGLE_APPLICATION_CREDENTIALS on GCP to use ADC")
            except KeyError:
                restore_env = None

        try:
            project_to_use = settings.GCP_PROJECT or settings.GCP_PROJECT_ID
            _CLIENT = firestore.Client(project=project_to_use) if project_to_use else firestore.Client()  # type: ignore
        finally:
            if restore_env is not None:
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = restore_env

        logger.info("Firestore client ready. project=%s", getattr(_CLIENT, "project", None))
    except Exception as exc:
        logger.exception("Failed to create Firestore client: %s", exc)
        raise
    return _CLIENT


def _collection():
    client = _ensure_client()
    return client.collection(settings.FIRESTORE_COLLECTION)


def save_csv(date: str, filename: str, content: bytes) -> None:
    collection = _collection()
    doc_ref = collection.document(date)
    size_bytes = len(content)
    size_mb = round(size_bytes / 1_000_000, 3)
    data = {
        "date": date,
        "filename": filename,
        "size_bytes": size_bytes,
        "size_mb": size_mb,
        "size": size_mb,
        "size_unit": "MB",
        "content": content,
    }
    if len(content) <= 200_000:
        data["content_b64"] = base64.b64encode(content).decode("ascii")

    logger.info(
        "Uploading CSV to Firestore: date=%s filename=%s size=%d bytes (%.3f MB) collection=%s",
        date,
        filename,
        size_bytes,
        size_mb,
        settings.FIRESTORE_COLLECTION,
    )
    try:
        doc_ref.set(data)
        logger.info("Firestore upload complete: doc=%s/%s", settings.FIRESTORE_COLLECTION, date)
    except Exception as exc:
        logger.exception("Firestore upload failed: %s", exc)
        raise


def list_dates() -> List[str]:
    docs = list(_collection().stream())
    dates: List[str] = [doc.id for doc in docs]
    dates.sort(reverse=True)
    return dates


def get_csv(date: str) -> Optional[Tuple[bytes, str]]:
    doc = _collection().document(date).get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    content = data.get("content")
    filename = data.get("filename") or f"auction_data_{date}.csv"
    if isinstance(content, bytes):
        return content, filename
    content_b64 = data.get("content_b64")
    if isinstance(content_b64, str):
        try:
            return base64.b64decode(content_b64), filename
        except Exception:
            return None
    return None


def _ensure_credentials_env() -> Optional[str]:
    global _TEMP_CRED_PATH
    existing = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if existing:
        return existing

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
    with os.fdopen(fd, "w", encoding="utf-8") as fp:
        fp.write(json_text)
    _TEMP_CRED_PATH = tmp_path
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp_path
    return tmp_path
