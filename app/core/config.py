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

    # Shared Google Cloud hints
    GCP_PROJECT: str = ""
    GCP_PROJECT_ID: str = ""

    # Cloud Spanner integration
    SPANNER_ENABLED: bool = False
    SPANNER_PROJECT: str = ""
    SPANNER_INSTANCE: str = ""
    SPANNER_DATABASE: str = ""
    SPANNER_TABLE: str = "auction_data"
    SPANNER_EMULATOR_HOST: str = ""

    # Standard Google ADC via env var `GOOGLE_APPLICATION_CREDENTIALS` is used if present
    GOOGLE_APPLICATION_CREDENTIALS: str = ""
    # Alternative credential input: path, raw JSON, or base64 JSON
    GCP_SA_KEY: str = ""

    # pydantic-settings v2 style config
    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", _PROJECT_ROOT_ENV),
        case_sensitive=False,
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
