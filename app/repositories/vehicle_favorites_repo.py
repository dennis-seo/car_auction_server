"""
vehicle_favorites 테이블 Repository

특정 경매 차량 즐겨찾기 CRUD 작업 처리
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

TABLE_NAME = "vehicle_favorites"


def create(user_id: str, record_id: int) -> Optional[Dict[str, Any]]:
    """
    차량 즐겨찾기 생성

    Args:
        user_id: 사용자 UUID
        record_id: 차량 레코드 ID (auction_records.id)

    Returns:
        생성된 즐겨찾기 정보 또는 None (중복 시)
    """
    require_enabled()
    sess = session()
    url = f"{base_url()}/rest/v1/{TABLE_NAME}"

    record = {
        "user_id": user_id,
        "record_id": record_id,
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
            "Duplicate vehicle favorite: user_id=%s record_id=%s",
            user_id, record_id
        )
        return None

    if resp.status_code not in (200, 201):
        logger.error(
            "Failed to create vehicle favorite (status=%s): %s",
            resp.status_code, resp.text
        )
        resp.raise_for_status()

    data = resp.json()
    if isinstance(data, list) and data:
        logger.info(
            "Created vehicle favorite: id=%s user_id=%s record_id=%s",
            data[0].get("id"), user_id, record_id
        )
        return data[0]

    raise RuntimeError("Failed to create vehicle favorite: unexpected response")


def get_by_id(favorite_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    """
    ID로 차량 즐겨찾기 조회 (소유권 확인 포함)

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


def list_by_user(user_id: str) -> List[Dict[str, Any]]:
    """
    사용자의 차량 즐겨찾기 목록 조회 (차량 정보 포함)

    Args:
        user_id: 사용자 UUID

    Returns:
        즐겨찾기 목록 (차량 정보 포함)
    """
    require_enabled()
    sess = session()
    url = f"{base_url()}/rest/v1/{TABLE_NAME}"

    # auction_records 테이블과 JOIN하여 차량 정보 포함
    params: Dict[str, str] = {
        "select": "*,auction_records(*)",
        "user_id": f"eq.{user_id}",
        "order": "created_at.desc",
    }

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
    차량 즐겨찾기 삭제

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
        logger.info("Deleted vehicle favorite: id=%s user_id=%s", favorite_id, user_id)
        return True

    return False


def exists(user_id: str, record_id: int) -> bool:
    """
    동일한 차량 즐겨찾기가 이미 존재하는지 확인

    Args:
        user_id: 사용자 UUID
        record_id: 차량 레코드 ID

    Returns:
        존재 여부
    """
    require_enabled()
    sess = session()
    url = f"{base_url()}/rest/v1/{TABLE_NAME}"

    params: Dict[str, str] = {
        "select": "id",
        "user_id": f"eq.{user_id}",
        "record_id": f"eq.{record_id}",
        "limit": "1",
    }

    resp = sess.get(url, headers=rest_headers(), params=params, timeout=10)

    if resp.status_code == 404:
        return False
    resp.raise_for_status()

    data = resp.json()
    return isinstance(data, list) and len(data) > 0


def check_record_exists(record_id: int) -> bool:
    """
    차량 레코드가 존재하는지 확인

    Args:
        record_id: 차량 레코드 ID

    Returns:
        존재 여부
    """
    require_enabled()
    sess = session()
    url = f"{base_url()}/rest/v1/auction_records"

    params: Dict[str, str] = {
        "select": "id",
        "id": f"eq.{record_id}",
        "limit": "1",
    }

    resp = sess.get(url, headers=rest_headers(), params=params, timeout=10)

    if resp.status_code == 404:
        return False
    resp.raise_for_status()

    data = resp.json()
    return isinstance(data, list) and len(data) > 0


def list_record_ids_by_user(user_id: str) -> List[int]:
    """
    사용자의 즐겨찾기 차량 record_id 목록만 조회 (경량 API)

    Args:
        user_id: 사용자 UUID

    Returns:
        record_id 리스트
    """
    require_enabled()
    sess = session()
    url = f"{base_url()}/rest/v1/{TABLE_NAME}"

    params: Dict[str, str] = {
        "select": "record_id",
        "user_id": f"eq.{user_id}",
        "order": "created_at.desc",
    }

    resp = sess.get(url, headers=rest_headers(), params=params, timeout=30)

    if resp.status_code == 404:
        return []
    resp.raise_for_status()

    data = resp.json()
    if isinstance(data, list):
        return [
            row.get("record_id")
            for row in data
            if isinstance(row, dict) and row.get("record_id") is not None
        ]
    return []
