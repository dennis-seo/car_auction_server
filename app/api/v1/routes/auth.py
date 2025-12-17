"""
인증 API 엔드포인트

Google OAuth 로그인 및 사용자 정보 조회
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.utils.auth import (
    verify_google_token,
    create_access_token,
    get_current_user,
)
from app.repositories import users_repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["인증"])


# ===== Request/Response 스키마 =====

class GoogleLoginRequest(BaseModel):
    """Google 로그인 요청"""
    id_token: str = Field(..., description="Google에서 받은 ID Token")


class AuthResponse(BaseModel):
    """로그인 응답"""
    access_token: str = Field(..., description="JWT 액세스 토큰")
    token_type: str = Field(default="bearer", description="토큰 타입")
    user: "UserResponse" = Field(..., description="사용자 정보")


class UserResponse(BaseModel):
    """사용자 정보 응답"""
    id: str = Field(..., description="사용자 UUID")
    email: str = Field(..., description="이메일")
    name: Optional[str] = Field(None, description="이름")
    profile_image: Optional[str] = Field(None, description="프로필 이미지 URL")
    created_at: Optional[str] = Field(None, description="가입일")


# Forward reference 해결
AuthResponse.model_rebuild()


# ===== API 엔드포인트 =====

@router.post(
    "/google",
    response_model=AuthResponse,
    summary="Google 로그인",
    description="Google ID Token을 검증하고 JWT 액세스 토큰을 발급합니다. 신규 사용자는 자동으로 회원가입됩니다."
)
async def google_login(request: GoogleLoginRequest):
    """
    Google OAuth 로그인

    1. Google ID Token 검증
    2. 사용자 조회 또는 생성
    3. JWT 액세스 토큰 발급
    """
    logger.info("Google login attempt started")

    # Google 토큰 검증
    google_user = verify_google_token(request.id_token)
    logger.info("Google token verified for: %s", google_user.email)

    # 사용자 조회 또는 생성
    try:
        user = users_repo.find_or_create(
            google_sub=google_user.sub,
            email=google_user.email,
            name=google_user.name,
            profile_image=google_user.picture
        )
        logger.info("User found/created: id=%s email=%s", user.get("id"), user.get("email"))
    except Exception as e:
        logger.error("User find_or_create failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"사용자 처리 중 오류가 발생했습니다: {str(e)}"
        )

    # JWT 토큰 생성
    access_token = create_access_token(
        user_id=user["id"],
        email=user["email"]
    )

    return AuthResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            id=user["id"],
            email=user["email"],
            name=user.get("name"),
            profile_image=user.get("profile_image"),
            created_at=user.get("created_at")
        )
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="내 정보 조회",
    description="현재 로그인한 사용자의 정보를 조회합니다."
)
async def get_me(current_user: dict = Depends(get_current_user)):
    """
    현재 로그인한 사용자 정보 조회
    """
    user = users_repo.get_by_id(current_user["id"])

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다"
        )

    return UserResponse(
        id=user["id"],
        email=user["email"],
        name=user.get("name"),
        profile_image=user.get("profile_image"),
        created_at=user.get("created_at")
    )