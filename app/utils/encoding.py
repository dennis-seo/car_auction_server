"""
인코딩 관련 유틸리티 함수
"""


def decode_csv_bytes(content: bytes) -> str:
    """
    CSV 바이트를 문자열로 디코딩

    UTF-8-sig를 먼저 시도하고, 실패하면 CP949(한글 Windows)로 폴백.

    Args:
        content: CSV 파일의 바이트 내용

    Returns:
        디코딩된 문자열
    """
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("cp949", errors="replace")
