from typing import List, Optional
from pydantic import BaseModel, Field


class VehicleRecord(BaseModel):
    """
    정규화된 차량 레코드

    경매에 출품된 차량의 상세 정보를 담고 있습니다.
    제조사, 모델, 트림 정보는 car_models.json 기준으로 정규화되어 있습니다.
    """
    id: Optional[int] = Field(None, description="레코드 고유 ID", example=12345)

    # 차량 식별
    vin: Optional[str] = Field(None, description="차대번호 (Vehicle Identification Number)", example="KMHD341CBNU123456")
    car_number: str = Field("", description="차량 등록번호", example="123가4567")

    # 경매 정보
    auction_date: str = Field("", description="경매 날짜 (YYYY-MM-DD 형식)", example="2025-11-27")
    sell_number: Optional[int] = Field(None, description="경매 출품번호", example=644)
    auction_house: Optional[str] = Field(None, description="경매장명", example="롯데 경매장")

    # JSON 기준 ID (car_models.json 참조)
    manufacturer_id: Optional[str] = Field(
        None,
        description="제조사 ID (car_models.json 기준). 국산: 1-5, 146 / 수입: 6-145",
        example="5"
    )
    model_id: Optional[str] = Field(
        None,
        description="모델 ID (car_models.json 기준)",
        example="96"
    )
    trim_id: Optional[str] = Field(
        None,
        description="트림 ID (car_models.json 기준)",
        example="3357"
    )

    # 정규화된 필드
    manufacturer: Optional[str] = Field(
        None,
        description="제조사명. 국산: 현대, 기아, 제네시스, 르노삼성, 쉐보레, 쌍용 / 수입: 벤츠, BMW, 아우디 등",
        example="현대"
    )
    model: Optional[str] = Field(None, description="모델명", example="그랜저")
    sub_model: Optional[str] = Field(None, description="세부모델 (세대 구분)", example="IG")
    trim: Optional[str] = Field(None, description="트림명", example="디 올뉴그랜저 (22년~현재)")
    year: Optional[int] = Field(None, description="연식 (년도)", example=2023, ge=1990, le=2030)
    fuel_type: Optional[str] = Field(
        None,
        description="연료 타입: 가솔린, 디젤, LPG, 전기, 하이브리드, 플러그인하이브리드, 수소",
        example="가솔린"
    )
    transmission: Optional[str] = Field(
        None,
        description="변속기 타입: 자동, 수동",
        example="자동"
    )
    engine_cc: Optional[int] = Field(None, description="배기량 (cc)", example=2497)
    usage_type: Optional[str] = Field(
        None,
        description="차량 용도: 자가용, 렌터카, 영업용",
        example="자가용"
    )

    # 상태 정보
    km: Optional[int] = Field(None, description="주행거리 (km)", example=45000)
    price: Optional[int] = Field(None, description="낙찰가 (만원 단위)", example=3190)
    score: Optional[str] = Field(
        None,
        description="차량 평가등급. 형식: '외관등급 / 내관등급' (예: A/B, 1/2 등)",
        example="A / B"
    )
    color: Optional[str] = Field(None, description="차량 외관 색상", example="어비스블랙")
    image_url: Optional[str] = Field(
        None,
        description="차량 이미지 URL",
        example="https://imgmk.lotteautoauction.net/AU_CAR_IMG_ORG_HP/202511/KS20251126001234.JPG"
    )

    class Config:
        from_attributes = True
        json_schema_extra = {
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


class VehicleListResponse(BaseModel):
    """
    차량 목록 응답

    페이지네이션을 지원하는 차량 검색 결과입니다.
    """
    total: int = Field(..., description="검색 조건에 맞는 전체 차량 수", example=1523)
    limit: int = Field(..., description="요청한 최대 조회 수", example=100)
    offset: int = Field(..., description="요청한 시작 위치 (0부터 시작)", example=0)
    items: List[VehicleRecord] = Field(..., description="차량 목록")

    class Config:
        json_schema_extra = {
            "example": {
                "total": 1523,
                "limit": 100,
                "offset": 0,
                "items": [
                    {
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
                ]
            }
        }


class ErrorResponse(BaseModel):
    """API 에러 응답"""
    detail: str = Field(..., description="에러 상세 메시지", example="차량을 찾을 수 없습니다")


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
