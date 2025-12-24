"""
app/utils/encoding.py 단위 테스트
"""
import pytest
from app.utils.encoding import decode_csv_bytes


class TestDecodeCSVBytes:
    """decode_csv_bytes 함수 테스트"""

    def test_utf8_sig_decode(self):
        """UTF-8-sig (BOM 포함) 디코딩"""
        # UTF-8 BOM + "현대"
        content = b'\xef\xbb\xbf\xed\x98\x84\xeb\x8c\x80'
        result = decode_csv_bytes(content)
        assert result == "현대"

    def test_utf8_without_bom(self):
        """BOM 없는 UTF-8 디코딩"""
        content = "그랜저".encode("utf-8")
        result = decode_csv_bytes(content)
        assert result == "그랜저"

    def test_ascii_content(self):
        """ASCII 내용 디코딩"""
        content = b"Hello, World!"
        result = decode_csv_bytes(content)
        assert result == "Hello, World!"

    def test_cp949_fallback(self):
        """CP949 폴백 디코딩"""
        # "현대" in CP949 encoding
        content = bytes([0xc7, 0xf6, 0xb4, 0xeb])
        result = decode_csv_bytes(content)
        assert "현대" in result

    def test_cp949_full_text(self):
        """CP949 전체 텍스트 디코딩"""
        # Create CP949 encoded text
        text = "테스트 데이터입니다"
        content = text.encode("cp949")
        result = decode_csv_bytes(content)
        assert result == text

    def test_empty_bytes(self):
        """빈 바이트 디코딩"""
        result = decode_csv_bytes(b"")
        assert result == ""

    def test_mixed_content(self):
        """한글/영문 혼합 내용"""
        content = "Hello 안녕하세요 World".encode("utf-8")
        result = decode_csv_bytes(content)
        assert "Hello" in result
        assert "안녕하세요" in result
        assert "World" in result

    def test_csv_header_utf8(self):
        """UTF-8 CSV 헤더 디코딩"""
        content = "이름,나이,주소\n홍길동,30,서울".encode("utf-8-sig")
        result = decode_csv_bytes(content)
        assert "이름" in result
        assert "홍길동" in result

    def test_csv_header_cp949(self):
        """CP949 CSV 헤더 디코딩"""
        content = "이름,나이,주소\n홍길동,30,서울".encode("cp949")
        result = decode_csv_bytes(content)
        assert "이름" in result
        assert "홍길동" in result

    def test_special_characters(self):
        """특수문자 포함 텍스트"""
        content = "가격: ₩1,000,000".encode("utf-8")
        result = decode_csv_bytes(content)
        assert "₩" in result
        assert "1,000,000" in result
