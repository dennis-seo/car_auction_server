"""
차량 즐겨찾기 API 엔드포인트

특정 경매 차량 즐겨찾기 관리
"""

import logging

from fastapi import APIRouter, Depends, Path, Request, status
from fastapi.responses import Response

from app.utils.auth import get_current_user
from app.core.config import settings
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
)
from app.core.rate_limiter import limiter, RateLimits
from app.schemas.vehicle_favorites import (
    VehicleFavoriteCreate,
    VehicleFavoriteResponse,
    VehicleFavoriteWithVehicle,
    VehicleFavoriteListResponse,
)
from app.schemas.auction import VehicleRecord
from app.repositories import vehicle_favorites_repo


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/vehicle-favorites", tags=["차량 즐겨찾기"])


@router.post(
    "",
    response_model=VehicleFavoriteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="차량 즐겨찾기 추가",
    description="""
특정 경매 차량을 즐겨찾기에 추가합니다.

## 사용 방법
차량 목록 또는 상세 조회에서 받은 `id` (record_id)를 전달합니다.

## 중복 처리
이미 동일한 차량이 즐겨찾기에 존재하면 409 Conflict 에러를 반환합니다.
""",
    responses={
        201: {"description": "즐겨찾기 추가 성공"},
        401: {"description": "인증 필요"},
        404: {"description": "차량을 찾을 수 없음"},
        409: {"description": "이미 존재하는 즐겨찾기"},
        503: {"description": "Supabase 비활성화"},
    },
)
@limiter.limit(RateLimits.VEHICLE_FAVORITES_CREATE)
async def create_vehicle_favorite(
    request: Request,
    body: VehicleFavoriteCreate,
    current_user: dict = Depends(get_current_user),
):
    """차량 즐겨찾기 추가"""
    if not settings.SUPABASE_ENABLED:
        raise ServiceUnavailableError(message="Supabase가 비활성화되어 있습니다")

    # 차량 레코드 존재 확인
    if not vehicle_favorites_repo.check_record_exists(body.record_id):
        raise NotFoundError(message="차량을 찾을 수 없습니다")

    # 중복 확인
    if vehicle_favorites_repo.exists(
        user_id=current_user["id"],
        record_id=body.record_id,
    ):
        raise ConflictError(message="이미 존재하는 즐겨찾기입니다")

    # 생성
    result = vehicle_favorites_repo.create(
        user_id=current_user["id"],
        record_id=body.record_id,
    )

    if result is None:
        raise ConflictError(message="이미 존재하는 즐겨찾기입니다")

    return VehicleFavoriteResponse(**result)


@router.get(
    "",
    response_model=VehicleFavoriteListResponse,
    summary="차량 즐겨찾기 목록 조회",
    description="""
현재 로그인한 사용자의 차량 즐겨찾기 목록을 조회합니다.

차량 상세 정보가 함께 반환됩니다.
""",
    responses={
        200: {"description": "즐겨찾기 목록"},
        401: {"description": "인증 필요"},
        503: {"description": "Supabase 비활성화"},
    },
)
@limiter.limit(RateLimits.VEHICLE_FAVORITES_LIST)
async def list_vehicle_favorites(
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """차량 즐겨찾기 목록 조회"""
    if not settings.SUPABASE_ENABLED:
        raise ServiceUnavailableError(message="Supabase가 비활성화되어 있습니다")

    items = vehicle_favorites_repo.list_by_user(user_id=current_user["id"])

    # 응답 변환
    response_items = []
    for item in items:
        vehicle_data = item.pop("auction_records", None)
        favorite = VehicleFavoriteWithVehicle(
            id=item["id"],
            record_id=item["record_id"],
            created_at=item["created_at"],
            vehicle=VehicleRecord(**vehicle_data) if vehicle_data else None,
        )
        response_items.append(favorite)

    return VehicleFavoriteListResponse(
        items=response_items,
        total=len(response_items),
    )


@router.delete(
    "/{favorite_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="차량 즐겨찾기 삭제",
    description="차량 즐겨찾기를 삭제합니다. 자신의 즐겨찾기만 삭제할 수 있습니다.",
    responses={
        204: {"description": "삭제 성공"},
        401: {"description": "인증 필요"},
        404: {"description": "즐겨찾기를 찾을 수 없음"},
        503: {"description": "Supabase 비활성화"},
    },
)
@limiter.limit(RateLimits.VEHICLE_FAVORITES_DELETE)
async def delete_vehicle_favorite(
    request: Request,
    favorite_id: str = Path(..., description="삭제할 즐겨찾기 ID"),
    current_user: dict = Depends(get_current_user),
):
    """차량 즐겨찾기 삭제"""
    if not settings.SUPABASE_ENABLED:
        raise ServiceUnavailableError(message="Supabase가 비활성화되어 있습니다")

    # 존재 여부 및 소유권 확인
    existing = vehicle_favorites_repo.get_by_id(favorite_id, current_user["id"])
    if not existing:
        raise NotFoundError(message="즐겨찾기를 찾을 수 없습니다")

    # 삭제
    success = vehicle_favorites_repo.delete(favorite_id, current_user["id"])
    if not success:
        raise NotFoundError(message="즐겨찾기를 찾을 수 없습니다")

    return Response(status_code=status.HTTP_204_NO_CONTENT)
