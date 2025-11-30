"""
Supabase 공통 헬퍼 함수 모듈

supabase_repo.py와 auction_records_repo.py에서 공통으로 사용하는
인증, 세션, HTTP 헤더 관련 유틸리티 함수들.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

import requests

from app.core.config import settings


_SESSION: Optional[requests.Session] = None


def require_enabled() -> None:
    """Supabase가 활성화되어 있는지 확인"""
    if not settings.SUPABASE_ENABLED:
        raise RuntimeError("Supabase integration is disabled")


def base_url() -> str:
    """Supabase REST API base URL 반환"""
    url = (settings.SUPABASE_URL or "").strip().rstrip("/")
    if not url:
        raise RuntimeError("SUPABASE_URL must be configured")
    return url


def read_key() -> str:
    """읽기용 API 키 반환 (service role 또는 anon key)"""
    key = (settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY or "").strip()
    if not key:
        raise RuntimeError("Supabase API key is not configured")
    return key


def service_key() -> str:
    """쓰기용 Service Role 키 반환"""
    key = (settings.SUPABASE_SERVICE_ROLE_KEY or "").strip()
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY must be configured for write operations")
    return key


def session() -> requests.Session:
    """재사용 가능한 requests Session 반환"""
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
    return _SESSION


def rest_headers(
    use_service: bool = False,
    extra: Optional[Dict[str, str]] = None,
    json_body: bool = False
) -> Dict[str, str]:
    """
    Supabase REST API 요청용 HTTP 헤더 생성

    Args:
        use_service: True면 service role key 사용 (쓰기 작업)
        extra: 추가할 헤더
        json_body: True면 Content-Type: application/json 추가

    Returns:
        HTTP 헤더 딕셔너리
    """
    key = service_key() if use_service else read_key()
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


def chunk(items: List[Dict[str, object]], size: int) -> Iterable[List[Dict[str, object]]]:
    """리스트를 지정된 크기의 청크로 분할"""
    for i in range(0, len(items), size):
        yield items[i : i + size]