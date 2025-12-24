"""
car_auction_server 테스트를 위한 공통 fixture
"""
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# 프로젝트 루트를 path에 추가
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ========== App Fixtures ==========

@pytest.fixture(scope="session")
def app():
    """FastAPI 앱 인스턴스 생성"""
    # 테스트용 기본 환경변수 설정
    os.environ.setdefault("SUPABASE_ENABLED", "false")
    os.environ.setdefault("JWT_SECRET_KEY", "test_secret_key_for_testing")
    os.environ.setdefault("GOOGLE_CLIENT_ID", "test_client_id")
    os.environ.setdefault("ADMIN_TOKEN", "test_admin_token")

    from app.main import create_app
    return create_app()


@pytest.fixture
def client(app):
    """FastAPI TestClient 생성"""
    with TestClient(app) as c:
        yield c


# ========== Settings Fixtures ==========

@pytest.fixture(autouse=True)
def reset_settings_cache():
    """각 테스트 전에 settings 캐시 초기화"""
    from app.core.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def mock_supabase_disabled(monkeypatch):
    """Supabase 비활성화"""
    monkeypatch.setenv("SUPABASE_ENABLED", "false")


@pytest.fixture
def mock_supabase_enabled(monkeypatch):
    """테스트용 Supabase 활성화"""
    monkeypatch.setenv("SUPABASE_ENABLED", "true")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test_service_key")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test_anon_key")
    monkeypatch.setenv("SUPABASE_TABLE", "auction_data")


@pytest.fixture
def mock_jwt_settings(monkeypatch):
    """JWT 테스트 설정"""
    monkeypatch.setenv("JWT_SECRET_KEY", "test_jwt_secret_key")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "60")


@pytest.fixture
def admin_headers():
    """Admin API용 인증 헤더"""
    return {"Authorization": "Bearer test_admin_token"}


@pytest.fixture
def auth_headers(mock_jwt_settings):
    """사용자 인증용 JWT 헤더 생성"""
    from app.core.config import get_settings
    get_settings.cache_clear()

    from app.utils.auth import create_access_token
    token = create_access_token(user_id="test_user_id", email="test@example.com")
    return {"Authorization": f"Bearer {token}"}


# ========== File System Fixtures ==========

@pytest.fixture
def temp_sources_dir(tmp_path, monkeypatch):
    """임시 sources 디렉토리 생성"""
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()
    monkeypatch.setenv("SOURCES_DIR", str(sources_dir))
    return sources_dir


@pytest.fixture
def sample_csv_content():
    """테스트용 샘플 CSV 내용 (bytes)"""
    return b'''Post Title,sell_number,car_number,color,fuel,image,km,price,title,trans,year,auction_name,vin,score
[\xed\x98\x84\xeb\x8c\x80] \xea\xb7\xb8\xeb\x9e\x9c\xec\xa0\x80 IG 2.5,0644,123\xea\xb0\x804567,\xeb\xb8\x94\xeb\x9e\x99,\xea\xb0\x80\xec\x86\x94\xeb\xa6\xb0,https://example.com/img.jpg,45000,3190,\xea\xb7\xb8\xeb\x9e\x9c\xec\xa0\x80 IG,\xec\x98\xa4\xed\x86\xa0,2022,\xeb\xa1\xaf\xeb\x8d\xb0 \xea\xb2\xbd\xeb\xa7\xa4\xec\x9e\xa5,KMHD341CBNU123456,A / B
'''


@pytest.fixture
def sample_csv_file(temp_sources_dir, sample_csv_content):
    """임시 디렉토리에 샘플 CSV 파일 생성"""
    filepath = temp_sources_dir / "auction_data_251125.csv"
    filepath.write_bytes(sample_csv_content)
    return filepath


# ========== Mock Fixtures ==========

@pytest.fixture
def mock_google_verify(mocker):
    """Google OAuth 토큰 검증 모킹"""
    mock_idinfo = {
        "sub": "google_user_123",
        "email": "test@example.com",
        "name": "Test User",
        "picture": "https://example.com/photo.jpg"
    }
    mocker.patch(
        "google.oauth2.id_token.verify_oauth2_token",
        return_value=mock_idinfo
    )
    return mock_idinfo


@pytest.fixture
def mock_google_verify_fail(mocker):
    """Google OAuth 검증 실패 모킹"""
    mocker.patch(
        "google.oauth2.id_token.verify_oauth2_token",
        side_effect=ValueError("Invalid token")
    )


@pytest.fixture
def mock_users_repo(mocker):
    """users_repo 모킹"""
    mock_user = {
        "id": "test_user_id",
        "google_sub": "google_user_123",
        "email": "test@example.com",
        "name": "Test User",
        "profile_image": "https://example.com/photo.jpg",
        "created_at": "2024-01-01T00:00:00Z",
        "last_logout_at": None
    }

    mocker.patch(
        "app.repositories.users_repo.find_or_create",
        return_value=mock_user
    )
    mocker.patch(
        "app.repositories.users_repo.get_by_id",
        return_value=mock_user
    )
    mocker.patch(
        "app.repositories.users_repo.update_last_logout",
        return_value=None
    )

    return mock_user
