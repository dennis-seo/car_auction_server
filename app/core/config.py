from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SOURCES_DIR: str = "sources"
    APP_NAME: str = "Car Auction API"
    APP_VERSION: str = "1.0.0"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

