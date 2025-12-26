"""
커스텀 예외 클래스 및 글로벌 예외 핸들러

일관된 에러 응답 형식을 위한 예외 처리 인프라를 제공합니다.
"""

from typing import Optional


class AppException(Exception):
    """
    애플리케이션 기본 예외 클래스

    모든 커스텀 예외의 부모 클래스입니다.
    글로벌 예외 핸들러에서 일관된 응답으로 변환됩니다.
    """

    status_code: int = 500
    default_message: str = "서버 내부 오류가 발생했습니다"

    def __init__(self, message: Optional[str] = None, detail: Optional[str] = None):
        self.message = message or self.default_message
        self.detail = detail  # 추가 디버깅 정보 (로깅용)
        super().__init__(self.message)


class NotFoundError(AppException):
    """리소스를 찾을 수 없는 경우 (404)"""

    status_code = 404
    default_message = "요청한 리소스를 찾을 수 없습니다"


class ValidationError(AppException):
    """요청 파라미터 검증 실패 (400)"""

    status_code = 400
    default_message = "잘못된 요청입니다"


class AuthenticationError(AppException):
    """인증 실패 (401)"""

    status_code = 401
    default_message = "인증이 필요합니다"


class ForbiddenError(AppException):
    """권한 없음 (403)"""

    status_code = 403
    default_message = "권한이 없습니다"


class ServiceUnavailableError(AppException):
    """서비스 이용 불가 (503)"""

    status_code = 503
    default_message = "서비스를 일시적으로 사용할 수 없습니다"


class ConfigurationError(AppException):
    """서버 설정 오류 (500)"""

    status_code = 500
    default_message = "서버 설정 오류입니다"


class ExternalServiceError(AppException):
    """외부 서비스 오류 (502)"""

    status_code = 502
    default_message = "외부 서비스 오류가 발생했습니다"


class ConflictError(AppException):
    """리소스 충돌 (409)"""

    status_code = 409
    default_message = "리소스가 이미 존재합니다"
