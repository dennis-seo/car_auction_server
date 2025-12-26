"""
즐겨찾기 API 엔드포인트

제조사/모델/트림 즐겨찾기 관리
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Path, Query, Request, status
from fastapi.responses import Response

from app.utils.auth import get_current_user
from app.core.config import settings
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from app.core.rate_limiter import limiter, RateLimits
from app.schemas.favorites import (
    FavoriteCreate,
    FavoriteResponse,
    FavoriteListResponse,
)
from app.repositories import favorites_repo


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/favorites", tags=["즐겨찾기"])


@router.post(
    "",
    response_model=FavoriteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="즐겨찾기 추가",
    description="""
제조사, 모델, 또는 트림을 즐겨찾기에 추가합니다.

## 타입별 필수 필드
- **manufacturer**: manufacturer_id만 필요
- **model**: manufacturer_id + model_id 필요
- **trim**: manufacturer_id + model_id + trim_id 필요

## 중복 처리
이미 동일한 조합의 즐겨찾기가 존재하면 409 Conflict 에러를 반환합니다.
""",
    responses={
        201: {"description": "즐겨찾기 추가 성공"},
        400: {"description": "잘못된 요청 (타입에 맞지 않는 필드)"},
        401: {"description": "인증 필요"},
        409: {"description": "이미 존재하는 즐겨찾기"},
        503: {"description": "Supabase 비활성화"},
    },
)
@limiter.limit(RateLimits.FAVORITES_CREATE)
async def create_favorite(
    request: Request,
    body: FavoriteCreate,
    current_user: dict = Depends(get_current_user),
):
    """즐겨찾기 추가"""
    if not settings.SUPABASE_ENABLED:
        raise ServiceUnavailableError(message="Supabase가 비활성화되어 있습니다")

    # 타입별 필드 유효성 검증
    try:
        body.validate_type_fields()
    except ValueError as e:
        raise ValidationError(message=str(e))

    # 중복 확인
    if favorites_repo.exists(
        user_id=current_user["id"],
        favorite_type=body.favorite_type,
        manufacturer_id=body.manufacturer_id,
        model_id=body.model_id,
        trim_id=body.trim_id,
    ):
        raise ConflictError(message="이미 존재하는 즐겨찾기입니다")

    # 생성
    result = favorites_repo.create(
        user_id=current_user["id"],
        favorite_type=body.favorite_type,
        manufacturer_id=body.manufacturer_id,
        model_id=body.model_id,
        trim_id=body.trim_id,
        manufacturer_label=body.manufacturer_label,
        model_label=body.model_label,
        trim_label=body.trim_label,
    )

    if result is None:
        raise ConflictError(message="이미 존재하는 즐겨찾기입니다")

    return FavoriteResponse(**result)


@router.get(
    "",
    response_model=FavoriteListResponse,
    summary="즐겨찾기 목록 조회",
    description="""
현재 로그인한 사용자의 즐겨찾기 목록을 조회합니다.

## 필터링
`favorite_type` 파라미터로 특정 타입만 조회할 수 있습니다.
""",
    responses={
        200: {"description": "즐겨찾기 목록"},
        401: {"description": "인증 필요"},
        503: {"description": "Supabase 비활성화"},
    },
)
@limiter.limit(RateLimits.FAVORITES_LIST)
async def list_favorites(
    request: Request,
    favorite_type: Optional[str] = Query(
        None,
        description="필터링할 타입 (manufacturer, model, trim)",
        pattern="^(manufacturer|model|trim)$",
    ),
    current_user: dict = Depends(get_current_user),
):
    """즐겨찾기 목록 조회"""
    if not settings.SUPABASE_ENABLED:
        raise ServiceUnavailableError(message="Supabase가 비활성화되어 있습니다")

    items = favorites_repo.list_by_user(
        user_id=current_user["id"],
        favorite_type=favorite_type,
    )

    return FavoriteListResponse(
        items=[FavoriteResponse(**item) for item in items],
        total=len(items),
    )


@router.delete(
    "/{favorite_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="즐겨찾기 삭제",
    description="즐겨찾기를 삭제합니다. 자신의 즐겨찾기만 삭제할 수 있습니다.",
    responses={
        204: {"description": "삭제 성공"},
        401: {"description": "인증 필요"},
        404: {"description": "즐겨찾기를 찾을 수 없음"},
        503: {"description": "Supabase 비활성화"},
    },
)
@limiter.limit(RateLimits.FAVORITES_DELETE)
async def delete_favorite(
    request: Request,
    favorite_id: str = Path(..., description="삭제할 즐겨찾기 ID"),
    current_user: dict = Depends(get_current_user),
):
    """즐겨찾기 삭제"""
    if not settings.SUPABASE_ENABLED:
        raise ServiceUnavailableError(message="Supabase가 비활성화되어 있습니다")

    # 존재 여부 및 소유권 확인
    existing = favorites_repo.get_by_id(favorite_id, current_user["id"])
    if not existing:
        raise NotFoundError(message="즐겨찾기를 찾을 수 없습니다")

    # 삭제
    success = favorites_repo.delete(favorite_id, current_user["id"])
    if not success:
        raise NotFoundError(message="즐겨찾기를 찾을 수 없습니다")

    return Response(status_code=status.HTTP_204_NO_CONTENT)
