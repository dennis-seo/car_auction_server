"""
인증 API 엔드포인트

Google OAuth 로그인 및 사용자 정보 조회
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.utils.auth import (
    verify_google_token,
    verify_google_access_token,
    create_access_token,
    get_current_user,
)
from app.repositories import users_repo
from app.core.rate_limiter import limiter, RateLimits

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["인증"])


# ===== Request/Response 스키마 =====

class GoogleLoginRequest(BaseModel):
    """Google 로그인 요청 (id_token 또는 access_token 중 하나 필수)"""
    id_token: Optional[str] = Field(None, description="Google ID Token (GoogleLogin 컴포넌트)")
    access_token: Optional[str] = Field(None, description="Google Access Token (useGoogleLogin 훅)")


class TokenResponse(BaseModel):
    """토큰 응답 (refresh용)"""
    access_token: str = Field(..., description="JWT 액세스 토큰")
    token_type: str = Field(default="bearer", description="토큰 타입")


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
    description="""
Google 토큰을 검증하고 JWT 액세스 토큰을 발급합니다. 신규 사용자는 자동으로 회원가입됩니다.

**지원 토큰 타입:**
- `id_token`: GoogleLogin 컴포넌트에서 제공하는 ID Token
- `access_token`: useGoogleLogin 훅에서 제공하는 Access Token (커스텀 버튼 사용 시)

둘 중 하나만 전송하면 됩니다.

**Rate Limit:** IP당 분당 10회
"""
)
@limiter.limit(RateLimits.AUTH_GOOGLE)
async def google_login(request: Request, login_request: GoogleLoginRequest):
    """
    Google OAuth 로그인

    1. Google Token 검증 (id_token 또는 access_token)
    2. 사용자 조회 또는 생성
    3. JWT 액세스 토큰 발급
    """
    logger.info("Google login attempt started")

    # id_token과 access_token 둘 다 없는 경우
    if not login_request.id_token and not login_request.access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="id_token 또는 access_token 중 하나를 제공해야 합니다"
        )

    # Google 토큰 검증 (id_token 우선)
    if login_request.id_token:
        google_user = verify_google_token(login_request.id_token)
        logger.info("Google ID token verified for: %s", google_user.email)
    else:
        google_user = verify_google_access_token(login_request.access_token)
        logger.info("Google access token verified for: %s", google_user.email)

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
    description="""
현재 로그인한 사용자의 정보를 조회합니다.

**Rate Limit:** IP당 분당 30회
"""
)
@limiter.limit(RateLimits.AUTH_ME)
async def get_me(request: Request, current_user: dict = Depends(get_current_user)):
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


class LogoutResponse(BaseModel):
    """로그아웃 응답"""
    success: bool = Field(..., description="로그아웃 성공 여부")
    message: str = Field(..., description="응답 메시지")


@router.post(
    "/logout",
    response_model=LogoutResponse,
    summary="로그아웃",
    description="""
현재 로그인한 사용자를 로그아웃합니다. 이후 해당 토큰은 사용할 수 없습니다.

**Rate Limit:** IP당 분당 10회
"""
)
@limiter.limit(RateLimits.AUTH_LOGOUT)
async def logout(request: Request, current_user: dict = Depends(get_current_user)):
    """
    로그아웃 처리

    현재 사용자의 last_logout_at 시간을 업데이트하여
    기존에 발급된 모든 토큰을 무효화합니다.
    """
    try:
        users_repo.update_last_logout(current_user["id"])
        logger.info("User logged out: id=%s email=%s", current_user["id"], current_user["email"])
        return LogoutResponse(
            success=True,
            message="로그아웃되었습니다"
        )
    except Exception as e:
        logger.error("Logout failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="로그아웃 처리 중 오류가 발생했습니다"
        )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="토큰 갱신",
    description="""
현재 유효한 토큰으로 새 토큰을 발급받습니다.

**사용 시나리오:**
- 토큰 만료 전에 호출하여 세션을 유지
- 클라이언트에서 주기적으로 호출하여 자동 갱신

**주의:** 만료된 토큰으로는 갱신할 수 없습니다.

**Rate Limit:** IP당 분당 20회
"""
)
@limiter.limit(RateLimits.AUTH_REFRESH)
async def refresh_token(request: Request, current_user: dict = Depends(get_current_user)):
    """
    토큰 갱신

    현재 유효한 토큰으로 새 토큰을 발급받습니다.
    토큰 만료 전에 호출하여 세션을 유지할 수 있습니다.
    """
    new_token = create_access_token(
        user_id=current_user["id"],
        email=current_user["email"]
    )
    logger.info("Token refreshed for user: id=%s email=%s", current_user["id"], current_user["email"])
    return TokenResponse(
        access_token=new_token,
        token_type="bearer"
    )