from fastapi import APIRouter, HTTPException, Path

from app.services.csv_service import get_auction_data_for_date
from app.schemas.auction import AuctionResponse


router = APIRouter(tags=["Auction"])


@router.get(
    "/auction/{date}",
    summary="경매 데이터 조회 (JSON)",
    description="지정된 날짜의 경매 데이터를 JSON 형식으로 반환합니다. 날짜 형식은 YYMMDD입니다.",
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
):
    """경매 데이터를 JSON으로 반환"""
    try:
        result = get_auction_data_for_date(date)
        if result is None:
            raise HTTPException(status_code=404, detail="해당 날짜의 데이터를 찾을 수 없습니다")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="데이터 조회 실패") from exc
