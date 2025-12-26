import os
import sys
import logging
import threading
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

# Allow running this file directly (IDE Run button)
if __package__ is None or __package__ == "":
    # add project root to sys.path so `import app...` works when running app/main.py
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.api.v1.routes.dates import router as dates_router
from app.api.v1.routes.files import router as files_router
from app.api.v1.routes.admin import router as admin_router
from app.api.v1.routes.auction import router as auction_router
from app.api.v1.routes.vehicles import router as vehicles_router
from app.api.v1.routes.vehicle_history import router as vehicle_history_router
from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.favorites import router as favorites_router
from app.api.v1.routes.vehicle_favorites import router as vehicle_favorites_router
from app.core.config import settings
from app.core.exceptions import AppException
from app.core.rate_limiter import limiter
from app.crawler.downloader import download_if_changed
try:
    from app.repositories import supabase_repo  # type: ignore
except Exception:
    supabase_repo = None  # type: ignore



# 기본 허용 도메인 (CORS_ORIGINS 미설정 시 사용)
DEFAULT_CORS_ORIGINS = [
    "https://dennis-seo.github.io",  # GitHub Pages 프론트엔드
    "http://localhost:3000",          # 로컬 개발 환경
    "http://localhost:5173",          # Vite 기본 포트
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]


def _get_cors_origins() -> list[str]:
    """
    CORS 허용 도메인 목록 반환

    - CORS_ORIGINS 환경변수가 설정되면 해당 도메인만 허용
    - 설정되지 않으면 기본 도메인 목록 사용

    Note: allow_credentials=True 사용 시 와일드카드(*)는 브라우저에서 허용되지 않음
    """
    origins_str = settings.CORS_ORIGINS.strip()
    if not origins_str:
        # 기본 도메인 목록 사용
        return DEFAULT_CORS_ORIGINS
    # 환경변수에서 지정된 도메인 사용
    return [origin.strip() for origin in origins_str.split(",") if origin.strip()]


def create_app() -> FastAPI:
    app = FastAPI(title="Car Auction API", version="1.0.0")

    # Rate Limiter 설정
    app.state.limiter = limiter

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
        """Rate Limit 초과 시 한국어 응답 및 Retry-After 헤더 포함"""
        retry_after = getattr(exc, "retry_after", 60)
        return JSONResponse(
            status_code=429,
            content={"detail": "요청이 너무 많습니다. 잠시 후 다시 시도해주세요."},
            headers={"Retry-After": str(retry_after)}
        )

    # CORS 설정 (환경 변수 기반)
    cors_origins = _get_cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )

    # Mount routers (keep paths identical to current API)
    app.include_router(dates_router, prefix="/api")
    app.include_router(files_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")
    app.include_router(auction_router, prefix="/api")
    app.include_router(vehicles_router, prefix="/api")
    app.include_router(vehicle_history_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(health_router, prefix="/api")
    app.include_router(favorites_router, prefix="/api")
    app.include_router(vehicle_favorites_router, prefix="/api")

    # 글로벌 예외 핸들러
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        """커스텀 예외를 일관된 JSON 응답으로 변환"""
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """처리되지 않은 예외를 500 응답으로 변환"""
        error_logger = logging.getLogger("uvicorn.error")
        error_logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "서버 내부 오류가 발생했습니다"},
        )

    # Kick off one crawl attempt on startup (non-blocking)
    # Use uvicorn's error logger so INFO lines show up under uvicorn
    logger = logging.getLogger("uvicorn.error")

    @app.on_event("startup")
    async def _startup_crawl_once() -> None:
        url = getattr(settings, "CRAWL_URL", None)
        if not url:
            return

        def _run():
            try:
                # Supabase config summary (safe)
                from datetime import datetime as _dt
                from app.utils.bizdate import next_business_day
                logger.info(
                    "Supabase config: enabled=%s url=%s table=%s history_table=%s",
                    getattr(settings, "SUPABASE_ENABLED", False),
                    getattr(settings, "SUPABASE_URL", "") or "<unset>",
                    getattr(settings, "SUPABASE_TABLE", "<unset>"),
                    getattr(settings, "SUPABASE_HISTORY_TABLE", "") or "<none>",
                )
                # Decide source date for crawler (YYMMDD)
                src_date = _dt.now().strftime("%y%m%d")

                logger.info("Startup crawl (pre-checked Supabase): %s", url)
                result = download_if_changed(url, return_bytes_on_no_change=True)
                logger.info("Startup crawl result: %s", result)
                if settings.SUPABASE_ENABLED and supabase_repo is not None and (result.get("path") or result.get("content")):
                    content = None
                    filename = None
                    if result.get("path"):
                        path = result["path"]
                        filename = os.path.basename(path)
                        with open(path, "rb") as f:
                            content = f.read()
                    else:
                        content = result.get("content")
                        filename = result.get("filename") or f"auction_data_{src_date}.csv"
                    # Try to parse src_date from filename if possible
                    if filename and filename.startswith("auction_data_") and filename.endswith(".csv"):
                        try:
                            src_date = filename[len("auction_data_") : -len(".csv")]
                        except Exception:
                            pass
                    # Map to target business date and upload when changed or missing
                    try:
                        target_date = next_business_day(src_date)
                    except Exception:
                        target_date = src_date
                    should_upload = bool(result.get("changed"))
                    if content and filename:
                        # If row is missing, upload regardless of changed
                        try:
                            exists = supabase_repo.get_csv(target_date)  # type: ignore[attr-defined]
                        except Exception:
                            exists = None
                        if exists is None or should_upload:
                            supabase_repo.save_csv(target_date, filename, content)  # type: ignore[attr-defined]
            except Exception as exc:
                logger.error("Startup crawl failed: %s", exc)

        threading.Thread(target=_run, daemon=True).start()

    return app


app = create_app()

if __name__ == "__main__":
    # Local dev entrypoint: python app/main.py
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
