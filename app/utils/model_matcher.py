"""
JSON 기반 차량 모델 매칭 유틸리티

car_models.json을 기반으로 제목에서 manufacturer_id, model_id, trim_id를 매칭합니다.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional, Tuple


@dataclass
class MatchResult:
    """매칭 결과"""
    manufacturer_id: Optional[str] = None
    manufacturer_name: Optional[str] = None
    model_id: Optional[str] = None
    model_name: Optional[str] = None
    trim_id: Optional[str] = None
    trim_name: Optional[str] = None


# 제조사 별명 → JSON label 매핑
MANUFACTURER_LABEL_MAP = {
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
    "도요타": "토요타",
    "렉서스": "렉서스",
    "혼다": "혼다",
    "닛산": "닛산",
    "스바루": "스바루",

    # 수입 - 미국
    "포드": "포드",
    "링컨": "링컨",
    "지프": "지프",
    "캐딜락": "캐딜락",
    "테슬라": "테슬라",
    "크라이슬러": "크라이슬러",

    # 수입 - 기타
    "볼보": "볼보",
    "랜드로버": "랜드로버",
    "재규어": "재규어",
    "마세라티": "마세라티",
    "푸조": "푸조",
}

# 모델명 변형 패턴 (title에서 → JSON model명)
MODEL_VARIATIONS = {
    # 현대
    "그랜져": "그랜저",
    "싼타페": "싼타페",
    "산타페": "싼타페",
    "투싼": "투싼",
    "투쌍": "투싼",
    "벨로스터": "벨로스터",
    "코나": "코나",
    "넥소": "넥쏘",
    "스타리아": "스타리아",
    "그랜드스타렉스": "스타렉스",
    "스타렉스": "스타렉스",
    "포터2": "포터",
    "포터II": "포터",
    "마이티": "마이티",

    # 기아
    "쏘렌토": "쏘렌토",
    "소렌토": "쏘렌토",
    "카니발": "카니발",
    "봉고3": "봉고",
    "봉고Ⅲ": "봉고",
    "봉고III": "봉고",
    "셀토스": "셀토스",
    "스포티지": "스포티지",
    "K3": "K3",
    "K5": "K5",
    "K7": "K7",
    "K8": "K8",
    "K9": "K9",
    "EV6": "EV6",
    "EV9": "EV9",
    "니로": "니로",
    "레이": "레이",
    "모닝": "모닝",

    # 제네시스
    "G70": "G70",
    "G80": "G80",
    "G90": "G90",
    "GV60": "GV60",
    "GV70": "GV70",
    "GV80": "GV80",

    # 벤츠 (JSON에는 "E클래스" 형태로 저장됨)
    "E-클래스": "E클래스",
    "E클래스": "E클래스",
    "C-클래스": "C클래스",
    "C클래스": "C클래스",
    "S-클래스": "S클래스",
    "S클래스": "S클래스",
    "A-클래스": "A클래스",
    "A클래스": "A클래스",
    "GLE-클래스": "GLE",
    "GLE클래스": "GLE",
    "GLC-클래스": "GLC",
    "GLC클래스": "GLC",
    "GLB-클래스": "GLB",
    "GLB클래스": "GLB",
    "GLA-클래스": "GLA",
    "GLA클래스": "GLA",
    "CLA-클래스": "CLA",
    "CLA클래스": "CLA",
    "CLS-클래스": "CLS",
    "CLS클래스": "CLS",
    "G-클래스": "G클래스",
    "G클래스": "G클래스",
    "GLS-클래스": "GLS",
    "GLS클래스": "GLS",

    # BMW
    "3시리즈": "3시리즈",
    "5시리즈": "5시리즈",
    "7시리즈": "7시리즈",
    "1시리즈": "1시리즈",
    "4시리즈": "4시리즈",
    "X1": "X1",
    "X3": "X3",
    "X5": "X5",
    "X6": "X6",
    "X7": "X7",

    # 아우디
    "A3": "A3",
    "A4": "A4",
    "A5": "A5",
    "A6": "A6",
    "A7": "A7",
    "Q3": "Q3",
    "Q5": "Q5",
    "Q7": "Q7",
    "Q8": "Q8",
    "e-tron": "e-트론",
    "이트론": "e-트론",

    # 테슬라 (모델 3, 모델Y 등)
    "모델3": "모델3",
    "모델 3": "모델3",
    "Model3": "모델3",
    "Model 3": "모델3",
    "모델Y": "모델Y",
    "모델 Y": "모델Y",
    "ModelY": "모델Y",
    "Model Y": "모델Y",
    "모델S": "모델S",
    "모델 S": "모델S",
    "ModelS": "모델S",
    "Model S": "모델S",
    "모델X": "모델X",
    "모델 X": "모델X",
    "ModelX": "모델X",
    "Model X": "모델X",

    # 렉서스
    "ES300": "ES",
    "ES350": "ES",
    "RX350": "RX",
    "RX450": "RX",
    "NX300": "NX",
    "NX350": "NX",
    "LS500": "LS",

    # 볼보
    "XC40": "XC40",
    "XC60": "XC60",
    "XC90": "XC90",
    "XC70": "XC70",
    "S40": "S40",
    "S60": "S60",
    "S90": "S90",
    "V40": "V40",
    "V60": "V60",

    # 닛산
    "알티마": "알티마",
    "로그": "로그",
    "맥시마": "맥시마",
    "무라노": "무라노",
    "큐브": "큐브",

    # 링컨
    "에비에이터": "에비에이터",
    "MKZ": "MKZ",
    "MKS": "MKS",
    "MKX": "MKX",
    "네비게이터": "네비게이터",
    "노틸러스": "노틸러스",

    # 캐딜락
    "ATS": "ATS",
    "ATS-V": "ATS",
    "CTS": "CTS",
    "CT6": "CT6",
    "XT5": "XT5",
    "에스컬레이드": "에스컬레이드",

    # 마세라티
    "르반떼": "르반떼",
    "레반테": "르반떼",
    "기블리": "기블리",
    "콰트로포르테": "콰트로포르테",
    "그란투리스모": "그란투리스모",
    "그란카브리오": "그란카브리오",

    # 푸조
    "308": "308",
    "308SW": "308",
    "508": "508",
    "2008": "2008",
    "e-2008": "2008",
    "3008": "3008",
    "5008": "5008",

    # 크라이슬러
    "300C": "300C",
    "퍼시피카": "퍼시피카",

    # 스바루
    "아웃백": "아웃백",
    "포레스터": "포레스터",
    "XV": "XV",
    "레거시": "레거시",

    # 현대 추가 모델
    "제네시스": "제네시스",
    "제네시스쿠페": "제네시스쿠페",
    "다이너스티": "다이너스티",
    "카운티": "카운티",
    "e-카운티": "카운티",

    # 쉐보레 추가 모델
    "콜로라도": "콜로라도",
    "이쿼녹스": "이쿼녹스",
    "알페온": "알페온",
    "트래버스": "트래버스",
    "라세티": "라세티",
    "라세티프리미어": "라세티",

    # 토요타 추가 모델
    "아발론": "아발론",
    "시에나": "시에나",
    "하이랜더": "하이랜더",

    # BMW 추가 모델
    "6시리즈": "6시리즈",
    "그란투리스모": "GT",
    "M3": "M3",
    "M4": "M4",
    "X4": "X4",
    "X7": "X7",

    # 포드 추가 모델
    "토러스": "토러스",
    "뉴토러스": "토러스",
    "포커스": "포커스",
    "브롱코": "브롱코",

    # 벤츠 추가 모델
    "M-클래스": "M클래스",
    "M클래스": "M클래스",
    "ML": "M클래스",
    "GLK-클래스": "GLK",
    "GLK클래스": "GLK",

    # 혼다 추가 모델
    "HR-V": "HR-V",
    "파일럿": "파일럿",

    # 랜드로버 추가 모델
    "프리랜더": "프리랜더",
    "프리랜더2": "프리랜더",

    # 렉서스 추가 모델
    "IS": "IS",
    "IS250": "IS",
    "IS300": "IS",
    "CT": "CT",
    "CT200h": "CT",
    "GS": "GS",
    "LC": "LC",
    "UX": "UX",

    # 르노삼성 추가 모델
    "클리오": "클리오",
    "마스터": "마스터",

    # 기아 추가 모델
    "EV9": "EV9",
}

# 트림 매칭용 키워드 추출 패턴
TRIM_YEAR_PATTERN = re.compile(r'\((\d{2})년~([^\)]+)\)')


@lru_cache(maxsize=1)
def _load_car_models() -> Dict:
    """JSON 파일 로드 (캐싱)"""
    json_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data",
        "car_models.json"
    )

    if not os.path.exists(json_path):
        return {"domestic": [], "import": []}

    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_manufacturer_index() -> Dict[str, Dict]:
    """제조사명 → 제조사 정보 인덱스 구축"""
    data = _load_car_models()
    index: Dict[str, Dict] = {}

    for category in ["domestic", "import"]:
        for mfr in data.get(category, []):
            label = mfr.get("label", "")
            index[label] = mfr

    return index


def _build_model_index() -> Dict[str, List[Tuple[Dict, Dict]]]:
    """모델명 → [(제조사정보, 모델정보)] 인덱스 구축"""
    data = _load_car_models()
    index: Dict[str, List[Tuple[Dict, Dict]]] = {}

    for category in ["domestic", "import"]:
        for mfr in data.get(category, []):
            for model in mfr.get("models", []):
                model_name = model.get("model", "")
                if model_name not in index:
                    index[model_name] = []
                index[model_name].append((mfr, model))

    return index


# 인덱스 캐시
_MFR_INDEX: Optional[Dict[str, Dict]] = None
_MODEL_INDEX: Optional[Dict[str, List[Tuple[Dict, Dict]]]] = None


def _get_mfr_index() -> Dict[str, Dict]:
    global _MFR_INDEX
    if _MFR_INDEX is None:
        _MFR_INDEX = _build_manufacturer_index()
    return _MFR_INDEX


def _get_model_index() -> Dict[str, List[Tuple[Dict, Dict]]]:
    global _MODEL_INDEX
    if _MODEL_INDEX is None:
        _MODEL_INDEX = _build_model_index()
    return _MODEL_INDEX


def _extract_manufacturer_from_title(title: str) -> Tuple[Optional[str], str]:
    """제목에서 제조사 추출"""
    # [제조사] 형태
    bracket_match = re.match(r'^\[([^\]]+)\]\s*', title)
    if bracket_match:
        raw = bracket_match.group(1)
        remaining = title[bracket_match.end():]
        label = MANUFACTURER_LABEL_MAP.get(raw, raw)
        return label, remaining

    # "제조사 모델명" 형태
    parts = title.split(maxsplit=1)
    if parts:
        first = parts[0]
        # 괄호 포함 제조사 (쉐보레(한국GM))
        paren_match = re.match(r'^([^\(]+)(\([^\)]+\))?', first)
        if paren_match:
            full = paren_match.group(0)
            if full in MANUFACTURER_LABEL_MAP:
                remaining = parts[1] if len(parts) > 1 else ""
                return MANUFACTURER_LABEL_MAP[full], remaining
            base = paren_match.group(1)
            if base in MANUFACTURER_LABEL_MAP:
                remaining = parts[1] if len(parts) > 1 else ""
                return MANUFACTURER_LABEL_MAP[base], remaining

    return None, title


def _normalize_model_text(text: str) -> str:
    """모델명 텍스트 정규화 (검색용)"""
    # 접두어 제거
    prefixes = [
        r'^더\s*뉴\s*', r'^더뉴\s*',
        r'^올\s*뉴\s*', r'^디\s*올\s*뉴\s*',
        r'^신형\s*', r'^NEW\s+', r'^뉴\s*',
        r'^NF\s+', r'^LF\s+', r'^YF\s+',
    ]
    for p in prefixes:
        text = re.sub(p, '', text, flags=re.IGNORECASE)

    # 연식 제거
    text = re.sub(r'\(\d{2}년~[^\)]+\)', '', text)

    # 세대코드 제거
    text = re.sub(r'\([A-Z]{1,3}\d{1,3}\)', '', text)
    text = re.sub(r'\(DM\)|\(DN8\)|\(CN7\)|\(NX4\)', '', text)

    return text.strip()


def _find_model_in_text(text: str, manufacturer_label: Optional[str]) -> Optional[Tuple[Dict, Dict]]:
    """텍스트에서 모델 찾기"""
    model_index = _get_model_index()
    normalized = _normalize_model_text(text)

    # 1. 정확한 모델명 매칭 시도
    for model_name, entries in model_index.items():
        if model_name in normalized or model_name in text:
            # 제조사가 지정된 경우 해당 제조사 모델만
            if manufacturer_label:
                for mfr, model in entries:
                    if mfr.get("label") == manufacturer_label:
                        return (mfr, model)
            # 제조사 미지정시 첫 번째 매칭
            if entries:
                return entries[0]

    # 2. 변형 모델명으로 시도
    for variation, canonical in MODEL_VARIATIONS.items():
        if variation in normalized or variation in text:
            if canonical in model_index:
                entries = model_index[canonical]
                if manufacturer_label:
                    for mfr, model in entries:
                        if mfr.get("label") == manufacturer_label:
                            return (mfr, model)
                if entries:
                    return entries[0]

    # 3. 첫 단어로 시도
    first_word = normalized.split()[0] if normalized.split() else None
    if first_word:
        # 변형 확인
        canonical = MODEL_VARIATIONS.get(first_word, first_word)
        if canonical in model_index:
            entries = model_index[canonical]
            if manufacturer_label:
                for mfr, model in entries:
                    if mfr.get("label") == manufacturer_label:
                        return (mfr, model)
            if entries:
                return entries[0]

    return None


def _find_best_trim(trims: List[Dict], title: str) -> Optional[Dict]:
    """트림 목록에서 가장 적합한 트림 찾기"""
    if not trims:
        return None

    # 연식 추출
    year_match = TRIM_YEAR_PATTERN.search(title)
    title_year = year_match.group(1) if year_match else None

    best_trim = None
    best_score = -1

    for trim in trims:
        trim_name = trim.get("trim", "")
        score = 0

        # 연식 매칭
        trim_year_match = TRIM_YEAR_PATTERN.search(trim_name)
        if trim_year_match and title_year:
            trim_start_year = trim_year_match.group(1)
            if title_year == trim_start_year:
                score += 10
            elif abs(int(title_year) - int(trim_start_year)) <= 2:
                score += 5

        # 키워드 매칭 (하이브리드, N, 일렉트릭 등)
        keywords = ["하이브리드", "N", "일렉트릭", "플러그인", "PHEV"]
        for kw in keywords:
            if kw in title and kw in trim_name:
                score += 3
            elif kw in title and kw not in trim_name:
                score -= 2

        if score > best_score:
            best_score = score
            best_trim = trim

    # 매칭 점수가 너무 낮으면 None
    return best_trim if best_score >= 0 else (trims[0] if trims else None)


def match_car_model(title: str) -> MatchResult:
    """
    차량 제목에서 manufacturer_id, model_id, trim_id 매칭

    Args:
        title: 차량 제목 (Post Title)

    Returns:
        MatchResult: 매칭된 ID들
    """
    if not title:
        return MatchResult()

    result = MatchResult()

    # 1. 제조사 추출
    mfr_label, remaining = _extract_manufacturer_from_title(title)

    # 2. 제조사 정보 조회
    mfr_index = _get_mfr_index()
    if mfr_label and mfr_label in mfr_index:
        mfr = mfr_index[mfr_label]
        result.manufacturer_id = mfr.get("id")
        result.manufacturer_name = mfr.get("label")

    # 3. 모델 찾기
    model_match = _find_model_in_text(remaining, mfr_label)
    if not model_match and mfr_label:
        # 전체 제목으로 재시도
        model_match = _find_model_in_text(title, mfr_label)

    if model_match:
        mfr_info, model_info = model_match
        # 제조사가 매칭 안됐으면 모델에서 가져온 정보 사용
        if not result.manufacturer_id:
            result.manufacturer_id = mfr_info.get("id")
            result.manufacturer_name = mfr_info.get("label")

        result.model_id = model_info.get("id")
        result.model_name = model_info.get("model")

        # 4. 트림 찾기
        trims = model_info.get("trims", [])
        best_trim = _find_best_trim(trims, title)
        if best_trim:
            result.trim_id = best_trim.get("id")
            result.trim_name = best_trim.get("trim")

    return result


def reload_car_models() -> None:
    """JSON 캐시 리로드"""
    global _MFR_INDEX, _MODEL_INDEX
    _load_car_models.cache_clear()
    _MFR_INDEX = None
    _MODEL_INDEX = None
