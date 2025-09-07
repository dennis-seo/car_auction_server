from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.csv_service import get_csv_path_for_date


router = APIRouter()


@router.get("/csv/{date}")
def get_csv(date: str):
    try:
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

