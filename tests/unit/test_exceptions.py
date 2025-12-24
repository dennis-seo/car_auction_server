"""
커스텀 예외 클래스 테스트
"""

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import (
    AppException,
    NotFoundError,
    ValidationError,
    AuthenticationError,
    ForbiddenError,
    ServiceUnavailableError,
    ConfigurationError,
    ExternalServiceError,
)


class TestAppException:
    """AppException 기본 클래스 테스트"""

    def test_default_message(self):
        exc = AppException()
        assert exc.message == "서버 내부 오류가 발생했습니다"
        assert exc.status_code == 500

    def test_custom_message(self):
        exc = AppException(message="커스텀 에러 메시지")
        assert exc.message == "커스텀 에러 메시지"

    def test_detail_for_debugging(self):
        exc = AppException(message="에러", detail="디버그 정보")
        assert exc.detail == "디버그 정보"


class TestNotFoundError:
    """NotFoundError 테스트"""

    def test_status_code(self):
        exc = NotFoundError()
        assert exc.status_code == 404

    def test_default_message(self):
        exc = NotFoundError()
        assert exc.message == "요청한 리소스를 찾을 수 없습니다"

    def test_custom_message(self):
        exc = NotFoundError("차량을 찾을 수 없습니다")
        assert exc.message == "차량을 찾을 수 없습니다"


class TestValidationError:
    """ValidationError 테스트"""

    def test_status_code(self):
        exc = ValidationError()
        assert exc.status_code == 400

    def test_default_message(self):
        exc = ValidationError()
        assert exc.message == "잘못된 요청입니다"


class TestAuthenticationError:
    """AuthenticationError 테스트"""

    def test_status_code(self):
        exc = AuthenticationError()
        assert exc.status_code == 401

    def test_default_message(self):
        exc = AuthenticationError()
        assert exc.message == "인증이 필요합니다"


class TestForbiddenError:
    """ForbiddenError 테스트"""

    def test_status_code(self):
        exc = ForbiddenError()
        assert exc.status_code == 403

    def test_default_message(self):
        exc = ForbiddenError()
        assert exc.message == "권한이 없습니다"


class TestServiceUnavailableError:
    """ServiceUnavailableError 테스트"""

    def test_status_code(self):
        exc = ServiceUnavailableError()
        assert exc.status_code == 503

    def test_default_message(self):
        exc = ServiceUnavailableError()
        assert exc.message == "서비스를 일시적으로 사용할 수 없습니다"


class TestConfigurationError:
    """ConfigurationError 테스트"""

    def test_status_code(self):
        exc = ConfigurationError()
        assert exc.status_code == 500

    def test_default_message(self):
        exc = ConfigurationError()
        assert exc.message == "서버 설정 오류입니다"


class TestExternalServiceError:
    """ExternalServiceError 테스트"""

    def test_status_code(self):
        exc = ExternalServiceError()
        assert exc.status_code == 502

    def test_default_message(self):
        exc = ExternalServiceError()
        assert exc.message == "외부 서비스 오류가 발생했습니다"


class TestExceptionInheritance:
    """예외 상속 관계 테스트"""

    def test_all_exceptions_inherit_from_app_exception(self):
        exceptions = [
            NotFoundError,
            ValidationError,
            AuthenticationError,
            ForbiddenError,
            ServiceUnavailableError,
            ConfigurationError,
            ExternalServiceError,
        ]
        for exc_class in exceptions:
            assert issubclass(exc_class, AppException)

    def test_all_exceptions_are_exception_subclass(self):
        exceptions = [
            AppException,
            NotFoundError,
            ValidationError,
            AuthenticationError,
            ForbiddenError,
            ServiceUnavailableError,
            ConfigurationError,
            ExternalServiceError,
        ]
        for exc_class in exceptions:
            assert issubclass(exc_class, Exception)
