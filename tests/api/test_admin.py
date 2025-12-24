"""
app/api/v1/routes/admin.py API 테스트
"""
import pytest
from unittest.mock import patch, MagicMock


class TestAdminTokenValidation:
    """Admin 토큰 검증 테스트"""

    def test_missing_token_returns_401(self, client):
        """토큰 없이 요청 시 401 반환"""
        response = client.post("/api/admin/crawl")
        assert response.status_code == 401

    def test_invalid_token_returns_401(self, client):
        """잘못된 토큰으로 요청 시 401 반환"""
        response = client.post(
            "/api/admin/crawl",
            headers={"Authorization": "Bearer wrong_token"}
        )
        assert response.status_code == 401

    def test_valid_bearer_token_accepted(self, client, admin_headers):
        """유효한 Bearer 토큰은 인증 통과"""
        response = client.post("/api/admin/crawl", headers=admin_headers)
        # 401이 아니면 토큰은 통과된 것
        assert response.status_code != 401

    def test_x_admin_token_header_accepted(self, client):
        """X-Admin-Token 헤더로 인증 통과"""
        response = client.post(
            "/api/admin/crawl",
            headers={"X-Admin-Token": "test_admin_token"}
        )
        # 401이 아니면 토큰은 통과된 것
        assert response.status_code != 401


class TestAdminCrawl:
    """POST /api/admin/crawl 테스트"""

    def test_crawl_success_with_mock(self, client, admin_headers):
        """크롤링 요청 성공 (모킹)"""
        mock_result = {
            "changed": False,
            "path": None,
            "content": b"test,data\n1,2",
            "filename": "auction_data_251224.csv"
        }

        with patch("app.api.v1.routes.admin.download_if_changed", return_value=mock_result):
            response = client.post("/api/admin/crawl", headers=admin_headers)
            # 성공적으로 처리됨
            assert response.status_code == 200

    def test_crawl_with_mocked_download(self, client, admin_headers, monkeypatch):
        """크롤링 성공 시나리오 (모킹)"""
        monkeypatch.setenv("ADMIN_TOKEN", "test_admin_token")
        monkeypatch.setenv("CRAWL_URL", "https://example.com/data.csv")
        monkeypatch.setenv("SUPABASE_ENABLED", "false")

        from app.core.config import get_settings
        get_settings.cache_clear()

        mock_result = {
            "changed": True,
            "path": None,
            "content": b"test,data\n1,2",
            "filename": "auction_data_251224.csv"
        }

        with patch("app.api.v1.routes.admin.download_if_changed", return_value=mock_result):
            response = client.post("/api/admin/crawl", headers=admin_headers)

            assert response.status_code == 200
            result = response.json()
            assert "changed" in result or "content" in result


class TestAdminEnsureDate:
    """POST /api/admin/ensure/{date} 테스트"""

    def test_ensure_without_supabase_returns_400(self, client, admin_headers, monkeypatch):
        """Supabase 비활성화 시 400 반환"""
        monkeypatch.setenv("ADMIN_TOKEN", "test_admin_token")
        monkeypatch.setenv("SUPABASE_ENABLED", "false")

        from app.core.config import get_settings
        get_settings.cache_clear()

        response = client.post("/api/admin/ensure/251224", headers=admin_headers)

        assert response.status_code == 400
        assert "Supabase" in response.json()["detail"]

    def test_ensure_missing_token_returns_401(self, client):
        """토큰 없이 요청 시 401 반환"""
        response = client.post("/api/admin/ensure/251224")
        assert response.status_code == 401


class TestDatesEndpoint:
    """GET /api/dates 테스트"""

    def test_dates_with_local_files(self, client, temp_sources_dir, monkeypatch):
        """로컬 파일 모드에서 날짜 목록 반환"""
        # 테스트 CSV 파일 생성
        (temp_sources_dir / "auction_data_251125.csv").write_text("test")
        (temp_sources_dir / "auction_data_251126.csv").write_text("test")

        monkeypatch.setenv("SUPABASE_ENABLED", "false")
        monkeypatch.setattr("app.core.config.settings.SOURCES_DIR", str(temp_sources_dir))

        from app.core.config import get_settings
        get_settings.cache_clear()

        response = client.get("/api/dates")

        assert response.status_code == 200
        dates = response.json()
        assert isinstance(dates, list)

    def test_dates_empty_directory(self, client, temp_sources_dir, monkeypatch):
        """빈 디렉토리에서 빈 리스트 반환"""
        monkeypatch.setenv("SUPABASE_ENABLED", "false")
        monkeypatch.setattr("app.core.config.settings.SOURCES_DIR", str(temp_sources_dir))

        from app.core.config import get_settings
        get_settings.cache_clear()

        response = client.get("/api/dates")

        assert response.status_code == 200
        assert response.json() == []

    def test_dates_with_limit(self, client, temp_sources_dir, monkeypatch):
        """limit 파라미터 테스트"""
        # 여러 CSV 파일 생성
        for i in range(5):
            (temp_sources_dir / f"auction_data_25112{i}.csv").write_text("test")

        monkeypatch.setenv("SUPABASE_ENABLED", "false")
        monkeypatch.setattr("app.core.config.settings.SOURCES_DIR", str(temp_sources_dir))

        from app.core.config import get_settings
        get_settings.cache_clear()

        response = client.get("/api/dates?limit=3")

        assert response.status_code == 200
        dates = response.json()
        assert len(dates) <= 3
