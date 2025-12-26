import logging

from fastapi import APIRouter, Path
from fastapi.responses import FileResponse, Response

from app.core.config import settings
from app.core.exceptions import AppException, NotFoundError
from app.services.csv_service import get_csv_path_for_date, get_csv_content_for_date

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Files"])


@router.get(
    "/csv/{date}",
    summary="CSV 파일 다운로드",
    description="지정된 날짜의 경매 데이터 CSV 파일을 다운로드합니다. `/files/{date}`와 동일합니다.",
    responses={
        200: {
            "description": "CSV 파일 반환",
            "content": {"text/csv": {}},
        },
        404: {"description": "해당 날짜의 CSV 파일을 찾을 수 없음"},
        500: {"description": "서버 내부 오류"},
    },
)
@router.get(
    "/files/{date}",
    summary="CSV 파일 다운로드",
    description="지정된 날짜의 경매 데이터 CSV 파일을 다운로드합니다. 날짜 형식은 YYMMDD입니다.",
    responses={
        200: {
            "description": "CSV 파일 반환",
            "content": {"text/csv": {}},
        },
        404: {"description": "해당 날짜의 CSV 파일을 찾을 수 없음"},
        500: {"description": "서버 내부 오류"},
    },
)
def get_csv(
    date: str = Path(
        ...,
        description="조회할 날짜 (YYMMDD 형식, 예: 251126)",
        example="251126",
        min_length=6,
        max_length=6,
    ),
):
    try:
        # Supabase mode: fetch bytes and return direct response
        if settings.SUPABASE_ENABLED:
            content, filename = get_csv_content_for_date(date)
            if content is None:
                raise NotFoundError(message="CSV 파일을 찾을 수 없습니다")
            headers = {
                "Content-Disposition": f"attachment; filename={filename}",
            }
            return Response(content=content, media_type="text/csv", headers=headers)

        # Local mode: serve file
        path, filename = get_csv_path_for_date(date)
        if path is None:
            raise NotFoundError(message="CSV 파일을 찾을 수 없습니다")
        return FileResponse(
            path,
            media_type="text/csv",
            filename=filename,
        )
    except (NotFoundError, AppException):
        raise
    except Exception as exc:
        logger.error("CSV 파일 조회 실패 (date=%s): %s", date, exc, exc_info=True)
        raise AppException(message="CSV 파일 조회에 실패했습니다") from exc

