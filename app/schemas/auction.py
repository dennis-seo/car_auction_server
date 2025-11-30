from typing import List, Optional
from pydantic import BaseModel, Field


class VehicleRecord(BaseModel):
    """정규화된 차량 레코드"""
    id: Optional[int] = Field(None, description="레코드 ID")

    # 차량 식별
    vin: Optional[str] = Field(None, description="차대번호")
    car_number: str = Field("", description="차량번호")

    # 경매 정보
    auction_date: str = Field("", description="경매 날짜 (YYYY-MM-DD)")
    sell_number: Optional[int] = Field(None, description="출품번호")
    auction_house: Optional[str] = Field(None, description="경매장명")

    # JSON 기준 ID
    manufacturer_id: Optional[str] = Field(None, description="제조사 ID")
    model_id: Optional[str] = Field(None, description="모델 ID")
    trim_id: Optional[str] = Field(None, description="트림 ID")

    # 정규화된 필드
    manufacturer: Optional[str] = Field(None, description="제조사")
    model: Optional[str] = Field(None, description="모델명")
    sub_model: Optional[str] = Field(None, description="세부모델")
    trim: Optional[str] = Field(None, description="트림")
    year: Optional[int] = Field(None, description="연식")
    fuel_type: Optional[str] = Field(None, description="연료 타입")
    transmission: Optional[str] = Field(None, description="변속기")
    engine_cc: Optional[int] = Field(None, description="배기량(cc)")
    usage_type: Optional[str] = Field(None, description="용도")

    # 상태 정보
    km: Optional[int] = Field(None, description="주행거리")
    price: Optional[int] = Field(None, description="낙찰가(만원)")
    score: Optional[str] = Field(None, description="평가등급")
    color: Optional[str] = Field(None, description="색상")
    image_url: Optional[str] = Field(None, description="이미지 URL")

    class Config:
        from_attributes = True


class VehicleQueryParams(BaseModel):
    """차량 조회 쿼리 파라미터"""
    manufacturer_id: Optional[str] = Field(None, description="제조사 ID")
    model_id: Optional[str] = Field(None, description="모델 ID")
    trim_id: Optional[str] = Field(None, description="트림 ID")
    manufacturer: Optional[str] = Field(None, description="제조사명")
    model: Optional[str] = Field(None, description="모델명")
    year_from: Optional[int] = Field(None, description="연식 시작")
    year_to: Optional[int] = Field(None, description="연식 끝")
    date_from: Optional[str] = Field(None, description="경매일 시작 (YYYY-MM-DD)")
    date_to: Optional[str] = Field(None, description="경매일 끝 (YYYY-MM-DD)")
    limit: int = Field(100, ge=1, le=1000, description="최대 조회 수")
    offset: int = Field(0, ge=0, description="오프셋")


class VehicleListResponse(BaseModel):
    """차량 목록 응답"""
    total: int = Field(..., description="전체 개수")
    limit: int = Field(..., description="요청 limit")
    offset: int = Field(..., description="요청 offset")
    items: List[VehicleRecord] = Field(..., description="차량 목록")


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
