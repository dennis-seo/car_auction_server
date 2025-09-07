from typing import Optional

from fastapi import APIRouter, HTTPException, Header

from app.core.config import settings
from app.crawler.downloader import download_if_changed


router = APIRouter()


def _extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


@router.post("/admin/crawl")
def admin_crawl(
    authorization: Optional[str] = Header(default=None),
    x_admin_token: Optional[str] = Header(default=None),
    ext: str = "csv",
    prefix: str = "auction_data_",
    date: Optional[str] = None,
):
    token = _extract_bearer_token(authorization) or x_admin_token
    if not settings.ADMIN_TOKEN or token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not settings.CRAWL_URL:
        raise HTTPException(status_code=400, detail="CRAWL_URL not configured")

    try:
        result = download_if_changed(
            settings.CRAWL_URL,
            file_ext=ext,
            filename_prefix=prefix,
            date_override=date,
        )
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"crawl failed: {exc}") from exc

