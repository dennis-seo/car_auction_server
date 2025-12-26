"""
Health Check 엔드포인트

서버 상태 모니터링, 배포 검증, 로드밸런서 헬스체크용
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])


class ServiceStatus(BaseModel):
    """개별 서비스 상태"""
    supabase: str = Field(..., description="Supabase 연결 상태")


class HealthResponse(BaseModel):
    """Health Check 응답"""
    status: str = Field(..., description="서버 상태 (healthy/unhealthy)")
    timestamp: str = Field(..., description="응답 시간 (ISO 8601)")
    version: str = Field(..., description="서버 버전")
    services: Optional[ServiceStatus] = Field(None, description="연결된 서비스 상태")


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="서버 상태 확인",
    description="""
서버 상태 및 연결된 서비스 상태를 확인합니다.

**용도:**
- 로드밸런서 헬스체크
- 배포 검증
- 모니터링 시스템 연동
"""
)
async def health_check():
    """
    서버 상태 확인

    - 기본 상태 정보 반환
    - Supabase 연결 상태 확인 (활성화된 경우)
    """
    services = None

    # Supabase 연결 확인
    if settings.SUPABASE_ENABLED:
        supabase_status = "disconnected"
        try:
            from app.repositories import supabase_repo
            # 간단한 연결 테스트 (날짜 목록 조회)
            supabase_repo.get_dates()
            supabase_status = "connected"
        except Exception as e:
            logger.warning("Supabase 연결 확인 실패: %s", e)
            supabase_status = "error"

        services = ServiceStatus(supabase=supabase_status)

    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(timezone.utc).isoformat(),
        version=settings.APP_VERSION,
        services=services
    )
