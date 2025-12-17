"""
인증 유틸리티 모듈

Google OAuth ID Token 검증 및 JWT 토큰 생성/검증
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from app.core.config import settings


logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


class GoogleTokenPayload:
    """Google ID Token에서 추출한 사용자 정보"""
    def __init__(self, sub: str, email: str, name: Optional[str], picture: Optional[str]):
        self.sub = sub
        self.email = email
        self.name = name
        self.picture = picture


def verify_google_token(token: str) -> GoogleTokenPayload:
    """
    Google ID Token 검증

    Args:
        token: 클라이언트에서 받은 Google ID Token

    Returns:
        GoogleTokenPayload: 검증된 사용자 정보

    Raises:
        HTTPException: 토큰이 유효하지 않은 경우
    """
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google Client ID가 설정되지 않았습니다"
        )

    try:
        idinfo = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID
        )

        return GoogleTokenPayload(
            sub=idinfo["sub"],
            email=idinfo["email"],
            name=idinfo.get("name"),
            picture=idinfo.get("picture")
        )
    except ValueError as e:
        logger.warning("Google token verification failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 Google 토큰입니다"
        )


def create_access_token(user_id: str, email: str) -> str:
    """
    JWT 액세스 토큰 생성

    Args:
        user_id: 사용자 UUID
        email: 사용자 이메일

    Returns:
        JWT 토큰 문자열
    """
    if not settings.JWT_SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY가 설정되지 않았습니다")

    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "email": email,
        "exp": expire,
        "iat": datetime.now(timezone.utc)
    }

    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    JWT 액세스 토큰 디코딩 및 검증

    Args:
        token: JWT 토큰 문자열

    Returns:
        토큰 페이로드 딕셔너리

    Raises:
        HTTPException: 토큰이 유효하지 않거나 만료된 경우
    """
    if not settings.JWT_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT 설정이 완료되지 않았습니다"
        )

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="토큰이 만료되었습니다"
        )
    except jwt.InvalidTokenError as e:
        logger.warning("JWT verification failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 토큰입니다"
        )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    """
    현재 인증된 사용자 정보를 반환하는 의존성

    사용법:
        @router.get("/me")
        async def get_me(user: dict = Depends(get_current_user)):
            return user
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증이 필요합니다",
            headers={"WWW-Authenticate": "Bearer"}
        )

    payload = decode_access_token(credentials.credentials)
    return {
        "id": payload["sub"],
        "email": payload["email"]
    }


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[dict]:
    """
    선택적 인증 - 토큰이 있으면 사용자 정보 반환, 없으면 None

    인증이 필수가 아닌 엔드포인트에서 사용
    """
    if credentials is None:
        return None

    try:
        payload = decode_access_token(credentials.credentials)
        return {
            "id": payload["sub"],
            "email": payload["email"]
        }
    except HTTPException:
        return None