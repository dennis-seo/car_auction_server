"""
favorites 테이블 Repository

제조사/모델/트림 즐겨찾기 CRUD 작업 처리
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Any

from app.repositories.supabase_common import (
    require_enabled,
    base_url,
    session,
    rest_headers,
)


logger = logging.getLogger(__name__)

TABLE_NAME = "favorites"


def create(
    user_id: str,
    favorite_type: str,
    manufacturer_id: str,
    model_id: Optional[str] = None,
    trim_id: Optional[str] = None,
    manufacturer_label: Optional[str] = None,
    model_label: Optional[str] = None,
    trim_label: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    즐겨찾기 생성

    Args:
        user_id: 사용자 UUID
        favorite_type: 즐겨찾기 타입 (manufacturer, model, trim)
        manufacturer_id: 제조사 ID
        model_id: 모델 ID (model/trim 타입에서 필수)
        trim_id: 트림 ID (trim 타입에서만 필수)
        manufacturer_label: 제조사명 (표시용)
        model_label: 모델명 (표시용)
        trim_label: 트림명 (표시용)

    Returns:
        생성된 즐겨찾기 정보 또는 None (중복 시)
    """
    require_enabled()
    sess = session()
    url = f"{base_url()}/rest/v1/{TABLE_NAME}"

    record = {
        "user_id": user_id,
        "favorite_type": favorite_type,
        "manufacturer_id": manufacturer_id,
        "model_id": model_id,
        "trim_id": trim_id,
        "manufacturer_label": manufacturer_label,
        "model_label": model_label,
        "trim_label": trim_label,
    }

    headers = rest_headers(
        use_service=True,
        json_body=True,
        extra={"Prefer": "return=representation"}
    )

    resp = sess.post(url, headers=headers, json=record, timeout=30)

    # 409 Conflict (unique constraint violation)
    if resp.status_code == 409:
        logger.info(
            "Duplicate favorite: user_id=%s type=%s mfr=%s model=%s trim=%s",
            user_id, favorite_type, manufacturer_id, model_id, trim_id
        )
        return None

    if resp.status_code not in (200, 201):
        logger.error(
            "Failed to create favorite (status=%s): %s",
            resp.status_code, resp.text
        )
        resp.raise_for_status()

    data = resp.json()
    if isinstance(data, list) and data:
        logger.info(
            "Created favorite: id=%s user_id=%s type=%s",
            data[0].get("id"), user_id, favorite_type
        )
        return data[0]

    raise RuntimeError("Failed to create favorite: unexpected response")


def get_by_id(favorite_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """
    ID로 즐겨찾기 조회 (소유권 확인 포함)

    Args:
        favorite_id: 즐겨찾기 UUID
        user_id: 사용자 UUID (소유권 확인용)

    Returns:
        즐겨찾기 정보 또는 None
    """
    require_enabled()
    sess = session()
    url = f"{base_url()}/rest/v1/{TABLE_NAME}"

    params = {
        "select": "*",
        "id": f"eq.{favorite_id}",
        "user_id": f"eq.{user_id}",
    }
    resp = sess.get(url, headers=rest_headers(), params=params, timeout=30)

    if resp.status_code == 404:
        return None
    resp.raise_for_status()

    data = resp.json()
    if isinstance(data, list) and data:
        return data[0]
    return None


def list_by_user(
    user_id: str,
    favorite_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    사용자의 즐겨찾기 목록 조회

    Args:
        user_id: 사용자 UUID
        favorite_type: 필터링할 타입 (선택)

    Returns:
        즐겨찾기 목록
    """
    require_enabled()
    sess = session()
    url = f"{base_url()}/rest/v1/{TABLE_NAME}"

    params: Dict[str, str] = {
        "select": "*",
        "user_id": f"eq.{user_id}",
        "order": "created_at.desc",
    }

    if favorite_type:
        params["favorite_type"] = f"eq.{favorite_type}"

    resp = sess.get(url, headers=rest_headers(), params=params, timeout=30)

    if resp.status_code == 404:
        return []
    resp.raise_for_status()

    data = resp.json()
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def delete(favorite_id: str, user_id: str) -> bool:
    """
    즐겨찾기 삭제

    Args:
        favorite_id: 즐겨찾기 UUID
        user_id: 사용자 UUID (소유권 확인용)

    Returns:
        삭제 성공 여부
    """
    require_enabled()
    sess = session()
    url = f"{base_url()}/rest/v1/{TABLE_NAME}"

    params = {
        "id": f"eq.{favorite_id}",
        "user_id": f"eq.{user_id}",
    }

    headers = rest_headers(use_service=True, extra={"Prefer": "return=representation"})

    resp = sess.delete(url, headers=headers, params=params, timeout=30)

    if resp.status_code == 404:
        return False

    if resp.status_code not in (200, 204):
        logger.error("Delete failed (status=%s): %s", resp.status_code, resp.text)
        return False

    # 삭제된 행이 있는지 확인
    data = resp.json() if resp.text else []
    if isinstance(data, list) and data:
        logger.info("Deleted favorite: id=%s user_id=%s", favorite_id, user_id)
        return True

    return False


def exists(
    user_id: str,
    favorite_type: str,
    manufacturer_id: str,
    model_id: Optional[str] = None,
    trim_id: Optional[str] = None,
) -> bool:
    """
    동일한 즐겨찾기가 이미 존재하는지 확인

    Args:
        user_id: 사용자 UUID
        favorite_type: 즐겨찾기 타입
        manufacturer_id: 제조사 ID
        model_id: 모델 ID
        trim_id: 트림 ID

    Returns:
        존재 여부
    """
    require_enabled()
    sess = session()
    url = f"{base_url()}/rest/v1/{TABLE_NAME}"

    params: Dict[str, str] = {
        "select": "id",
        "user_id": f"eq.{user_id}",
        "favorite_type": f"eq.{favorite_type}",
        "manufacturer_id": f"eq.{manufacturer_id}",
        "limit": "1",
    }

    if model_id is not None:
        params["model_id"] = f"eq.{model_id}"
    else:
        params["model_id"] = "is.null"

    if trim_id is not None:
        params["trim_id"] = f"eq.{trim_id}"
    else:
        params["trim_id"] = "is.null"

    resp = sess.get(url, headers=rest_headers(), params=params, timeout=10)

    if resp.status_code == 404:
        return False
    resp.raise_for_status()

    data = resp.json()
    return isinstance(data, list) and len(data) > 0
