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
try:
    from app.repositories import firestore_repo  # type: ignore
except Exception:
    firestore_repo = None  # type: ignore


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
    # Use uvicorn's error logger so INFO lines show up under uvicorn
    logger = logging.getLogger("uvicorn.error")

    @app.on_event("startup")
    async def _startup_crawl_once() -> None:
        url = getattr(settings, "CRAWL_URL", None)
        if not url:
            return

        def _run():
            try:
                # Firestore config summary (safe)
                import os as _os
                from datetime import datetime as _dt
                logger.info(
                    "Firestore config: enabled=%s project=%s collection=%s creds=%s",
                    getattr(settings, "FIRESTORE_ENABLED", False),
                    getattr(settings, "GCP_PROJECT", "<auto>"),
                    getattr(settings, "FIRESTORE_COLLECTION", "auction_data"),
                    _os.path.basename(_os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "<env-not-set>"),
                )
                # Decide date key (YYMMDD) for Firestore existence check
                date_key = _dt.now().strftime("%y%m%d")
                if settings.FIRESTORE_ENABLED and firestore_repo is not None:
                    exists = None
                    try:
                        exists = firestore_repo.get_csv(date_key)  # type: ignore[attr-defined]
                    except Exception as exc:
                        logger.error("Firestore pre-check failed: %s", exc)
                    if exists is not None:
                        logger.info("Firestore already has today's document: %s; skipping crawl", date_key)
                        return

                logger.info("Startup crawl (pre-checked Firestore): %s", url)
                result = download_if_changed(url, return_bytes_on_no_change=True)
                logger.info("Startup crawl result: %s", result)
                if settings.FIRESTORE_ENABLED and firestore_repo is not None and (result.get("path") or result.get("content")):
                    import os
                    content = None
                    filename = None
                    if result.get("path"):
                        path = result["path"]
                        filename = os.path.basename(path)
                        with open(path, "rb") as f:
                            content = f.read()
                    else:
                        content = result.get("content")
                        filename = result.get("filename") or f"auction_data_{date_key}.csv"
                    # If date_key wasn't parsed, try from filename
                    if filename and not date_key and filename.startswith("auction_data_") and filename.endswith(".csv"):
                        date_key = filename[len("auction_data_") : -len(".csv")]
                    if content and filename and date_key:
                        firestore_repo.save_csv(date_key, filename, content)  # type: ignore[attr-defined]
            except Exception as exc:
                logger.error("Startup crawl failed: %s", exc)

        threading.Thread(target=_run, daemon=True).start()

    return app


app = create_app()

if __name__ == "__main__":
    # Local dev entrypoint: python app/main.py
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
