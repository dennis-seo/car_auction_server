from fastapi import APIRouter, HTTPException

from app.services.csv_service import (
    list_available_dates,
    list_available_dates_paginated,
)


router = APIRouter()


@router.get("/dates", response_model=list[str])
def get_dates() -> list[str]:
    try:
        return list_available_dates()
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to list dates") from exc


@router.get("/dates/paged")
def get_dates_paged(page: int = 1, size: int = 20) -> dict:
    try:
        return list_available_dates_paginated(page, size)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to list dates") from exc
