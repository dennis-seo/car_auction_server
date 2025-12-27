"""
users 테이블 Repository

사용자 정보 CRUD 작업을 처리하는 모듈
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple

from app.repositories.supabase_common import (
    require_enabled,
    base_url,
    session,
    rest_headers,
)
from app.core.permissions import UserRole


logger = logging.getLogger(__name__)

TABLE_NAME = "users"

# 기본 역할
DEFAULT_ROLE = UserRole.FREE.value


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


def update_last_logout(user_id: str) -> None:
    """
    마지막 로그아웃 시간 업데이트 (토큰 무효화용)

    Args:
        user_id: 사용자 UUID
    """
    require_enabled()
    sess = session()
    url = f"{base_url()}/rest/v1/{TABLE_NAME}"

    params = {"id": f"eq.{user_id}"}
    record = {"last_logout_at": datetime.now(timezone.utc).isoformat()}

    headers = rest_headers(use_service=True, json_body=True)

    resp = sess.patch(url, headers=headers, params=params, json=record, timeout=30)
    if resp.status_code not in (200, 204):
        logger.warning("Failed to update last_logout_at for user %s", user_id)
    else:
        logger.info("User logged out: id=%s", user_id)


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


# ===== 역할(Role) 관련 함수 =====

def update_role(
    user_id: str,
    new_role: str,
    updated_by: str
) -> Optional[Dict[str, Any]]:
    """
    사용자 역할 변경

    Args:
        user_id: 변경할 사용자 UUID
        new_role: 새 역할 (master, bidder, premium, free)
        updated_by: 변경을 수행한 관리자 UUID

    Returns:
        업데이트된 사용자 정보 또는 None
    """
    require_enabled()

    # 유효한 역할인지 확인
    if not UserRole.is_valid_for_db(new_role):
        raise ValueError(f"유효하지 않은 역할입니다: {new_role}")

    sess = session()
    url = f"{base_url()}/rest/v1/{TABLE_NAME}"

    params = {"id": f"eq.{user_id}"}
    record = {
        "role": new_role,
        "role_updated_at": datetime.now(timezone.utc).isoformat(),
        "role_updated_by": updated_by,
    }

    headers = rest_headers(
        use_service=True,
        json_body=True,
        extra={"Prefer": "return=representation"}
    )

    resp = sess.patch(url, headers=headers, params=params, json=record, timeout=30)

    if resp.status_code not in (200, 204):
        logger.error(
            "Failed to update user role (user_id=%s, status=%s): %s",
            user_id, resp.status_code, resp.text
        )
        return None

    data = resp.json()
    if isinstance(data, list) and data:
        logger.info(
            "User role updated: user_id=%s, new_role=%s, updated_by=%s",
            user_id, new_role, updated_by
        )
        return data[0]

    return get_by_id(user_id)


def list_users(
    page: int = 1,
    limit: int = 20,
    role: Optional[str] = None,
    search: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """
    사용자 목록 조회 (페이징, 필터링 지원)

    Args:
        page: 페이지 번호 (1부터 시작)
        limit: 페이지당 수 (최대 100)
        role: 역할 필터
        search: 이메일/이름 검색

    Returns:
        (사용자 목록, 전체 개수)
    """
    require_enabled()

    # 유효성 검사
    if page < 1:
        page = 1
    if limit < 1:
        limit = 1
    if limit > 100:
        limit = 100

    sess = session()
    url = f"{base_url()}/rest/v1/{TABLE_NAME}"
    offset = (page - 1) * limit

    # 기본 파라미터
    params: Dict[str, str] = {
        "select": "id,email,name,profile_image,role,created_at,last_login_at,role_updated_at",
        "order": "created_at.desc",
        "limit": str(limit),
        "offset": str(offset),
    }

    # 역할 필터
    if role and UserRole.is_valid_for_db(role):
        params["role"] = f"eq.{role}"

    # 검색 (이메일 또는 이름)
    if search:
        # PostgREST or 조건: email ILIKE %search% OR name ILIKE %search%
        params["or"] = f"(email.ilike.*{search}*,name.ilike.*{search}*)"

    headers = rest_headers(extra={"Prefer": "count=exact"})
    resp = sess.get(url, headers=headers, params=params, timeout=30)

    if resp.status_code == 404:
        return [], 0
    resp.raise_for_status()

    # content-range 헤더에서 전체 개수 추출
    total = 0
    if "content-range" in resp.headers:
        range_header = resp.headers["content-range"]
        if "/" in range_header:
            total_str = range_header.split("/")[-1]
            if total_str != "*":
                total = int(total_str)

    data = resp.json()
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)], total

    return [], total


def get_user_stats() -> Dict[str, Any]:
    """
    사용자 통계 조회

    Returns:
        등급별 사용자 수 및 가입 통계
    """
    require_enabled()

    sess = session()
    url = f"{base_url()}/rest/v1/{TABLE_NAME}"

    # 전체 사용자 및 역할별 수 조회
    # Supabase에서는 GROUP BY가 제한적이므로 각각 조회

    stats = {
        "total_users": 0,
        "by_role": {
            "master": 0,
            "bidder": 0,
            "premium": 0,
            "free": 0,
        },
        "recent_signups": {
            "today": 0,
            "this_week": 0,
            "this_month": 0,
        }
    }

    # 전체 사용자 수
    headers = rest_headers(extra={"Prefer": "count=exact"})
    resp = sess.head(url, headers=headers, params={"select": "id"}, timeout=10)
    if "content-range" in resp.headers:
        range_header = resp.headers["content-range"]
        if "/" in range_header:
            total_str = range_header.split("/")[-1]
            if total_str != "*":
                stats["total_users"] = int(total_str)

    # 역할별 사용자 수
    for role in UserRole.db_values():
        resp = sess.head(
            url,
            headers=headers,
            params={"select": "id", "role": f"eq.{role}"},
            timeout=10
        )
        if "content-range" in resp.headers:
            range_header = resp.headers["content-range"]
            if "/" in range_header:
                total_str = range_header.split("/")[-1]
                if total_str != "*":
                    stats["by_role"][role] = int(total_str)

    # 최근 가입자 수
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)

    # 오늘 가입
    resp = sess.head(
        url,
        headers=headers,
        params={"select": "id", "created_at": f"gte.{today_start.isoformat()}"},
        timeout=10
    )
    if "content-range" in resp.headers:
        range_header = resp.headers["content-range"]
        if "/" in range_header:
            total_str = range_header.split("/")[-1]
            if total_str != "*":
                stats["recent_signups"]["today"] = int(total_str)

    # 이번 주 가입
    resp = sess.head(
        url,
        headers=headers,
        params={"select": "id", "created_at": f"gte.{week_start.isoformat()}"},
        timeout=10
    )
    if "content-range" in resp.headers:
        range_header = resp.headers["content-range"]
        if "/" in range_header:
            total_str = range_header.split("/")[-1]
            if total_str != "*":
                stats["recent_signups"]["this_week"] = int(total_str)

    # 이번 달 가입
    resp = sess.head(
        url,
        headers=headers,
        params={"select": "id", "created_at": f"gte.{month_start.isoformat()}"},
        timeout=10
    )
    if "content-range" in resp.headers:
        range_header = resp.headers["content-range"]
        if "/" in range_header:
            total_str = range_header.split("/")[-1]
            if total_str != "*":
                stats["recent_signups"]["this_month"] = int(total_str)

    return stats


def count_by_role(role: str) -> int:
    """특정 역할의 사용자 수 조회"""
    require_enabled()

    sess = session()
    url = f"{base_url()}/rest/v1/{TABLE_NAME}"

    headers = rest_headers(extra={"Prefer": "count=exact"})
    resp = sess.head(
        url,
        headers=headers,
        params={"select": "id", "role": f"eq.{role}"},
        timeout=10
    )

    if "content-range" in resp.headers:
        range_header = resp.headers["content-range"]
        if "/" in range_header:
            total_str = range_header.split("/")[-1]
            if total_str != "*":
                return int(total_str)

    return 0