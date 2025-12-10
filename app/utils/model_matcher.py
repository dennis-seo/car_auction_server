"""
JSON 기반 차량 모델 매칭 유틸리티

car_models.json을 기반으로 제목에서 manufacturer_id, model_id, trim_id를 매칭합니다.

클라이언트에서 동일한 파싱을 구현하려면 다음 JSON 파일들이 필요합니다:
- app/data/car_models.json: 제조사/모델/트림 마스터 데이터
- app/data/manufacturer_aliases.json: 제조사명 정규화 매핑
- app/data/model_variations.json: 모델명 변형 매핑
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


def _get_data_path(filename: str) -> str:
    """데이터 파일 경로 반환"""
    return os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data",
        filename
    )


@lru_cache(maxsize=1)
def _load_manufacturer_aliases() -> Dict[str, str]:
    """제조사 별명 매핑 로드 (캐싱)"""
    path = _get_data_path("manufacturer_aliases.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _load_model_variations() -> Dict[str, str]:
    """모델명 변형 매핑 로드 (캐싱)"""
    path = _get_data_path("model_variations.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# 하위 호환성을 위한 변수 (JSON에서 로드)
MANUFACTURER_LABEL_MAP = _load_manufacturer_aliases()
MODEL_VARIATIONS = _load_model_variations()

# 트림 매칭용 키워드 추출 패턴
TRIM_YEAR_PATTERN = re.compile(r'\((\d{2})년~([^\)]+)\)')

# 세대코드 패턴 (B8, G70, F3 등)
GENERATION_CODE_PATTERN = re.compile(r'\b([A-Z]{1,2}\d{1,2})\b')

# 세대 숫자 패턴 (4세대, 5세대 등)
GENERATION_NUMBER_PATTERN = re.compile(r'(\d)세대')

# 세대코드 → 트림 키워드 매핑 (경매장 세대코드가 트림명과 다를 때)
GENERATION_TO_TRIM_KEYWORD = {
    # 현대 쏘나타
    'DN8': '신형쏘나타',
    # 현대 그랜저
    'IG': '그랜저IG',
    'HG': '그랜저HG',
    'TG': '그랜저TG',
    # 현대 아반떼
    'AD': '아반떼AD',
    'CN7': '아반떼CN7',
    'MD': '아반떼MD',
    'HD': '아반떼HD',
    'XD': '아반떼XD',
    # 기아 K5
    'DL3': '신형K5',
}


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
    # 특수 케이스: 제네시스 브랜드 모델 (G70/G80/G90/GV60/GV70/GV80)
    # "현대 제네시스 G80" 같은 경우에도 제네시스 브랜드로 인식
    genesis_models = re.search(r'GENESIS\s+(G70|G80|G90|GV60|GV70|GV80)|제네시스\s+(G70|G80|G90|GV60|GV70|GV80)', title, re.IGNORECASE)
    if genesis_models:
        return "제네시스", title

    # 특수 케이스: 테슬라 (TESLA로 시작하거나 포함)
    if re.search(r'TESLA\s+(MODEL|모델)', title, re.IGNORECASE):
        return "테슬라", title

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


def _is_word_boundary_match(text: str, keyword: str) -> bool:
    """
    키워드가 텍스트에서 독립된 단어로 존재하는지 확인

    예: "XM3"에서 "M3"는 False (앞에 X가 붙어있음)
        "BMW M3"에서 "M3"는 True (독립된 단어)
    """
    # 정규식: 앞뒤로 알파벳/숫자가 아닌 문자이거나 문자열 시작/끝
    pattern = r'(?<![A-Za-z0-9가-힣])' + re.escape(keyword) + r'(?![A-Za-z0-9가-힣])'
    return bool(re.search(pattern, text))


def _find_model_in_text(text: str, manufacturer_label: Optional[str]) -> Optional[Tuple[Dict, Dict]]:
    """텍스트에서 모델 찾기"""
    model_index = _get_model_index()
    normalized = _normalize_model_text(text)

    # 제조사가 지정된 경우: 해당 제조사 모델만 필터링하여 검색
    if manufacturer_label:
        # 해당 제조사의 모델만 추출
        manufacturer_models: Dict[str, List[Tuple[Dict, Dict]]] = {}
        for model_name, entries in model_index.items():
            for mfr, model in entries:
                if mfr.get("label") == manufacturer_label:
                    if model_name not in manufacturer_models:
                        manufacturer_models[model_name] = []
                    manufacturer_models[model_name].append((mfr, model))

        # 0. 변형 모델명으로 먼저 시도 (MODEL Y → 모델Y 등)
        sorted_variations = sorted(MODEL_VARIATIONS.items(), key=lambda x: len(x[0]), reverse=True)
        for variation, canonical in sorted_variations:
            if _is_word_boundary_match(text, variation) or _is_word_boundary_match(normalized, variation):
                if canonical in manufacturer_models:
                    entries = manufacturer_models[canonical]
                    if entries:
                        return entries[0]

        # 1. 길이 역순 정렬 (긴 모델명 우선 매칭: XM3 > M3)
        sorted_models = sorted(manufacturer_models.items(), key=lambda x: len(x[0]), reverse=True)

        for model_name, entries in sorted_models:
            # 단어 경계 매칭 확인
            if _is_word_boundary_match(normalized, model_name) or _is_word_boundary_match(text, model_name):
                if entries:
                    return entries[0]

        # 2. 단어 경계 매칭 실패 시, substring 매칭 시도 (긴 것 우선)
        for model_name, entries in sorted_models:
            if model_name in normalized or model_name in text:
                if entries:
                    return entries[0]

        return None

    # 제조사 미지정: 전체 모델에서 검색

    # 1. 변형 모델명으로 먼저 시도 (긴 키워드 우선 - GENESIS G80, TESLA MODEL Y 등)
    sorted_variations = sorted(MODEL_VARIATIONS.items(), key=lambda x: len(x[0]), reverse=True)
    for variation, canonical in sorted_variations:
        if _is_word_boundary_match(text, variation) or _is_word_boundary_match(normalized, variation):
            if canonical in model_index:
                entries = model_index[canonical]
                if entries:
                    return entries[0]

    # 2. 정확한 모델명 매칭 시도 (단어 경계 확인)
    sorted_models = sorted(model_index.items(), key=lambda x: len(x[0]), reverse=True)
    for model_name, entries in sorted_models:
        if _is_word_boundary_match(normalized, model_name) or _is_word_boundary_match(text, model_name):
            if entries:
                return entries[0]

    # 3. 첫 단어로 시도
    first_word = normalized.split()[0] if normalized.split() else None
    if first_word:
        # 변형 확인
        canonical = MODEL_VARIATIONS.get(first_word, first_word)
        if canonical in model_index:
            entries = model_index[canonical]
            if entries:
                return entries[0]

    return None


def _check_keyword_in_title(title: str, keyword: str) -> bool:
    """
    키워드가 제목에 독립된 단어로 존재하는지 확인

    'N'의 경우 'DN8'에서는 False, '쏘나타 N'에서는 True
    """
    if keyword == "N":
        # N은 독립 단어로 있어야 함 (앞뒤로 공백/괄호/문자열끝)
        return bool(re.search(r'(?<![A-Za-z0-9])N(?![A-Za-z0-9])', title))
    return keyword in title


def _parse_year_range(year_str: str) -> Tuple[Optional[int], Optional[int]]:
    """
    연식 범위 문자열 파싱

    예: "(08년~16년)" → (8, 16)
        "(16년~현재)" → (16, 99)
    """
    match = TRIM_YEAR_PATTERN.search(year_str)
    if not match:
        return None, None

    start_year = int(match.group(1))
    end_part = match.group(2)

    if "현재" in end_part:
        end_year = 99  # 현재 = 무한대
    else:
        # "16년" 에서 숫자 추출
        end_match = re.search(r'(\d{2})년', end_part)
        end_year = int(end_match.group(1)) if end_match else 99

    return start_year, end_year


def _extract_title_year(title: str) -> Optional[int]:
    """
    제목에서 차량 연식 추출 (마지막 연식 범위 사용)

    예: "아우디 NEW A4(05~16년) 2.0 TDI 콰트로 다이나믹 B8 (13년~14년)"
        → 13 (마지막 괄호의 시작 연도)
    """
    matches = TRIM_YEAR_PATTERN.findall(title)
    if matches:
        # 마지막 매칭의 시작 연도 사용
        return int(matches[-1][0])
    return None


def _extract_generation_code(text: str) -> Optional[str]:
    """
    텍스트에서 세대코드 추출 (B8, G70, F3 등)

    트림명에 자주 등장하는 코드 우선 매칭
    모델명과 혼동될 수 있는 코드(K5, K7, Q3 등)는 제외
    """
    # 모델명으로 사용되는 코드들 (세대코드에서 제외)
    model_name_codes = {'K3', 'K5', 'K7', 'K8', 'K9',
                        'Q2', 'Q3', 'Q5', 'Q7', 'Q8',
                        'X1', 'X3', 'X5', 'X6', 'X7',
                        'A3', 'A4', 'A5', 'A6', 'A7', 'A8',
                        'S3', 'S4', 'S5', 'S6', 'S7', 'S8',
                        'E1', 'E2', 'E3', 'E4', 'E5', 'E6'}

    # 일반적인 세대코드 패턴들
    common_codes = ['B5', 'B6', 'B7', 'B8', 'B9',  # 아우디
                    'E90', 'E60', 'F30', 'G20', 'G30', 'G70',  # BMW
                    'W212', 'W213', 'W222', 'W223',  # 벤츠
                    'F3', 'DM', 'DN8', 'CN7', 'NX4', 'DL3',  # 기타
                    'AD', 'MD', 'HD', 'XD',  # 현대 아반떼
                    'IG', 'HG', 'TG',  # 현대 그랜저
                    'TM', 'CM',  # 현대 싼타페
                    'LF', 'YF', 'NF']  # 현대 쏘나타

    for code in common_codes:
        if code in text.upper() and code not in model_name_codes:
            return code

    # 일반 패턴 매칭 (모델명 제외)
    match = GENERATION_CODE_PATTERN.search(text)
    if match:
        code = match.group(1).upper()
        if code not in model_name_codes:
            return code

    return None


def _find_best_trim(trims: List[Dict], title: str, fuel_type: Optional[str] = None) -> Optional[Dict]:
    """트림 목록에서 가장 적합한 트림 찾기"""
    if not trims:
        return None

    # 제목에서 연식 추출 (마지막 연식 범위 사용)
    title_year = _extract_title_year(title)

    # 제목에서 세대코드 추출
    title_gen_code = _extract_generation_code(title)

    # 제목에서 세대 숫자 추출 (4세대, 5세대 등)
    gen_num_match = GENERATION_NUMBER_PATTERN.search(title)
    title_gen_num = int(gen_num_match.group(1)) if gen_num_match else None

    best_trim = None
    best_score = -1

    for trim in trims:
        trim_name = trim.get("trim", "")
        score = 0

        # 1. 세대코드 매칭 (B8, G70 등) - 가장 높은 우선순위
        if title_gen_code:
            trim_gen_code = _extract_generation_code(trim_name)
            if trim_gen_code and title_gen_code.upper() == trim_gen_code.upper():
                score += 20  # 세대코드 정확 매칭
            else:
                # 세대코드 → 트림 키워드 매핑 확인
                mapped_keyword = GENERATION_TO_TRIM_KEYWORD.get(title_gen_code.upper())
                if mapped_keyword and mapped_keyword.replace(' ', '') in trim_name.replace(' ', ''):
                    score += 18  # 매핑된 키워드 매칭

        # 2. 연식 범위 매칭
        trim_start, trim_end = _parse_year_range(trim_name)
        if trim_start is not None and title_year is not None:
            # 차량 연식이 트림 범위 내에 있는지 확인
            if trim_start <= title_year <= trim_end:
                score += 15  # 범위 내 매칭
            elif title_year == trim_start:
                score += 10  # 시작 연도 정확 매칭
            elif abs(title_year - trim_start) <= 2:
                score += 5   # 근접 매칭

        # 3. 트림명 접두어/키워드 매칭 (더 뉴, 신형, 올 뉴 등)
        # 제목과 트림명에서 동일한 접두어가 있으면 점수 부여
        # 공백을 제거하고 비교 (신형 K5 vs 신형K5)
        title_normalized = title.replace(' ', '')
        trim_normalized = trim_name.replace(' ', '')

        trim_prefixes = ['더뉴', '뉴신형', '신형', '올뉴', '디올뉴', 'THENEW', 'ALLNEW']
        prefix_matched = False
        for prefix in trim_prefixes:
            title_has = prefix in title_normalized
            trim_has = prefix in trim_normalized
            if title_has and trim_has:
                score += 10  # 접두어 매칭
                prefix_matched = True
                break
            elif title_has and not trim_has:
                score -= 3   # 제목에는 있는데 트림에 없으면 페널티
            elif not title_has and trim_has:
                score -= 1   # 트림에만 있으면 약한 페널티

        # 세대 숫자 매칭 (4세대 → B8 등) - 접두어 매칭 안됐을 때만
        if not prefix_matched and title_gen_num and len(trims) > 1:
            # 하이브리드 트림 제외하고 인덱스 계산
            non_hybrid_trims = [t for t in trims if '하이브리드' not in t.get('trim', '')]
            if trim in non_hybrid_trims:
                trim_index = non_hybrid_trims.index(trim)
                estimated_gen = len(non_hybrid_trims) - trim_index
                if estimated_gen == title_gen_num:
                    score += 8

        # 4. 연료 타입 매칭 (하이브리드, 전기 등)
        is_hybrid_trim = "하이브리드" in trim_name
        is_ev_trim = "일렉트릭" in trim_name or "EV" in trim_name or "전기" in trim_name
        is_phev_trim = "플러그인" in trim_name or "PHEV" in trim_name

        if fuel_type == "하이브리드":
            if is_hybrid_trim:
                score += 5
            else:
                score -= 3
        elif fuel_type == "전기":
            if is_ev_trim:
                score += 5
            else:
                score -= 3
        elif fuel_type == "플러그인하이브리드":
            if is_phev_trim:
                score += 5
            else:
                score -= 3
        else:
            # 연료 타입 미지정 시, 일반 트림 우선 (하이브리드/전기 트림 페널티)
            if is_hybrid_trim or is_ev_trim or is_phev_trim:
                score -= 2

        # 5. 키워드 매칭 (N 라인 등)
        keywords = ["N"]
        for kw in keywords:
            title_has_kw = _check_keyword_in_title(title, kw)
            trim_has_kw = kw in trim_name
            if title_has_kw and trim_has_kw:
                score += 3
            elif title_has_kw and not trim_has_kw:
                score -= 2

        if score > best_score:
            best_score = score
            best_trim = trim

    # 매칭 점수가 너무 낮으면 첫 번째 트림 반환
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

        # 4. 트림 찾기 (fuel_type 힌트 추출)
        fuel_type = None
        if "(H)" in title or "(HEV)" in title or "하이브리드" in title:
            fuel_type = "하이브리드"
        elif "(PHEV)" in title or "플러그인" in title:
            fuel_type = "플러그인하이브리드"
        elif "EV" in title or "일렉트릭" in title or "전기" in title:
            fuel_type = "전기"

        trims = model_info.get("trims", [])
        best_trim = _find_best_trim(trims, title, fuel_type)
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
