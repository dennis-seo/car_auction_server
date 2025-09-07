import os
import sys
import logging
import threading
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Allow running this file directly (IDE Run button)
if __package__ is None or __package__ == "":
    # add project root to sys.path so `import app...` works when running app/main.py
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.api.v1.routes.dates import router as dates_router
from app.api.v1.routes.files import router as files_router
from app.api.v1.routes.admin import router as admin_router
from app.core.config import settings
from app.crawler.downloader import download_if_changed


def create_app() -> FastAPI:
    app = FastAPI(title="Car Auction API", version="1.0.0")

    # CORS: mirror behavior from the simple server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # Mount routers (keep paths identical to current API)
    app.include_router(dates_router, prefix="/api")
    app.include_router(files_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")

    # Kick off one crawl attempt on startup (non-blocking)
    logger = logging.getLogger("crawler")

    @app.on_event("startup")
    async def _startup_crawl_once() -> None:
        url = getattr(settings, "CRAWL_URL", None)
        if not url:
            return

        def _run():
            try:
                logger.info("Startup crawl: %s", url)
                result = download_if_changed(url)
                logger.info("Startup crawl result: %s", result)
            except Exception as exc:
                logger.error("Startup crawl failed: %s", exc)

        threading.Thread(target=_run, daemon=True).start()

    return app


app = create_app()

if __name__ == "__main__":
    # Local dev entrypoint: python app/main.py
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
