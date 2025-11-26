from typing import List, Optional
from pydantic import BaseModel, Field


class AuctionItem(BaseModel):
    """경매 차량 정보"""
    post_title: Optional[str] = Field(None, alias="Post Title", description="게시글 제목")
    sell_number: str = Field("", description="출품 번호", example="0644")
    car_number: str = Field("", description="차량 번호", example="165하8219")
    color: str = Field("", description="색상", example="비크블랙")
    fuel: str = Field("", description="연료 타입", example="가솔린")
    image: str = Field("", description="차량 이미지 URL", example="https://imgmk.lotteautoauction.net/AU_CAR_IMG_ORG_HP/202509/KS20250926005628.JPG")
    km: str = Field("", description="주행거리", example="85882")
    price: str = Field("", description="가격 (만원 단위)", example="3190")
    title: str = Field("", description="차량 모델명", example="THE ALL NEW GENESIS G80 (G) 2.5T")
    trans: str = Field("", description="변속기", example="오토")
    year: str = Field("", description="연식", example="2022")
    auction_name: str = Field("", description="경매장 이름", example="롯데 경매장")
    vin: str = Field("", description="차대번호", example="KMTGB41CBNU116836")
    score: str = Field("", description="평가 등급", example="A / D")

    class Config:
        populate_by_name = True


class AuctionResponse(BaseModel):
    """경매 데이터 응답"""
    date: str = Field(..., description="경매 날짜 (YYMMDD 형식)", example="250929")
    source_filename: str = Field(..., description="원본 파일명", example="auction_data_250929.csv")
    row_count: int = Field(..., description="총 차량 수", example=150)
    items: List[AuctionItem] = Field(..., description="차량 목록")
