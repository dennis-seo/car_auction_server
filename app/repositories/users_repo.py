"""
users 테이블 Repository

사용자 정보 CRUD 작업을 처리하는 모듈
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from app.repositories.supabase_common import (
    require_enabled,
    base_url,
    session,
    rest_headers,
)


logger = logging.getLogger(__name__)

TABLE_NAME = "users"


def get_by_google_sub(google_sub: str) -> Optional[Dict[str, Any]]:
    """
    Google Sub ID로 사용자 조회

    Args:
        google_sub: Google 고유 사용자 ID

    Returns:
        사용자 정보 딕셔너리 또는 None
    """
    require_enabled()
    sess = session()
    url = f"{base_url()}/rest/v1/{TABLE_NAME}"

    params = {
        "select": "*",
        "google_sub": f"eq.{google_sub}",
    }
    resp = sess.get(url, headers=rest_headers(), params=params, timeout=30)

    if resp.status_code == 404:
        return None
    resp.raise_for_status()

    data = resp.json()
    if isinstance(data, list) and data:
        return data[0]
    return None


def get_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """
    사용자 ID로 조회

    Args:
        user_id: 사용자 UUID

    Returns:
        사용자 정보 딕셔너리 또는 None
    """
    require_enabled()
    sess = session()
    url = f"{base_url()}/rest/v1/{TABLE_NAME}"

    params = {
        "select": "*",
        "id": f"eq.{user_id}",
    }
    resp = sess.get(url, headers=rest_headers(), params=params, timeout=30)

    if resp.status_code == 404:
        return None
    resp.raise_for_status()

    data = resp.json()
    if isinstance(data, list) and data:
        return data[0]
    return None


def create(
    google_sub: str,
    email: str,
    name: Optional[str] = None,
    profile_image: Optional[str] = None
) -> Dict[str, Any]:
    """
    새 사용자 생성

    Args:
        google_sub: Google 고유 사용자 ID
        email: 이메일 주소
        name: 사용자 이름
        profile_image: 프로필 이미지 URL

    Returns:
        생성된 사용자 정보
    """
    require_enabled()
    sess = session()
    url = f"{base_url()}/rest/v1/{TABLE_NAME}"

    record = {
        "google_sub": google_sub,
        "email": email,
        "name": name,
        "profile_image": profile_image,
    }

    headers = rest_headers(
        use_service=True,
        json_body=True,
        extra={"Prefer": "return=representation"}
    )

    resp = sess.post(url, headers=headers, json=record, timeout=30)
    if resp.status_code not in (200, 201):
        logger.error("Failed to create user (status=%s): %s", resp.status_code, resp.text)
        resp.raise_for_status()

    data = resp.json()
    if isinstance(data, list) and data:
        logger.info("Created new user: id=%s email=%s", data[0].get("id"), email)
        return data[0]

    raise RuntimeError("Failed to create user: unexpected response")


def update_last_login(user_id: str) -> None:
    """
    마지막 로그인 시간 업데이트

    Args:
        user_id: 사용자 UUID
    """
    require_enabled()
    sess = session()
    url = f"{base_url()}/rest/v1/{TABLE_NAME}"

    params = {"id": f"eq.{user_id}"}
    record = {"last_login_at": datetime.now(timezone.utc).isoformat()}

    headers = rest_headers(use_service=True, json_body=True)

    resp = sess.patch(url, headers=headers, params=params, json=record, timeout=30)
    if resp.status_code not in (200, 204):
        logger.warning("Failed to update last_login_at for user %s", user_id)


def update_profile(
    user_id: str,
    name: Optional[str] = None,
    profile_image: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    사용자 프로필 업데이트

    Args:
        user_id: 사용자 UUID
        name: 새 이름 (None이면 업데이트하지 않음)
        profile_image: 새 프로필 이미지 URL

    Returns:
        업데이트된 사용자 정보 또는 None
    """
    require_enabled()
    sess = session()
    url = f"{base_url()}/rest/v1/{TABLE_NAME}"

    params = {"id": f"eq.{user_id}"}
    record = {}
    if name is not None:
        record["name"] = name
    if profile_image is not None:
        record["profile_image"] = profile_image

    if not record:
        return get_by_id(user_id)

    headers = rest_headers(
        use_service=True,
        json_body=True,
        extra={"Prefer": "return=representation"}
    )

    resp = sess.patch(url, headers=headers, params=params, json=record, timeout=30)
    if resp.status_code not in (200, 204):
        logger.error("Failed to update user profile (status=%s): %s", resp.status_code, resp.text)
        return None

    data = resp.json()
    if isinstance(data, list) and data:
        return data[0]
    return get_by_id(user_id)


def find_or_create(
    google_sub: str,
    email: str,
    name: Optional[str] = None,
    profile_image: Optional[str] = None
) -> Dict[str, Any]:
    """
    사용자 조회 또는 생성 (로그인 시 사용)

    기존 사용자가 있으면 프로필 업데이트 후 반환,
    없으면 새로 생성

    Args:
        google_sub: Google 고유 사용자 ID
        email: 이메일 주소
        name: 사용자 이름
        profile_image: 프로필 이미지 URL

    Returns:
        사용자 정보 딕셔너리
    """
    existing = get_by_google_sub(google_sub)

    if existing:
        user_id = existing["id"]
        # 프로필 정보 업데이트 (Google에서 변경되었을 수 있음)
        if name or profile_image:
            update_profile(user_id, name=name, profile_image=profile_image)
        update_last_login(user_id)
        return get_by_id(user_id) or existing

    return create(google_sub, email, name, profile_image)