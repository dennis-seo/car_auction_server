"""
차량 검색 API 엔드포인트

제조사, 모델, 트림 기준으로 차량을 검색하는 API를 제공합니다.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.schemas.auction import VehicleListResponse, VehicleRecord


router = APIRouter(tags=["Vehicles"])


@router.get(
    "/vehicles",
    summary="차량 검색",
    description="제조사, 모델, 트림 등 다양한 조건으로 차량을 검색합니다.",
    response_model=VehicleListResponse,
    responses={
        200: {"description": "검색 결과 반환"},
        400: {"description": "잘못된 요청"},
        500: {"description": "서버 내부 오류"},
        503: {"description": "Supabase 비활성화"},
    },
)
def search_vehicles(
    manufacturer_id: Optional[str] = Query(None, description="제조사 ID (예: M001)"),
    model_id: Optional[str] = Query(None, description="모델 ID (예: MD001)"),
    trim_id: Optional[str] = Query(None, description="트림 ID (예: T001)"),
    manufacturer: Optional[str] = Query(None, description="제조사명 (예: 현대)"),
    model: Optional[str] = Query(None, description="모델명 (부분 일치, 예: 그랜저)"),
    year_from: Optional[int] = Query(None, ge=1990, le=2030, description="연식 시작"),
    year_to: Optional[int] = Query(None, ge=1990, le=2030, description="연식 끝"),
    date_from: Optional[str] = Query(None, description="경매일 시작 (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="경매일 끝 (YYYY-MM-DD)"),
    limit: int = Query(100, ge=1, le=1000, description="최대 조회 수"),
    offset: int = Query(0, ge=0, description="오프셋"),
):
    """
    다양한 조건으로 차량을 검색합니다.

    - **manufacturer_id**: car_models.json의 제조사 ID로 필터링
    - **model_id**: car_models.json의 모델 ID로 필터링
    - **trim_id**: car_models.json의 트림 ID로 필터링
    - **manufacturer**: 제조사명으로 필터링 (정확히 일치)
    - **model**: 모델명으로 필터링 (부분 일치)
    - **year_from/year_to**: 연식 범위 필터링
    - **date_from/date_to**: 경매일 범위 필터링
    """
    if not settings.SUPABASE_ENABLED:
        raise HTTPException(status_code=503, detail="Supabase가 비활성화되어 있습니다")

    try:
        from app.repositories import auction_records_repo

        items, total = auction_records_repo.search_vehicles(
            manufacturer_id=manufacturer_id,
            model_id=model_id,
            trim_id=trim_id,
            manufacturer=manufacturer,
            model=model,
            year_from=year_from,
            year_to=year_to,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )

        return VehicleListResponse(
            total=total,
            limit=limit,
            offset=offset,
            items=[VehicleRecord(**item) for item in items],
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"검색 실패: {exc}") from exc


@router.get(
    "/vehicles/{record_id}",
    summary="차량 상세 조회",
    description="특정 레코드 ID의 차량 정보를 조회합니다.",
    response_model=VehicleRecord,
    responses={
        200: {"description": "차량 정보 반환"},
        404: {"description": "차량을 찾을 수 없음"},
        500: {"description": "서버 내부 오류"},
        503: {"description": "Supabase 비활성화"},
    },
)
def get_vehicle(record_id: int):
    """특정 레코드 ID의 차량 정보를 조회합니다."""
    if not settings.SUPABASE_ENABLED:
        raise HTTPException(status_code=503, detail="Supabase가 비활성화되어 있습니다")

    try:
        from app.repositories import auction_records_repo

        items, _ = auction_records_repo.search_vehicles(limit=1, offset=0)

        # ID로 직접 조회
        import requests
        session = requests.Session()
        base_url = f"{auction_records_repo._base_url()}/rest/v1/{auction_records_repo._TABLE_NAME}"
        headers = auction_records_repo._rest_headers()
        params = {"id": f"eq.{record_id}", "select": "*"}

        resp = session.get(base_url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()

        data = resp.json()
        if not data or not isinstance(data, list) or len(data) == 0:
            raise HTTPException(status_code=404, detail="차량을 찾을 수 없습니다")

        return VehicleRecord(**data[0])

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"조회 실패: {exc}") from exc
