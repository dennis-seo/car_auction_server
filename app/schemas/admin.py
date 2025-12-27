"""
Admin API 스키마

관리자용 API 요청/응답 스키마 정의
"""

from typing import List, Optional
from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.auction import Pagination


class UserRoleEnum(str, Enum):
    """사용자 역할 열거형 (API 문서용)"""
    master = "master"
    bidder = "bidder"
    premium = "premium"
    free = "free"


# ===== 사용자 관리 =====

class UserSummary(BaseModel):
    """사용자 요약 정보 (목록용)"""
    id: str = Field(..., description="사용자 UUID")
    email: str = Field(..., description="이메일")
    name: Optional[str] = Field(None, description="이름")
    profile_image: Optional[str] = Field(None, description="프로필 이미지 URL")
    role: str = Field(..., description="역할 (master, bidder, premium, free)")
    created_at: Optional[str] = Field(None, description="가입일시")
    last_login_at: Optional[str] = Field(None, description="마지막 로그인")


class UserDetail(UserSummary):
    """사용자 상세 정보"""
    role_updated_at: Optional[str] = Field(None, description="역할 변경일시")
    role_updated_by: Optional[str] = Field(None, description="역할 변경자 UUID")


class UserListResponse(BaseModel):
    """사용자 목록 응답"""
    pagination: Pagination = Field(..., description="페이지네이션 정보")
    items: List[UserSummary] = Field(..., description="사용자 목록")


class UpdateRoleRequest(BaseModel):
    """역할 변경 요청"""
    role: UserRoleEnum = Field(..., description="변경할 역할")

    class Config:
        json_schema_extra = {
            "example": {
                "role": "premium"
            }
        }


class UpdateRoleResponse(BaseModel):
    """역할 변경 응답"""
    id: str = Field(..., description="사용자 UUID")
    email: str = Field(..., description="이메일")
    name: Optional[str] = Field(None, description="이름")
    role: str = Field(..., description="변경된 역할")
    role_updated_at: Optional[str] = Field(None, description="역할 변경일시")
    role_updated_by: Optional[str] = Field(None, description="역할 변경자 UUID")


# ===== 통계 =====

class RoleStats(BaseModel):
    """역할별 사용자 수"""
    master: int = Field(0, description="마스터 수")
    bidder: int = Field(0, description="입찰업체 수")
    premium: int = Field(0, description="유료 사용자 수")
    free: int = Field(0, description="무료 사용자 수")


class SignupStats(BaseModel):
    """가입 통계"""
    today: int = Field(0, description="오늘 가입")
    this_week: int = Field(0, description="이번 주 가입")
    this_month: int = Field(0, description="이번 달 가입")


class UserStatsResponse(BaseModel):
    """사용자 통계 응답"""
    total_users: int = Field(..., description="전체 사용자 수")
    by_role: RoleStats = Field(..., description="역할별 사용자 수")
    recent_signups: SignupStats = Field(..., description="최근 가입 통계")

    class Config:
        json_schema_extra = {
            "example": {
                "total_users": 150,
                "by_role": {
                    "master": 2,
                    "bidder": 10,
                    "premium": 25,
                    "free": 113
                },
                "recent_signups": {
                    "today": 5,
                    "this_week": 23,
                    "this_month": 67
                }
            }
        }
