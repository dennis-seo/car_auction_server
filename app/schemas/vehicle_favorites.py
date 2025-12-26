"""
차량 즐겨찾기 API 스키마

특정 경매 차량 즐겨찾기 요청/응답 스키마 정의
"""

from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.auction import VehicleRecord


class VehicleFavoriteCreate(BaseModel):
    """차량 즐겨찾기 생성 요청"""

    record_id: int = Field(..., description="차량 레코드 ID", examples=[12345])


class VehicleFavoriteResponse(BaseModel):
    """차량 즐겨찾기 응답"""

    id: str = Field(..., description="즐겨찾기 고유 ID")
    record_id: int = Field(..., description="차량 레코드 ID")
    created_at: str = Field(..., description="생성 시간")


class VehicleFavoriteWithVehicle(BaseModel):
    """차량 정보를 포함한 즐겨찾기 응답"""

    id: str = Field(..., description="즐겨찾기 고유 ID")
    record_id: int = Field(..., description="차량 레코드 ID")
    created_at: str = Field(..., description="생성 시간")
    vehicle: Optional[VehicleRecord] = Field(None, description="차량 상세 정보")


class VehicleFavoriteListResponse(BaseModel):
    """차량 즐겨찾기 목록 응답"""

    items: List[VehicleFavoriteWithVehicle] = Field(..., description="즐겨찾기 목록")
    total: int = Field(..., description="총 개수")


class VehicleFavoriteIdsResponse(BaseModel):
    """차량 즐겨찾기 ID 목록 응답 (경량 API)"""

    record_ids: List[int] = Field(..., description="즐겨찾기한 차량 record_id 목록")
    total: int = Field(..., description="총 개수")
