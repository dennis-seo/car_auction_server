import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from app.services.csv_service import (
    get_auction_data_for_date,
    get_csv_content_for_date,
    get_csv_path_for_date,
)
from app.core.config import settings


logger = logging.getLogger("auction.api")


router = APIRouter()


@router.get("/auction_date/{date}")
def get_auction_date(date: str):
    try:
        data = get_auction_data_for_date(date)
        if data is None:
            raise HTTPException(status_code=404, detail="Auction data not found")
        return data
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch auction data from Spanner", extra={"date": date})
        raise HTTPException(status_code=500, detail="Failed to fetch auction data") from exc


@router.get("/csv/{date}")
@router.get("/files/{date}")
def get_csv(date: str):
    try:
        # Spanner mode: fetch bytes and return direct response
        if settings.SPANNER_ENABLED:
            content, filename = get_csv_content_for_date(date)
            if content is None:
                raise HTTPException(status_code=404, detail="CSV not found")
            headers = {
                "Content-Disposition": f"attachment; filename={filename}",
            }
            return Response(content=content, media_type="text/csv", headers=headers)

        # Local mode: serve file
        path, filename = get_csv_path_for_date(date)
        if path is None:
            raise HTTPException(status_code=404, detail="CSV not found")
        return FileResponse(
            path,
            media_type="text/csv",
            filename=filename,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to fetch CSV") from exc
