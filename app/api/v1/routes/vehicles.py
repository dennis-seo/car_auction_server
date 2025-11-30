"""
차량 검색 API 엔드포인트

제조사, 모델, 트림 기준으로 차량을 검색하는 API를 제공합니다.
auction_records 테이블에서 정규화된 차량 데이터를 조회합니다.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query

from app.core.config import settings
from app.schemas.auction import ErrorResponse, VehicleListResponse, VehicleRecord


router = APIRouter(tags=["Vehicles"])


@router.get(
    "/vehicles",
    summary="차량 검색",
    description="""
제조사, 모델, 트림 등 다양한 조건으로 경매 차량을 검색합니다.

## 검색 방식

### 1. ID 기반 검색 (권장)
`car_models.json`에 정의된 ID를 사용하여 정확한 검색이 가능합니다.
- `manufacturer_id`: 제조사 ID (예: 현대=5, 기아=2, 벤츠=6)
- `model_id`: 모델 ID (예: 그랜저=96, K5=38)
- `trim_id`: 트림 ID (예: 디 올뉴그랜저=3357)

### 2. 텍스트 기반 검색
- `manufacturer`: 제조사명으로 검색 (정확히 일치)
- `model`: 모델명으로 검색 (부분 일치, LIKE 검색)

### 3. 범위 검색
- `year_from` / `year_to`: 연식 범위
- `date_from` / `date_to`: 경매일 범위 (YYYY-MM-DD)

## 페이지네이션
- `limit`: 한 번에 조회할 최대 개수 (기본값: 100, 최대: 1000)
- `offset`: 시작 위치 (기본값: 0)

## 주요 제조사 ID
| 국산 | ID | 수입 | ID |
|------|-----|------|-----|
| 현대 | 5 | 벤츠 | 6 |
| 기아 | 2 | BMW | 7 |
| 제네시스 | 146 | 아우디 | 8 |
| 르노삼성 | 3 | 폭스바겐 | 9 |
| 쉐보레 | 1 | 볼보 | 10 |
| 쌍용 | 4 | 토요타 | 22 |
    """,
    response_model=VehicleListResponse,
    responses={
        200: {
            "description": "검색 결과 반환",
            "content": {
                "application/json": {
                    "example": {
                        "total": 1523,
                        "limit": 100,
                        "offset": 0,
                        "items": [
                            {
                                "id": 12345,
                                "manufacturer": "현대",
                                "model": "그랜저",
                                "year": 2023,
                                "price": 3190,
                                "km": 45000
                            }
                        ]
                    }
                }
            }
        },
        400: {
            "description": "잘못된 요청 파라미터",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "example": {"detail": "year_from은 year_to보다 작거나 같아야 합니다"}
                }
            }
        },
        500: {
            "description": "서버 내부 오류",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "example": {"detail": "검색 실패: Database connection error"}
                }
            }
        },
        503: {
            "description": "Supabase 비활성화 상태",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "example": {"detail": "Supabase가 비활성화되어 있습니다"}
                }
            }
        },
    },
)
def search_vehicles(
    manufacturer_id: Optional[str] = Query(
        None,
        description="제조사 ID (car_models.json 기준). 예: 현대=5, 기아=2, 벤츠=6",
        example="5"
    ),
    model_id: Optional[str] = Query(
        None,
        description="모델 ID (car_models.json 기준). 예: 그랜저=96, K5=38",
        example="96"
    ),
    trim_id: Optional[str] = Query(
        None,
        description="트림 ID (car_models.json 기준). 예: 디 올뉴그랜저=3357",
        example="3357"
    ),
    manufacturer: Optional[str] = Query(
        None,
        description="제조사명 (정확히 일치). 예: 현대, 기아, 벤츠, BMW",
        example="현대"
    ),
    model: Optional[str] = Query(
        None,
        description="모델명 (부분 일치 검색). 예: 그랜저, 쏘나타, E클래스",
        example="그랜저"
    ),
    year_from: Optional[int] = Query(
        None,
        ge=1990,
        le=2030,
        description="연식 시작 (이상). 예: 2020",
        example=2020
    ),
    year_to: Optional[int] = Query(
        None,
        ge=1990,
        le=2030,
        description="연식 끝 (이하). 예: 2024",
        example=2024
    ),
    date_from: Optional[str] = Query(
        None,
        description="경매일 시작 (YYYY-MM-DD 형식, 이상)",
        example="2025-01-01",
        regex=r"^\d{4}-\d{2}-\d{2}$"
    ),
    date_to: Optional[str] = Query(
        None,
        description="경매일 끝 (YYYY-MM-DD 형식, 이하)",
        example="2025-11-30",
        regex=r"^\d{4}-\d{2}-\d{2}$"
    ),
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="한 번에 조회할 최대 개수 (1-1000)",
        example=100
    ),
    offset: int = Query(
        0,
        ge=0,
        description="시작 위치 (0부터 시작, 페이지네이션용)",
        example=0
    ),
):
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
    description="""
특정 레코드 ID로 차량의 상세 정보를 조회합니다.

## 사용 예시
차량 목록 검색 결과에서 `id` 값을 사용하여 해당 차량의 전체 정보를 조회할 수 있습니다.

## 응답 필드
- **식별 정보**: id, vin (차대번호), car_number (차량번호)
- **경매 정보**: auction_date, sell_number, auction_house
- **차량 정보**: manufacturer, model, trim, year, fuel_type 등
- **상태 정보**: km (주행거리), price (낙찰가), score (평가등급), color
    """,
    response_model=VehicleRecord,
    responses={
        200: {
            "description": "차량 정보 반환",
            "content": {
                "application/json": {
                    "example": {
                        "id": 12345,
                        "vin": "KMHD341CBNU123456",
                        "car_number": "123가4567",
                        "auction_date": "2025-11-27",
                        "sell_number": 644,
                        "auction_house": "롯데 경매장",
                        "manufacturer_id": "5",
                        "model_id": "96",
                        "trim_id": "3357",
                        "manufacturer": "현대",
                        "model": "그랜저",
                        "sub_model": "IG",
                        "trim": "디 올뉴그랜저 (22년~현재)",
                        "year": 2023,
                        "fuel_type": "가솔린",
                        "transmission": "자동",
                        "engine_cc": 2497,
                        "usage_type": "자가용",
                        "km": 45000,
                        "price": 3190,
                        "score": "A / B",
                        "color": "어비스블랙",
                        "image_url": "https://imgmk.lotteautoauction.net/AU_CAR_IMG_ORG_HP/202511/KS20251126001234.JPG"
                    }
                }
            }
        },
        404: {
            "description": "차량을 찾을 수 없음",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "example": {"detail": "차량을 찾을 수 없습니다"}
                }
            }
        },
        500: {
            "description": "서버 내부 오류",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "example": {"detail": "조회 실패: Database connection error"}
                }
            }
        },
        503: {
            "description": "Supabase 비활성화 상태",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "example": {"detail": "Supabase가 비활성화되어 있습니다"}
                }
            }
        },
    },
)
def get_vehicle(
    record_id: int = Path(
        ...,
        description="조회할 차량의 레코드 ID",
        example=12345,
        ge=1
    )
):
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
