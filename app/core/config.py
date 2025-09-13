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

    # Firestore integration
    FIRESTORE_ENABLED: bool = False
    GCP_PROJECT: str = ""
    FIRESTORE_COLLECTION: str = "auction_data"
    # Standard Google ADC via env var `GOOGLE_APPLICATION_CREDENTIALS` is used if present
    GOOGLE_APPLICATION_CREDENTIALS: str = ""

    # pydantic-settings v2 style config
    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", _PROJECT_ROOT_ENV),
        case_sensitive=False,
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
