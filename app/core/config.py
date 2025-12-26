import os
from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


# Resolve .env at project root regardless of current working directory
_PROJECT_ROOT_ENV = str(Path(__file__).resolve().parents[2] / ".env")


class Settings(BaseSettings):
    SOURCES_DIR: str = "sources"
    APP_NAME: str = "Car Auction API"
    APP_VERSION: str = "1.0.0"
    # Default crawl target URL (can be overridden via env)
    CRAWL_URL: str = (
        "https://www.xn--2q1bm5w1qdbqaq6cwvm.com/wp-content/themes/welcomecar-new/auction_data.csv"
    )
    # Admin token for protected endpoints (set via .env or secrets)
    ADMIN_TOKEN: str = ""

    # Supabase integration
    SUPABASE_ENABLED: bool = False
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_TABLE: str = "auction_data"
    SUPABASE_HISTORY_TABLE: str = ""

    # Google OAuth 설정
    GOOGLE_CLIENT_ID: str = ""

    # JWT 설정
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 10080  # 7일

    # CORS 설정
    # 콤마로 구분된 도메인 목록 (예: "https://app.example.com,https://admin.example.com")
    # 빈 문자열이면 모든 도메인 허용 (개발용)
    CORS_ORIGINS: str = ""

    # pydantic-settings v2 style config
    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", _PROJECT_ROOT_ENV),
        case_sensitive=False,
        extra="ignore",  # allow unknown env vars so `.env` doesn't break startup
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
