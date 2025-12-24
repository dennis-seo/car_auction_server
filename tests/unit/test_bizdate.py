"""
app/utils/bizdate.py 단위 테스트
"""
import pytest
from app.utils.bizdate import (
    _parse_yymmdd,
    _format_yymmdd,
    next_business_day,
    previous_source_candidates_for_mapped,
    yymmdd_to_iso,
    iso_to_yymmdd,
)
from datetime import date


class TestParseYymmdd:
    """_parse_yymmdd 함수 테스트"""

    def test_valid_date(self):
        """정상적인 YYMMDD 파싱"""
        result = _parse_yymmdd("251130")
        assert result == date(2025, 11, 30)

    def test_valid_date_january(self):
        """1월 날짜 파싱"""
        result = _parse_yymmdd("250101")
        assert result == date(2025, 1, 1)

    def test_valid_date_december(self):
        """12월 날짜 파싱"""
        result = _parse_yymmdd("251231")
        assert result == date(2025, 12, 31)

    def test_invalid_length_short(self):
        """5자리 입력 시 에러"""
        with pytest.raises(ValueError, match="invalid yymmdd"):
            _parse_yymmdd("25113")

    def test_invalid_length_long(self):
        """7자리 입력 시 에러"""
        with pytest.raises(ValueError, match="invalid yymmdd"):
            _parse_yymmdd("2511301")

    def test_non_digit(self):
        """숫자가 아닌 문자 포함 시 에러"""
        with pytest.raises(ValueError, match="invalid yymmdd"):
            _parse_yymmdd("25ab30")

    def test_empty_string(self):
        """빈 문자열 입력 시 에러"""
        with pytest.raises(ValueError, match="invalid yymmdd"):
            _parse_yymmdd("")


class TestFormatYymmdd:
    """_format_yymmdd 함수 테스트"""

    def test_format_date(self):
        """date 객체를 YYMMDD로 포맷"""
        result = _format_yymmdd(date(2025, 11, 30))
        assert result == "251130"

    def test_format_single_digit_month(self):
        """한 자리 월 포맷"""
        result = _format_yymmdd(date(2025, 1, 5))
        assert result == "250105"


class TestNextBusinessDay:
    """next_business_day 함수 테스트"""

    def test_monday_to_tuesday(self):
        """월요일 → 화요일"""
        # 2025-11-24 is Monday
        result = next_business_day("251124")
        assert result == "251125"

    def test_tuesday_to_wednesday(self):
        """화요일 → 수요일"""
        result = next_business_day("251125")
        assert result == "251126"

    def test_wednesday_to_thursday(self):
        """수요일 → 목요일"""
        result = next_business_day("251126")
        assert result == "251127"

    def test_thursday_to_friday(self):
        """목요일 → 금요일"""
        result = next_business_day("251127")
        assert result == "251128"

    def test_friday_to_monday(self):
        """금요일 → 월요일 (+3일)"""
        result = next_business_day("251128")
        assert result == "251201"

    def test_saturday_to_monday(self):
        """토요일 → 월요일 (+2일)"""
        result = next_business_day("251129")
        assert result == "251201"

    def test_sunday_to_monday(self):
        """일요일 → 월요일 (+1일)"""
        result = next_business_day("251130")
        assert result == "251201"

    def test_year_boundary(self):
        """연도 경계 테스트 (12월 → 1월)"""
        # 2025-12-31 is Wednesday
        result = next_business_day("251231")
        assert result == "260101"


class TestPreviousSourceCandidates:
    """previous_source_candidates_for_mapped 함수 테스트"""

    def test_tuesday_returns_monday(self):
        """화요일 → [월요일]"""
        result = previous_source_candidates_for_mapped("251125")  # Tuesday
        assert result == ["251124"]

    def test_wednesday_returns_tuesday(self):
        """수요일 → [화요일]"""
        result = previous_source_candidates_for_mapped("251126")
        assert result == ["251125"]

    def test_thursday_returns_wednesday(self):
        """목요일 → [수요일]"""
        result = previous_source_candidates_for_mapped("251127")
        assert result == ["251126"]

    def test_friday_returns_thursday(self):
        """금요일 → [목요일]"""
        result = previous_source_candidates_for_mapped("251128")
        assert result == ["251127"]

    def test_monday_returns_sun_sat_fri(self):
        """월요일 → [일, 토, 금] 순서"""
        result = previous_source_candidates_for_mapped("251201")  # Monday
        assert result == ["251130", "251129", "251128"]  # Sun, Sat, Fri


class TestYymmddToIso:
    """yymmdd_to_iso 함수 테스트"""

    def test_valid_conversion(self):
        """정상 변환"""
        assert yymmdd_to_iso("251130") == "2025-11-30"

    def test_january(self):
        """1월 변환"""
        assert yymmdd_to_iso("250101") == "2025-01-01"

    def test_invalid_length_returns_original(self):
        """잘못된 길이는 원본 반환"""
        assert yymmdd_to_iso("25113") == "25113"

    def test_non_digit_returns_original(self):
        """숫자 아닌 문자 포함 시 원본 반환"""
        assert yymmdd_to_iso("25ab30") == "25ab30"


class TestIsoToYymmdd:
    """iso_to_yymmdd 함수 테스트"""

    def test_valid_conversion(self):
        """정상 변환"""
        assert iso_to_yymmdd("2025-11-30") == "251130"

    def test_january(self):
        """1월 변환"""
        assert iso_to_yymmdd("2025-01-01") == "250101"

    def test_invalid_format_returns_original(self):
        """잘못된 형식은 원본 반환"""
        assert iso_to_yymmdd("2025/11/30") == "2025/11/30"

    def test_short_string_returns_original(self):
        """짧은 문자열은 원본 반환"""
        assert iso_to_yymmdd("251130") == "251130"


class TestRoundTrip:
    """양방향 변환 테스트"""

    def test_yymmdd_to_iso_and_back(self):
        """YYMMDD → ISO → YYMMDD"""
        original = "251225"
        iso = yymmdd_to_iso(original)
        result = iso_to_yymmdd(iso)
        assert result == original

    def test_iso_to_yymmdd_and_back(self):
        """ISO → YYMMDD → ISO"""
        original = "2025-12-25"
        yymmdd = iso_to_yymmdd(original)
        result = yymmdd_to_iso(yymmdd)
        assert result == original
