"""
app/repositories/file_repo.py 테스트
"""
import pytest
from pathlib import Path


class TestListAuctionCSVFiles:
    """list_auction_csv_files 함수 테스트"""

    def test_list_files_empty_directory(self, temp_sources_dir, monkeypatch):
        """빈 디렉토리에서 빈 리스트 반환"""
        from app.core.config import get_settings
        get_settings.cache_clear()

        # sources 디렉토리 경로를 settings에 설정
        monkeypatch.setattr("app.core.config.settings.SOURCES_DIR", str(temp_sources_dir))

        from app.repositories.file_repo import list_auction_csv_files

        result = list_auction_csv_files()
        assert result == []

    def test_list_files_with_csv_files(self, temp_sources_dir, monkeypatch):
        """CSV 파일이 있는 디렉토리에서 파일 목록 반환"""
        # CSV 파일 생성
        (temp_sources_dir / "auction_data_251125.csv").write_text("test")
        (temp_sources_dir / "auction_data_251126.csv").write_text("test")

        from app.core.config import get_settings
        get_settings.cache_clear()
        monkeypatch.setattr("app.core.config.settings.SOURCES_DIR", str(temp_sources_dir))

        from app.repositories.file_repo import list_auction_csv_files

        result = list_auction_csv_files()

        assert len(result) == 2
        assert "auction_data_251125.csv" in result
        assert "auction_data_251126.csv" in result

    def test_list_files_includes_all_files(self, temp_sources_dir, monkeypatch):
        """디렉토리의 모든 파일 반환 (필터링 없음)"""
        (temp_sources_dir / "auction_data_251125.csv").write_text("test")
        (temp_sources_dir / "readme.txt").write_text("test")
        (temp_sources_dir / "data.json").write_text("{}")

        from app.core.config import get_settings
        get_settings.cache_clear()
        monkeypatch.setattr("app.core.config.settings.SOURCES_DIR", str(temp_sources_dir))

        from app.repositories.file_repo import list_auction_csv_files

        result = list_auction_csv_files()

        # list_auction_csv_files는 모든 파일을 반환함
        assert len(result) == 3
        assert "auction_data_251125.csv" in result

    def test_list_files_multiple_csv(self, temp_sources_dir, monkeypatch):
        """여러 CSV 파일이 있는 경우"""
        (temp_sources_dir / "auction_data_251125.csv").write_text("test")
        (temp_sources_dir / "auction_data_251126.csv").write_text("test")

        from app.core.config import get_settings
        get_settings.cache_clear()
        monkeypatch.setattr("app.core.config.settings.SOURCES_DIR", str(temp_sources_dir))

        from app.repositories.file_repo import list_auction_csv_files

        result = list_auction_csv_files()

        assert len(result) == 2


class TestResolveCSVFilepath:
    """resolve_csv_filepath 함수 테스트"""

    def test_resolve_existing_file(self, temp_sources_dir, monkeypatch):
        """존재하는 파일 경로 반환"""
        csv_file = temp_sources_dir / "auction_data_251125.csv"
        csv_file.write_text("test content")

        from app.core.config import get_settings
        get_settings.cache_clear()
        monkeypatch.setattr("app.core.config.settings.SOURCES_DIR", str(temp_sources_dir))

        from app.repositories.file_repo import resolve_csv_filepath

        result = resolve_csv_filepath("auction_data_251125.csv")

        assert result is not None
        assert result == str(csv_file)

    def test_resolve_non_existing_file(self, temp_sources_dir, monkeypatch):
        """존재하지 않는 파일은 None 반환"""
        from app.core.config import get_settings
        get_settings.cache_clear()
        monkeypatch.setattr("app.core.config.settings.SOURCES_DIR", str(temp_sources_dir))

        from app.repositories.file_repo import resolve_csv_filepath

        result = resolve_csv_filepath("non_existent.csv")

        assert result is None

    def test_resolve_with_full_path(self, temp_sources_dir, monkeypatch):
        """전체 경로로 파일 찾기"""
        csv_file = temp_sources_dir / "auction_data_251125.csv"
        csv_file.write_text("test content")

        from app.core.config import get_settings
        get_settings.cache_clear()
        monkeypatch.setattr("app.core.config.settings.SOURCES_DIR", str(temp_sources_dir))

        from app.repositories.file_repo import resolve_csv_filepath

        # 파일명만 전달해도 전체 경로 반환
        result = resolve_csv_filepath("auction_data_251125.csv")

        assert Path(result).is_absolute()
