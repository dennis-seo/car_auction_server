"""
Rate Limiting 설정

slowapi를 사용한 IP 기반 요청 제한
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# IP 주소 기반 Rate Limiter
limiter = Limiter(key_func=get_remote_address)


# Rate Limit 상수 정의
class RateLimits:
    """
    엔드포인트별 Rate Limit 설정

    형식: "요청수/기간" (예: "5/minute", "10/second", "100/hour")
    """
    # 인증 엔드포인트 (브루트포스 방지)
    AUTH_GOOGLE = "10/minute"      # Google 로그인: IP당 분당 10회
    AUTH_ME = "30/minute"          # 내 정보 조회: IP당 분당 30회
    AUTH_LOGOUT = "10/minute"      # 로그아웃: IP당 분당 10회
    AUTH_REFRESH = "20/minute"     # 토큰 갱신: IP당 분당 20회
