"""
app/utils/auth.py 통합 테스트
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import jwt
from fastapi import HTTPException


class TestCreateAccessToken:
    """JWT 토큰 생성 테스트"""

    def test_create_token_success(self, mock_jwt_settings):
        """정상적인 토큰 생성"""
        from app.core.config import get_settings
        get_settings.cache_clear()

        from app.utils.auth import create_access_token

        token = create_access_token(user_id="user123", email="test@example.com")

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_contains_correct_payload(self):
        """토큰 페이로드 검증 (decode_access_token 사용)"""
        from app.utils.auth import create_access_token, decode_access_token

        token = create_access_token(user_id="user123", email="test@example.com")

        # decode_access_token으로 검증
        payload = decode_access_token(token)

        assert payload["sub"] == "user123"
        assert payload["email"] == "test@example.com"
        assert "exp" in payload
        assert "iat" in payload

    def test_token_has_expiration(self):
        """토큰에 만료 시간이 있는지 검증"""
        from app.utils.auth import create_access_token, decode_access_token

        token = create_access_token(user_id="user123", email="test@example.com")

        payload = decode_access_token(token)

        # exp가 미래 시점인지 확인
        exp_time = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        assert exp_time > datetime.now(timezone.utc)


class TestDecodeAccessToken:
    """JWT 토큰 디코딩 테스트"""

    def test_decode_valid_token(self, mock_jwt_settings):
        """유효한 토큰 디코딩"""
        from app.core.config import get_settings
        get_settings.cache_clear()

        from app.utils.auth import create_access_token, decode_access_token

        token = create_access_token(user_id="user123", email="test@example.com")
        payload = decode_access_token(token)

        assert payload["sub"] == "user123"
        assert payload["email"] == "test@example.com"

    def test_decode_expired_token_raises_401(self):
        """만료된 토큰 디코딩 시 401 에러"""
        from app.core.config import settings
        from app.utils.auth import decode_access_token

        # 현재 설정된 키로 만료된 토큰 생성
        expired_payload = {
            "sub": "user123",
            "email": "test@example.com",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            "iat": datetime.now(timezone.utc) - timedelta(hours=2)
        }
        expired_token = jwt.encode(
            expired_payload,
            settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM
        )

        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(expired_token)

        assert exc_info.value.status_code == 401

    def test_decode_invalid_token_raises_401(self, mock_jwt_settings):
        """잘못된 토큰 디코딩 시 401 에러"""
        from app.core.config import get_settings
        get_settings.cache_clear()

        from app.utils.auth import decode_access_token

        with pytest.raises(HTTPException) as exc_info:
            decode_access_token("invalid.token.here")

        assert exc_info.value.status_code == 401

    def test_decode_tampered_token_raises_401(self, mock_jwt_settings):
        """변조된 토큰 디코딩 시 401 에러"""
        from app.core.config import get_settings
        get_settings.cache_clear()

        from app.utils.auth import create_access_token, decode_access_token

        token = create_access_token(user_id="user123", email="test@example.com")
        # 토큰 변조
        tampered_token = token[:-5] + "xxxxx"

        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(tampered_token)

        assert exc_info.value.status_code == 401


class TestVerifyGoogleToken:
    """Google OAuth 토큰 검증 테스트"""

    def test_verify_success(self, monkeypatch):
        """Google 토큰 검증 성공"""
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test_client_id")

        from app.core.config import get_settings
        get_settings.cache_clear()

        mock_idinfo = {
            "sub": "google_123",
            "email": "test@gmail.com",
            "name": "Test User",
            "picture": "https://example.com/photo.jpg"
        }

        with patch("google.oauth2.id_token.verify_oauth2_token", return_value=mock_idinfo):
            from app.utils.auth import verify_google_token

            result = verify_google_token("valid_google_token")

            assert result.sub == "google_123"
            assert result.email == "test@gmail.com"
            assert result.name == "Test User"
            assert result.picture == "https://example.com/photo.jpg"

    def test_verify_invalid_token_raises_401(self, monkeypatch):
        """잘못된 Google 토큰 시 401 에러"""
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test_client_id")

        from app.core.config import get_settings
        get_settings.cache_clear()

        with patch("google.oauth2.id_token.verify_oauth2_token", side_effect=ValueError("Invalid token")):
            from app.utils.auth import verify_google_token

            with pytest.raises(HTTPException) as exc_info:
                verify_google_token("invalid_token")

            assert exc_info.value.status_code == 401

    def test_missing_client_id_raises_500(self, monkeypatch):
        """GOOGLE_CLIENT_ID 미설정 시 500 에러"""
        # settings 객체를 직접 패치
        with patch("app.utils.auth.settings") as mock_settings:
            mock_settings.GOOGLE_CLIENT_ID = ""

            from app.utils.auth import verify_google_token

            with pytest.raises(HTTPException) as exc_info:
                verify_google_token("any_token")

            assert exc_info.value.status_code == 500
            assert "Client ID" in exc_info.value.detail


class TestGetCurrentUser:
    """get_current_user 의존성 테스트"""

    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self):
        """유효한 토큰으로 사용자 정보 반환"""
        from app.utils.auth import create_access_token, get_current_user
        from fastapi.security import HTTPAuthorizationCredentials

        # users_repo.get_by_id 모킹 (repositories 모듈 패치)
        mock_user = {
            "id": "user123",
            "email": "test@example.com",
            "last_logout_at": None
        }

        with patch("app.repositories.users_repo.get_by_id", return_value=mock_user):
            token = create_access_token(user_id="user123", email="test@example.com")
            credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

            result = await get_current_user(credentials)

            assert result["id"] == "user123"
            assert result["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_no_credentials_raises_401(self):
        """인증 정보 없을 때 401 에러"""
        from app.utils.auth import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(None)

        assert exc_info.value.status_code == 401
        assert "인증이 필요" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_logged_out_token_rejected(self):
        """로그아웃된 토큰 거부"""
        from app.utils.auth import create_access_token, get_current_user
        from fastapi.security import HTTPAuthorizationCredentials

        # 미래 시점에 로그아웃한 사용자 (토큰 발급 이후)
        logout_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        mock_user = {
            "id": "user123",
            "email": "test@example.com",
            "last_logout_at": logout_time
        }

        with patch("app.repositories.users_repo.get_by_id", return_value=mock_user):
            token = create_access_token(user_id="user123", email="test@example.com")
            credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials)

            assert exc_info.value.status_code == 401
            assert "로그아웃" in exc_info.value.detail
