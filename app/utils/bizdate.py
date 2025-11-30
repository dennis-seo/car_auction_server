from __future__ import annotations

from datetime import date, timedelta


def _parse_yymmdd(value: str) -> date:
    # YYMMDD -> 2000-based year assumption
    if len(value) != 6 or not value.isdigit():
        raise ValueError("invalid yymmdd")
    yy = int(value[:2])
    mm = int(value[2:4])
    dd = int(value[4:6])
    return date(2000 + yy, mm, dd)


def _format_yymmdd(d: date) -> str:
    return d.strftime("%y%m%d")


def next_business_day(yymmdd: str) -> str:
    d = _parse_yymmdd(yymmdd)
    wd = d.weekday()  # Mon=0 .. Sun=6
    if wd <= 3:  # Mon..Thu -> next day
        nd = d + timedelta(days=1)
    elif wd == 4:  # Fri -> Mon (+3)
        nd = d + timedelta(days=3)
    elif wd == 5:  # Sat -> Mon (+2)
        nd = d + timedelta(days=2)
    else:  # Sun -> Mon (+1)
        nd = d + timedelta(days=1)
    return _format_yymmdd(nd)


def previous_source_candidates_for_mapped(yymmdd_mapped: str) -> list[str]:
    """
    For a mapped business date (the doc id), return plausible source dates (original file dates)
    in preference order to locate the underlying file/content.
    - Tue..Fri -> [prev day]
    - Mon -> [Sun, Sat, Fri]
    """
    d = _parse_yymmdd(yymmdd_mapped)
    wd = d.weekday()
    if 1 <= wd <= 4:  # Tue..Fri
        return [_format_yymmdd(d - timedelta(days=1))]
    # Monday
    return [
        _format_yymmdd(d - timedelta(days=1)),  # Sun
        _format_yymmdd(d - timedelta(days=2)),  # Sat
        _format_yymmdd(d - timedelta(days=3)),  # Fri
    ]


def yymmdd_to_iso(yymmdd: str) -> str:
    """
    YYMMDD 형식을 YYYY-MM-DD (ISO) 형식으로 변환

    Args:
        yymmdd: 6자리 날짜 문자열 (예: "251130")

    Returns:
        ISO 형식 날짜 문자열 (예: "2025-11-30")
    """
    if len(yymmdd) == 6 and yymmdd.isdigit():
        return f"20{yymmdd[:2]}-{yymmdd[2:4]}-{yymmdd[4:6]}"
    return yymmdd


def iso_to_yymmdd(iso_date: str) -> str:
    """
    YYYY-MM-DD (ISO) 형식을 YYMMDD 형식으로 변환

    Args:
        iso_date: ISO 형식 날짜 문자열 (예: "2025-11-30")

    Returns:
        6자리 날짜 문자열 (예: "251130")
    """
    if len(iso_date) == 10 and iso_date[4] == "-" and iso_date[7] == "-":
        return iso_date[2:4] + iso_date[5:7] + iso_date[8:10]
    return iso_date

