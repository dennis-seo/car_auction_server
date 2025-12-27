"""
Admin 사용자 관리 API

마스터 권한 사용자 전용 사용자 관리 엔드포인트
"""

import logging

from fastapi import APIRouter, Depends, Path, Query, Request, status, HTTPException

from app.utils.auth import get_current_user
from app.core.config import settings
from app.core.exceptions import (
    NotFoundError,
    ForbiddenError,
    ServiceUnavailableError,
    ValidationError,
)
from app.core.rate_limiter import limiter, RateLimits
from app.core.permissions import UserRole, require_roles, RoleChecker
from app.schemas.auction import Pagination
from app.schemas.admin import (
    UserSummary,
    UserDetail,
    UserListResponse,
    UpdateRoleRequest,
    UpdateRoleResponse,
    UserStatsResponse,
    RoleStats,
    SignupStats,
)
from app.repositories import users_repo


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/users", tags=["Admin - 사용자 관리"])


def _check_master_role(current_user: dict) -> None:
    """마스터 권한 확인"""
    if current_user.get("role") != UserRole.MASTER.value:
        raise ForbiddenError(message="마스터 권한이 필요합니다")


@router.get(
    "",
    response_model=UserListResponse,
    summary="사용자 목록 조회",
    description="""
마스터 권한으로 전체 사용자 목록을 조회합니다.

## 필터링
- `role`: 특정 역할만 필터링 (master, bidder, premium, free)
- `search`: 이메일 또는 이름으로 검색

## 정렬
가입일 기준 최신순 정렬
""",
    responses={
        200: {"description": "사용자 목록"},
        401: {"description": "인증 필요"},
        403: {"description": "마스터 권한 필요"},
        503: {"description": "Supabase 비활성화"},
    },
)
@limiter.limit("30/minute")
async def list_users(
    request: Request,
    page: int = Query(1, ge=1, description="페이지 번호 (1부터 시작)"),
    limit: int = Query(20, ge=1, le=100, description="페이지당 수 (최대 100)"),
    role: str = Query(None, description="역할 필터 (master, bidder, premium, free)"),
    search: str = Query(None, description="이메일/이름 검색"),
    current_user: dict = Depends(get_current_user),
):
    """사용자 목록 조회 (마스터 전용)"""
    if not settings.SUPABASE_ENABLED:
        raise ServiceUnavailableError(message="Supabase가 비활성화되어 있습니다")

    _check_master_role(current_user)

    # 사용자 목록 조회
    users, total = users_repo.list_users(
        page=page,
        limit=limit,
        role=role,
        search=search,
    )

    # 페이지네이션 정보 계산
    total_pages = (total + limit - 1) // limit if total > 0 else 0

    pagination = Pagination(
        page=page,
        limit=limit,
        total_items=total,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )

    # 응답 변환
    items = [
        UserSummary(
            id=u.get("id", ""),
            email=u.get("email", ""),
            name=u.get("name"),
            profile_image=u.get("profile_image"),
            role=u.get("role", "free"),
            created_at=u.get("created_at"),
            last_login_at=u.get("last_login_at"),
        )
        for u in users
    ]

    return UserListResponse(pagination=pagination, items=items)


