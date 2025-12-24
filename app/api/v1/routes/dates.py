from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.services.csv_service import list_available_dates


router = APIRouter(tags=["Dates"])


@router.get(
    "/dates",
    response_model=list[str],
    summary="경매 날짜 목록 조회",
    description="""
사용 가능한 경매 날짜 목록을 조회합니다.

## 파라미터
- `limit`: 반환할 최대 날짜 수 (선택). 지정하지 않으면 전체 목록 반환

## 응답
- 날짜 목록 (YYYY-MM-DD 형식, 최신순 정렬)

## 예시
```
GET /api/dates        → 전체 날짜 목록
GET /api/dates?limit=5  → 최근 5개 날짜만
```
    """,
)
def get_dates(
    limit: Optional[int] = Query(
        None,
        ge=1,
        le=1000,
        description="반환할 최대 날짜 수 (1-1000). 미지정 시 전체 반환",
        example=10
    )
) -> list[str]:
    try:
        return list_available_dates(limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="날짜 목록 조회 실패") from exc
