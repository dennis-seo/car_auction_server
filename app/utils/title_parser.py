"""
차량 제목(Post Title) 파싱 유틸리티

원본 제목 예시:
- "기아 쏘렌토 R (09년~12년) 디젤 2.0 2WD TLX 최고급형"
- "현대 쏘나타 디 엣지(DN8)(23년~현재) LPG 2000cc 비즈니스1(렌터카용)"
- "[기아] 더 뉴봉고Ⅲ화물 1.2톤 LPG 킹캡 초장축 GL"
- "벤츠 E-클래스 W213(16년~현재) E200 아방가르드"

v2: JSON 기준(car_models.json) 기반 매칭 추가
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.utils.model_matcher import match_car_model, MatchResult


# 제조사 매핑 (다양한 표기 → 정규화된 이름)
MANUFACTURER_ALIASES = {
    # 국산
    "현대": "현대",
    "기아": "기아",
    "제네시스": "제네시스",
    "쉐보레": "쉐보레",
    "쉐보레(한국GM)": "쉐보레",
    "쉐보레(대우)": "쉐보레",
    "한국GM": "쉐보레",
    "르노삼성": "르노삼성",
    "르노(삼성)": "르노삼성",
    "르노코리아": "르노삼성",
    "KG모빌리티": "KG모빌리티",
    "KG모빌리티(쌍용)": "KG모빌리티",
    "쌍용": "KG모빌리티",

    # 수입 - 독일
    "벤츠": "벤츠",
    "메르세데스-벤츠": "벤츠",
    "메르세데스벤츠": "벤츠",
    "BMW": "BMW",
    "아우디": "아우디",
    "폭스바겐": "폭스바겐",
    "포르쉐": "포르쉐",
    "미니": "미니",

    # 수입 - 일본
    "토요타": "토요타",
    "렉서스": "렉서스",
    "혼다": "혼다",
    "닛산": "닛산",
    "인피니티": "인피니티",
    "마쓰다": "마쓰다",
    "스바루": "스바루",
    "미쓰비시": "미쓰비시",

    # 수입 - 미국
    "포드": "포드",
    "링컨": "링컨",
    "지프": "지프",
    "크라이슬러": "크라이슬러",
    "캐딜락": "캐딜락",
    "GMC": "GMC",
    "테슬라": "테슬라",

    # 수입 - 기타
    "볼보": "볼보",
    "랜드로버": "랜드로버",
    "재규어": "재규어",
    "푸조": "푸조",
    "시트로엥": "시트로엥",
    "피아트": "피아트",
    "알파로메오": "알파로메오",
    "마세라티": "마세라티",
    "페라리": "페라리",
    "람보르기니": "람보르기니",
    "벤틀리": "벤틀리",
    "롤스로이스": "롤스로이스",
    "애스턴마틴": "애스턴마틴",
    "맥라렌": "맥라렌",

    # 중국
    "DFSK": "DFSK",
    "DFSK(동풍자동차)": "DFSK",
    "동풍": "DFSK",
    "BYD": "BYD",
}

# 연료 타입 매핑
FUEL_TYPE_ALIASES = {
    # 가솔린
    "가솔린": "가솔린",
    "휘발유": "가솔린",
    "GDI": "가솔린",
    "GDi": "가솔린",
    "T-GDI": "가솔린",
    "터보": "가솔린",

    # 디젤
    "디젤": "디젤",
    "경유": "디젤",
    "CRDi": "디젤",
    "VGT": "디젤",
    "e-VGT": "디젤",
    "TDI": "디젤",

    # LPG
    "LPG": "LPG",
    "LPI": "LPG",
    "LPe": "LPG",

    # 전기
    "전기": "전기",
    "일렉트릭": "전기",
    "EV": "전기",
    "FCEV": "수소",

    # 하이브리드
    "하이브리드": "하이브리드",
    "HEV": "하이브리드",
    "(H)": "하이브리드",
    "(HEV)": "하이브리드",
    "PHEV": "플러그인하이브리드",
    "(PHEV)": "플러그인하이브리드",

    # 수소
    "수소": "수소",
}

# 변속기 매핑
TRANSMISSION_ALIASES = {
    "오토": "자동",
    "자동": "자동",
    "A/T": "자동",
    "AT": "자동",
    "DCT": "자동",

    "수동": "수동",
    "M/T": "수동",
    "MT": "수동",
}

# 용도 매핑
USAGE_TYPE_ALIASES = {
    "자가용": "자가용",
    "렌터카": "렌터카",
    "렌트": "렌터카",
    "영업용": "영업용",
    "관용": "관용",
}


@dataclass
class ParsedTitle:
    """파싱된 차량 제목 정보"""
    # JSON 기준 ID (car_models.json 기준)
    manufacturer_id: Optional[str] = None
    model_id: Optional[str] = None
    trim_id: Optional[str] = None

    # 텍스트 값
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    sub_model: Optional[str] = None
    trim: Optional[str] = None
    engine_cc: Optional[int] = None
    fuel_type: Optional[str] = None


def _extract_manufacturer(title: str) -> tuple[Optional[str], str]:
    """제조사 추출 및 제거된 문자열 반환"""
    # [제조사] 형태 처리
    bracket_match = re.match(r'^\[([^\]]+)\]\s*', title)
    if bracket_match:
        raw_manufacturer = bracket_match.group(1)
        remaining = title[bracket_match.end():]
        normalized = MANUFACTURER_ALIASES.get(raw_manufacturer, raw_manufacturer)
        return normalized, remaining

    # "제조사 모델명" 형태 처리 - 첫 단어가 제조사인지 확인
    parts = title.split(maxsplit=1)
    if parts:
        first_word = parts[0]
        # 괄호 포함된 제조사명 처리 (예: "쉐보레(한국GM)")
        paren_match = re.match(r'^([^\(]+)(\([^\)]+\))?', first_word)
        if paren_match:
            full_name = paren_match.group(0)
            if full_name in MANUFACTURER_ALIASES:
                remaining = parts[1] if len(parts) > 1 else ""
                return MANUFACTURER_ALIASES[full_name], remaining
            # 괄호 없는 부분만 확인
            base_name = paren_match.group(1)
            if base_name in MANUFACTURER_ALIASES:
                remaining = parts[1] if len(parts) > 1 else ""
                return MANUFACTURER_ALIASES[base_name], remaining

    return None, title


def _extract_engine_cc(title: str) -> Optional[int]:
    """배기량(cc) 추출"""
    # "2000cc", "2.0", "2000" 등의 패턴
    patterns = [
        r'(\d{3,4})\s*cc',           # 2000cc
        r'(\d\.\d)\s*(?:터보|T)?',    # 2.0 터보, 2.0T
        r'R?(\d\.\d)',                # R2.0
    ]

    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            value = match.group(1)
            if '.' in value:
                # 2.0 -> 2000
                return int(float(value) * 1000)
            return int(value)

    return None


def _extract_fuel_type(title: str) -> Optional[str]:
    """연료 타입 추출"""
    title_upper = title.upper()

    # 전기차 우선 확인
    if "일렉트릭" in title or "ELECTRIC" in title_upper or "EV" in title_upper:
        if "FCEV" in title_upper:
            return "수소"
        return "전기"

    # 하이브리드 확인
    if "하이브리드" in title or "HEV" in title_upper or "HYBRID" in title_upper:
        if "PHEV" in title_upper:
            return "플러그인하이브리드"
        return "하이브리드"

    # 연료 키워드 검색
    for keyword, fuel_type in FUEL_TYPE_ALIASES.items():
        if keyword in title:
            return fuel_type

    return None


def _extract_sub_model(title: str) -> Optional[str]:
    """세부 모델 코드 추출 (예: DN8, IG, W213, MQ4)"""
    # 괄호 안의 모델 코드
    patterns = [
        r'\(([A-Z]{1,3}\d{1,3})\)',     # (DN8), (IG), (CN7)
        r'\(([A-Z]\d[A-Z])\)',          # (G80)
        r'([A-Z]\d{3})',                 # W213
        r'\(([A-Z]{2,3}\d)\)',           # (MQ4), (NX4)
    ]

    for pattern in patterns:
        match = re.search(pattern, title)
        if match:
            return match.group(1)

    return None


# 복합 모델명 매핑 (띄어쓰기로 분리된 모델명들)
COMPOUND_MODEL_NAMES = {
    "그랜드 스타렉스": "그랜드스타렉스",
    "그랜저 IG": "그랜저",
    "스타렉스": "스타렉스",
    "포터 2": "포터2",
    "포터 II": "포터2",
    "포터II": "포터2",
    "봉고 3": "봉고3",
    "봉고 III": "봉고3",
    "봉고Ⅲ": "봉고3",
    "봉고Ⅲ화물": "봉고3",
    "올란도": "올란도",
}

# 모델명에서 제거할 접미사 (세대 코드 등)
MODEL_SUFFIX_PATTERNS = [
    r'\(DM\)',      # 싼타페(DM)
    r'\(DN8\)',     # 쏘나타(DN8)
    r'\(CN7\)',     # 아반떼(CN7)
    r'\(NX4\)',     # 투싼(NX4)
    r'\(RG3\)',     # G80(RG3)
    r'\(G\)',       # G80(G)
    r'MD$',         # 아반떼MD
    r'R$',          # 쏘렌토R, 스포티지R
]


def _normalize_model_name(model: str) -> str:
    """모델명 정규화"""
    if not model:
        return model

    # 복합 모델명 매핑
    for compound, normalized in COMPOUND_MODEL_NAMES.items():
        if compound in model:
            return normalized

    # 접미사 제거
    for pattern in MODEL_SUFFIX_PATTERNS:
        model = re.sub(pattern, '', model)

    return model.strip()


def _extract_model_and_trim(title: str, manufacturer: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """모델명과 트림 추출"""
    if not title:
        return None, None

    original_title = title  # 복합 모델명 검색용 보존

    # 연식 정보 제거 (예: "(09년~12년)", "(20년~현재)")
    title = re.sub(r'\(\d{2}년~[^\)]+\)', '', title)

    # 배기량 정보 제거
    title = re.sub(r'\d{3,4}\s*cc', '', title, flags=re.IGNORECASE)
    title = re.sub(r'\d\.\d\s*(?:터보|T)?', '', title)

    # 연료 타입 제거
    for keyword in FUEL_TYPE_ALIASES.keys():
        title = title.replace(keyword, '')

    # 정리
    title = re.sub(r'\s+', ' ', title).strip()

    # 모델명 접두어 패턴 제거 (더 뉴, 올 뉴, 신형, NEW 등)
    # 이들은 모델명이 아니라 세대/버전 수식어임
    model_prefix_patterns = [
        r'^더\s*뉴\s*',           # 더 뉴
        r'^더뉴\s*',              # 더뉴 (붙여쓰기)
        r'^올\s*뉴\s*',           # 올 뉴
        r'^디\s*올\s*뉴\s*',       # 디 올 뉴
        r'^신형\s*',              # 신형
        r'^NEW\s+',              # NEW
        r'^뉴\s*',                # 뉴
        r'^NF\s+',               # NF (쏘나타 세대명)
        r'^LF\s+',               # LF (쏘나타 세대명)
        r'^YF\s+',               # YF (쏘나타 세대명)
    ]

    for pattern in model_prefix_patterns:
        title = re.sub(pattern, '', title, flags=re.IGNORECASE)

    title = title.strip()

    # 복합 모델명 먼저 확인 (그랜드 스타렉스 등)
    for compound, normalized in COMPOUND_MODEL_NAMES.items():
        if compound in original_title:
            # 복합 모델명 이후 텍스트를 트림으로
            idx = original_title.find(compound)
            after = original_title[idx + len(compound):].strip()
            # 트림에서 연식, 연료 등 제거
            after = re.sub(r'\(\d{2}년~[^\)]+\)', '', after)
            after = re.sub(r'\d{3,4}\s*cc', '', after, flags=re.IGNORECASE)
            after = re.sub(r'\s+', ' ', after).strip()
            trim = after if len(after) > 2 else None
            return normalized, trim

    # 첫 단어를 모델명으로, 나머지를 트림으로
    parts = title.split(maxsplit=1)
    model = parts[0] if parts else None
    trim = parts[1].strip() if len(parts) > 1 else None

    # 모델명 정규화
    if model:
        model = _normalize_model_name(model)

    # 트림이 너무 짧으면 None
    if trim and len(trim) < 2:
        trim = None

    return model, trim


def parse_title(title: str) -> ParsedTitle:
    """
    차량 제목을 파싱하여 구조화된 정보 반환

    Args:
        title: 원본 차량 제목 (Post Title)

    Returns:
        ParsedTitle: 파싱된 차량 정보
    """
    if not title:
        return ParsedTitle()

    result = ParsedTitle()

    # 1. JSON 기준 매칭 시도 (car_models.json 기반)
    try:
        match_result: MatchResult = match_car_model(title)
        result.manufacturer_id = match_result.manufacturer_id
        result.model_id = match_result.model_id
        result.trim_id = match_result.trim_id

        # JSON 매칭 결과로 텍스트 값 설정
        if match_result.manufacturer_name:
            result.manufacturer = match_result.manufacturer_name
        if match_result.model_name:
            result.model = match_result.model_name
        if match_result.trim_name:
            result.trim = match_result.trim_name
    except Exception:
        # JSON 매칭 실패 시 기존 로직 사용
        pass

    # 2. JSON 매칭 결과가 없으면 기존 파싱 로직 사용
    if not result.manufacturer:
        result.manufacturer, remaining = _extract_manufacturer(title)
    else:
        _, remaining = _extract_manufacturer(title)

    # 3. 배기량 추출
    result.engine_cc = _extract_engine_cc(title)

    # 4. 연료 타입 추출
    result.fuel_type = _extract_fuel_type(title)

    # 5. 세부 모델 추출
    result.sub_model = _extract_sub_model(title)

    # 6. 모델명과 트림 추출 (JSON 매칭 결과가 없는 경우만)
    if not result.model:
        result.model, text_trim = _extract_model_and_trim(remaining, result.manufacturer)
        if not result.trim:
            result.trim = text_trim

    return result


def normalize_fuel(raw_fuel: str) -> Optional[str]:
    """원본 fuel 필드 정규화"""
    if not raw_fuel:
        return None

    raw_fuel = raw_fuel.strip()

    # 직접 매핑 확인
    if raw_fuel in FUEL_TYPE_ALIASES:
        return FUEL_TYPE_ALIASES[raw_fuel]

    # 용도 정보인 경우 (자가용, 렌터카)
    if raw_fuel in USAGE_TYPE_ALIASES:
        return None  # 연료가 아니라 용도임

    return raw_fuel


def normalize_transmission(raw_trans: str) -> Optional[str]:
    """원본 trans 필드 정규화"""
    if not raw_trans:
        return None

    raw_trans = raw_trans.strip()
    return TRANSMISSION_ALIASES.get(raw_trans, raw_trans)


def normalize_usage_type(raw_fuel: str) -> Optional[str]:
    """원본 fuel 필드에서 용도 추출 (자가용, 렌터카 등)"""
    if not raw_fuel:
        return None

    raw_fuel = raw_fuel.strip()

    if raw_fuel in USAGE_TYPE_ALIASES:
        return USAGE_TYPE_ALIASES[raw_fuel]

    return None


def normalize_score(raw_score: str) -> Optional[str]:
    """원본 score 필드 정규화"""
    if not raw_score:
        return None

    # "A / 4" -> "A4", "BB" -> "BB" 등
    score = raw_score.strip()
    score = re.sub(r'\s*/\s*', '', score)  # 공백과 슬래시 제거

    return score if score else None
