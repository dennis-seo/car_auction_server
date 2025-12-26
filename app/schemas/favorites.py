"""
즐겨찾기 API 스키마

제조사/모델/트림 즐겨찾기 요청/응답 스키마 정의
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


FavoriteType = Literal["manufacturer", "model", "trim"]


class FavoriteCreate(BaseModel):
    """즐겨찾기 생성 요청"""

    favorite_type: FavoriteType = Field(..., description="즐겨찾기 타입")
    manufacturer_id: str = Field(..., description="제조사 ID", examples=["5"])
    model_id: Optional[str] = Field(None, description="모델 ID", examples=["96"])
    trim_id: Optional[str] = Field(None, description="트림 ID", examples=["3357"])

    # 표시용 라벨 (선택)
    manufacturer_label: Optional[str] = Field(
        None, description="제조사명", examples=["현대"]
    )
    model_label: Optional[str] = Field(
        None, description="모델명", examples=["그랜저"]
    )
    trim_label: Optional[str] = Field(
        None, description="트림명", examples=["디 올뉴그랜저"]
    )

    @field_validator("model_id", "trim_id", mode="before")
    @classmethod
    def empty_str_to_none(cls, v):
        """빈 문자열을 None으로 변환"""
        return None if v == "" else v

    def validate_type_fields(self) -> None:
        """타입에 맞는 필드 검증"""
        if self.favorite_type == "manufacturer":
            if self.model_id is not None or self.trim_id is not None:
                raise ValueError(
                    "manufacturer 타입은 model_id, trim_id가 null이어야 합니다"
                )
        elif self.favorite_type == "model":
            if self.model_id is None:
                raise ValueError("model 타입은 model_id가 필수입니다")
            if self.trim_id is not None:
                raise ValueError("model 타입은 trim_id가 null이어야 합니다")
        elif self.favorite_type == "trim":
            if self.model_id is None or self.trim_id is None:
                raise ValueError("trim 타입은 model_id, trim_id가 필수입니다")


class FavoriteResponse(BaseModel):
    """즐겨찾기 응답"""

    id: str = Field(..., description="즐겨찾기 고유 ID")
    favorite_type: FavoriteType = Field(..., description="즐겨찾기 타입")
    manufacturer_id: str = Field(..., description="제조사 ID")
    model_id: Optional[str] = Field(None, description="모델 ID")
    trim_id: Optional[str] = Field(None, description="트림 ID")
    manufacturer_label: Optional[str] = Field(None, description="제조사명")
    model_label: Optional[str] = Field(None, description="모델명")
    trim_label: Optional[str] = Field(None, description="트림명")
    created_at: str = Field(..., description="생성 시간")


class FavoriteListResponse(BaseModel):
    """즐겨찾기 목록 응답"""

    items: List[FavoriteResponse] = Field(..., description="즐겨찾기 목록")
    total: int = Field(..., description="총 개수")