@router.get(
    "/stats",
    response_model=UserStatsResponse,
    summary="사용자 통계 조회",
    description="역할별 사용자 수 및 가입 통계를 조회합니다.",
    responses={
        200: {"description": "사용자 통계"},
        401: {"description": "인증 필요"},
        403: {"description": "마스터 권한 필요"},
        503: {"description": "Supabase 비활성화"},
    },
)
@limiter.limit("30/minute")
async def get_user_stats(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """사용자 통계 조회 (마스터 전용)"""
    if not settings.SUPABASE_ENABLED:
        raise ServiceUnavailableError(message="Supabase가 비활성화되어 있습니다")

    _check_master_role(current_user)

    stats = users_repo.get_user_stats()

    return UserStatsResponse(
        total_users=stats.get("total_users", 0),
        by_role=RoleStats(**stats.get("by_role", {})),
        recent_signups=SignupStats(**stats.get("recent_signups", {})),
    )


@router.get(
    "/{user_id}",
    response_model=UserDetail,
    summary="사용자 상세 조회",
    description="특정 사용자의 상세 정보를 조회합니다.",
    responses={
        200: {"description": "사용자 상세 정보"},
        401: {"description": "인증 필요"},
        403: {"description": "마스터 권한 필요"},
        404: {"description": "사용자를 찾을 수 없음"},
        503: {"description": "Supabase 비활성화"},
    },
)
@limiter.limit("60/minute")
async def get_user_detail(
    request: Request,
    user_id: str = Path(..., description="사용자 UUID"),
    current_user: dict = Depends(get_current_user),
):
    """사용자 상세 조회 (마스터 전용)"""
    if not settings.SUPABASE_ENABLED:
        raise ServiceUnavailableError(message="Supabase가 비활성화되어 있습니다")

    _check_master_role(current_user)

    user = users_repo.get_by_id(user_id)
    if not user:
        raise NotFoundError(message="사용자를 찾을 수 없습니다")

    return UserDetail(
        id=user.get("id", ""),
        email=user.get("email", ""),
        name=user.get("name"),
        profile_image=user.get("profile_image"),
        role=user.get("role", "free"),
        created_at=user.get("created_at"),
        last_login_at=user.get("last_login_at"),
        role_updated_at=user.get("role_updated_at"),
        role_updated_by=user.get("role_updated_by"),
    )


@router.patch(
    "/{user_id}/role",
    response_model=UpdateRoleResponse,
    summary="사용자 역할 변경",
    description="""
특정 사용자의 역할을 변경합니다.

## 제한 사항
- 자기 자신의 역할은 변경할 수 없습니다
- 마지막 마스터의 역할은 변경할 수 없습니다
""",
    responses={
        200: {"description": "역할 변경 성공"},
        400: {"description": "유효하지 않은 요청"},
        401: {"description": "인증 필요"},
        403: {"description": "마스터 권한 필요 또는 변경 불가"},
        404: {"description": "사용자를 찾을 수 없음"},
        503: {"description": "Supabase 비활성화"},
    },
)
@limiter.limit("10/minute")
async def update_user_role(
    request: Request,
    user_id: str = Path(..., description="사용자 UUID"),
    body: UpdateRoleRequest = ...,
    current_user: dict = Depends(get_current_user),
):
    """사용자 역할 변경 (마스터 전용)"""
    if not settings.SUPABASE_ENABLED:
        raise ServiceUnavailableError(message="Supabase가 비활성화되어 있습니다")

    _check_master_role(current_user)

    # 자기 자신 역할 변경 금지
    if user_id == current_user["id"]:
        raise ForbiddenError(message="자신의 역할은 변경할 수 없습니다")

    # 대상 사용자 확인
    target_user = users_repo.get_by_id(user_id)
    if not target_user:
        raise NotFoundError(message="사용자를 찾을 수 없습니다")

    # 마지막 마스터 보호
    if target_user.get("role") == UserRole.MASTER.value:
        master_count = users_repo.count_by_role(UserRole.MASTER.value)
        if master_count <= 1 and body.role.value != UserRole.MASTER.value:
            raise ForbiddenError(message="마지막 마스터의 역할은 변경할 수 없습니다")

    # 역할 변경
    try:
        updated_user = users_repo.update_role(
            user_id=user_id,
            new_role=body.role.value,
            updated_by=current_user["id"],
        )
    except ValueError as e:
        raise ValidationError(message=str(e))

    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="역할 변경에 실패했습니다"
        )

    return UpdateRoleResponse(
        id=updated_user.get("id", ""),
        email=updated_user.get("email", ""),
        name=updated_user.get("name"),
        role=updated_user.get("role", ""),
        role_updated_at=updated_user.get("role_updated_at"),
        role_updated_by=updated_user.get("role_updated_by"),
    )
