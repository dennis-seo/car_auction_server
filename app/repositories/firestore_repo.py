from __future__ import annotations

import base64
import logging
import os
from typing import List, Optional, Tuple

from app.core.config import settings


logger = logging.getLogger("firestore")
_CLIENT = None


def _running_on_gcp() -> bool:
    env = os.environ
    # Cloud Run/Cloud Functions/GAE indicators
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

    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    cred_exists = bool(cred_path and os.path.isfile(cred_path))
    on_gcp = _running_on_gcp()
    project_hint = settings.GCP_PROJECT or "<auto>"
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
    except Exception as exc:  # pragma: no cover - import environment dependent
        logger.exception("Failed to import google-cloud-firestore: %s", exc)
        raise RuntimeError(
            "google-cloud-firestore is not installed or import failed"
        ) from exc

    try:
        # If running on GCP, ignore local GOOGLE_APPLICATION_CREDENTIALS to prefer ADC
        restore_env = None
        if on_gcp and cred_path:
            restore_env = cred_path
            try:
                del os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
                logger.info("Ignoring GOOGLE_APPLICATION_CREDENTIALS on GCP to use ADC")
            except KeyError:
                restore_env = None

        try:
            if not settings.GCP_PROJECT:
                _CLIENT = firestore.Client()  # type: ignore
            else:
                _CLIENT = firestore.Client(project=settings.GCP_PROJECT)  # type: ignore
        finally:
            if restore_env is not None:
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = restore_env

        logger.info("Firestore client created. using project=%s", getattr(_CLIENT, "project", None))
    except Exception as exc:
        logger.exception("Failed to create Firestore client: %s", exc)
        raise
    return _CLIENT


def _collection():
    client = _ensure_client()
    return client.collection(settings.FIRESTORE_COLLECTION)


def save_csv(date: str, filename: str, content: bytes) -> None:
    """
    Save CSV content under document id `date`.
    Fields: date, filename, size, content (bytes), content_b64 (small only), hash (optional later).
    Note: Firestore has a 1 MiB per document limit. For larger files, prefer GCS.
    """
    col = _collection()
    doc_ref = col.document(date)
    size_bytes = len(content)
    # Store MB using decimal definition (1 MB = 1,000,000 bytes)
    size_mb = round(size_bytes / 1_000_000, 3)
    data = {
        "date": date,
        "filename": filename,
        # Keep bytes and MB for clarity; 'size' kept as MB for UI friendliness
        "size_bytes": size_bytes,
        "size_mb": size_mb,
        "size": size_mb,
        "size_unit": "MB",
        # Store raw bytes in Firestore Blob field
        "content": content,
    }
    # For convenience allow a quick preview for very small files
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
        logger.info("Firestore upload completed: doc=%s/%s", settings.FIRESTORE_COLLECTION, date)
    except Exception as exc:
        logger.exception("Firestore upload failed: %s", exc)
        raise


def list_dates() -> List[str]:
    col = _collection()
    docs = list(col.stream())
    dates: List[str] = []
    for d in docs:
        # Prefer document id as authoritative date key
        dates.append(d.id)
    # Sort desc (newest first) assuming YYMMDD string
    dates.sort(reverse=True)
    return dates


def get_csv(date: str) -> Optional[Tuple[bytes, str]]:
    """Return (content_bytes, filename) or None if not found."""
    col = _collection()
    doc = col.document(date).get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    content = data.get("content")
    filename = data.get("filename") or f"auction_data_{date}.csv"
    if isinstance(content, bytes):
        return content, filename
    # Fallback if only base64 was stored
    content_b64 = data.get("content_b64")
    if isinstance(content_b64, str):
        try:
            return base64.b64decode(content_b64), filename
        except Exception:
            return None
    return None
