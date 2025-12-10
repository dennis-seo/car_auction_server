"""
차량 시세 히스토리 집계 API 엔드포인트

날짜별로 분산된 거래 데이터를 제공하여 그래프가 제대로 그려지도록 합니다.
인기 모델의 경우 특정 날짜에 데이터가 집중되는 문제를 해결합니다.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.schemas.auction import AggregatedHistoryResponse, ErrorResponse


router = APIRouter(tags=["Vehicle History"])


@router.get(
    "/vehicle-history/aggregated",
    summary="차량 시세 히스토리 집계",
    description="""
날짜별로 분산된 거래 데이터와 통계를 제공합니다.

## 배경
인기 모델의 경우 특정 날짜에 데이터가 집중되어 그래프가 제대로 그려지지 않는 문제가 있습니다.
이 API는 날짜별로 샘플링된 데이터를 제공하여 이 문제를 해결합니다.

## 핵심 로직
1. 최근 {months}개월 내 데이터를 날짜 역순으로 조회
2. 날짜별로 그룹화하여 각 날짜에서 최대 {max_per_date}건만 선택
3. 최소 {min_dates}개 이상의 서로 다른 날짜가 확보될 때까지 수집
4. 전체 {max_total}건을 초과하지 않도록 제한
5. 날짜별 통계(건수, 평균/최저/최고가)를 함께 계산하여 반환

## 응답 구조
- **summary**: 전체 집계 요약 (총 건수, 날짜 수, 전체 최저/최고/평균가)
- **data**: 날짜별 집계 데이터 (날짜 오름차순 정렬)
  - **date**: 경매 날짜
  - **count**: 해당 날짜 원본 거래 건수 (샘플링 전)
  - **avg_price/min_price/max_price**: 해당 날짜 통계
  - **trades**: 개별 거래 (최대 max_per_date건, 가격 균등 샘플링)

## 사용 예시
```
GET /api/vehicle-history/aggregated?manufacturer_id=5&model_id=96
GET /api/vehicle-history/aggregated?manufacturer_id=5&model_id=96&trim_id=3357
GET /api/vehicle-history/aggregated?manufacturer_id=5&model_id=96&exclude_date=2025-11-27
```
    """,
    response_model=AggregatedHistoryResponse,
    responses={
        200: {
            "description": "집계 결과 반환",
            "content": {
                "application/json": {
                    "example": {
                        "summary": {
                            "total_count": 85,
                            "date_count": 12,
                            "min_price": 2500,
                            "max_price": 4200,
                            "avg_price": 3150.8
                        },
                        "data": [
                            {
                                "date": "2025-10-15",
                                "count": 8,
                                "avg_price": 3100.0,
                                "min_price": 2800,
                                "max_price": 3400,
                                "trades": [
                                    {"price": 2800, "km": 52000, "year": 2022, "score": "B / B"},
                                    {"price": 3100, "km": 38000, "year": 2023, "score": "A / B"},
                                    {"price": 3400, "km": 25000, "year": 2023, "score": "A / A"}
                                ]
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
                    "example": {"detail": "manufacturer_id와 model_id는 필수입니다"}
                }
            }
        },
        500: {
            "description": "서버 내부 오류",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "example": {"detail": "집계 실패: Database connection error"}
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
def get_aggregated_history(
    manufacturer_id: str = Query(
        ...,
        description="제조사 ID (필수). car_models.json 기준. 예: 현대=5, 기아=2, 벤츠=6",
        example="5"
    ),
    model_id: str = Query(
        ...,
        description="모델 ID (필수). car_models.json 기준. 예: 그랜저=96, K5=38",
        example="96"
    ),
    trim_id: Optional[str] = Query(
        None,
        description="트림 ID (선택). 없으면 모델 전체 데이터 조회. 예: 디 올뉴그랜저=3357",
        example="3357"
    ),
    min_dates: int = Query(
        5,
        ge=1,
        le=30,
        description="최소 확보할 날짜 수 (1-30)",
        example=5
    ),
    max_per_date: int = Query(
        10,
        ge=1,
        le=50,
        description="날짜별 최대 거래 건수 (1-50)",
        example=10
    ),
    max_total: int = Query(
        100,
        ge=10,
        le=500,
        description="전체 최대 거래 건수 (10-500)",
        example=100
    ),
    months: int = Query(
        12,
        ge=1,
        le=36,
        description="조회 기간 개월 수 (1-36)",
        example=12
    ),
    exclude_date: Optional[str] = Query(
        None,
        description="제외할 날짜 (현재 경매일, YYYY-MM-DD 형식)",
        example="2025-11-27",
        pattern=r"^\d{4}-\d{2}-\d{2}$"
    ),
):
    if not settings.SUPABASE_ENABLED:
        raise HTTPException(status_code=503, detail="Supabase가 비활성화되어 있습니다")

    try:
        from app.repositories import auction_records_repo

        result = auction_records_repo.get_aggregated_history(
            manufacturer_id=manufacturer_id,
            model_id=model_id,
            trim_id=trim_id,
            min_dates=min_dates,
            max_per_date=max_per_date,
            max_total=max_total,
            months=months,
            exclude_date=exclude_date,
        )

        return AggregatedHistoryResponse(**result)

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"집계 실패: {exc}") from exc
