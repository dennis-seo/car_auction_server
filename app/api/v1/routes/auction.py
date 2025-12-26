import logging

from fastapi import APIRouter, Path, Query

from app.core.exceptions import AppException, NotFoundError
from app.schemas.auction import AuctionResponse
from app.services.csv_service import get_auction_data_for_date_paginated

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Auction"])


@router.get(
    "/auction/{date}",
    summary="경매 데이터 조회 (JSON)",
    description="""
지정된 날짜의 경매 데이터를 JSON 형식으로 반환합니다.

## 페이징
- `page`: 페이지 번호 (1부터 시작, 기본값: 1)
- `limit`: 페이지당 항목 수 (기본값: 100, 최대: 500)

## 응답
- `pagination`: 페이지네이션 정보 (page, limit, total_items, total_pages, has_next, has_prev)
- `items`: 차량 목록 (각 항목에 `id` 필드 포함)
""",
    response_model=AuctionResponse,
    responses={
        200: {"description": "경매 데이터 반환"},
        404: {"description": "해당 날짜의 데이터를 찾을 수 없음"},
        500: {"description": "서버 내부 오류"},
    },
)
def get_auction(
    date: str = Path(
        ...,
        description="조회할 날짜 (YYMMDD 형식, 예: 251126)",
        example="251126",
        min_length=6,
        max_length=6,
    ),
    page: int = Query(
        1,
        description="페이지 번호 (1부터 시작)",
        ge=1,
        example=1,
    ),
    limit: int = Query(
        100,
        description="페이지당 항목 수 (최대 500)",
        ge=1,
        le=500,
        example=100,
    ),
):
    """경매 데이터를 JSON으로 반환 (페이징 지원)"""
    try:
        result = get_auction_data_for_date_paginated(date, page=page, limit=limit)
        if result is None:
            raise NotFoundError(message="해당 날짜의 데이터를 찾을 수 없습니다")
        return result
    except (NotFoundError, AppException):
        raise
    except Exception as exc:
        logger.error("경매 데이터 조회 실패 (date=%s): %s", date, exc, exc_info=True)
        raise AppException(message="데이터 조회에 실패했습니다") from exc
