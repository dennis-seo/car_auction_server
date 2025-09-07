from fastapi import APIRouter, HTTPException

from app.services.csv_service import list_available_dates


router = APIRouter()


@router.get("/dates", response_model=list[str])
def get_dates() -> list[str]:
    try:
        return list_available_dates()
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to list dates") from exc

