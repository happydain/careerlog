"""
강사 자동매칭 엔진
"""
import pandas as pd
from config import INSTRUCTOR_CONFIG


def get_used_hours(df: pd.DataFrame, instructor: str, year: int, month: int) -> float:
    """해당 강사의 해당 월 누적 시수"""
    try:
        mask = (
            (df["강사님"] == instructor) &
            (pd.to_datetime(df["강의일시"], errors="coerce").dt.year == year) &
            (pd.to_datetime(df["강의일시"], errors="coerce").dt.month == month) &
            (df.get("상태", pd.Series(["정상"] * len(df))) != "취소")
        )
        return pd.to_numeric(df[mask]["시수"], errors="coerce").sum()
    except Exception:
        return 0


def is_zoom(location: str) -> bool:
    return str(location).strip() in ("줌", "zoom", "Zoom", "동시송출")


def is_morning(start_time: str) -> bool:
    try:
        hour = int(str(start_time).split(":")[0])
        return hour < 13
    except Exception:
        return True


def match_instructor(row: dict, df: pd.DataFrame, year: int, month: int) -> str:
    """
    한 강의에 대해 최적 강사 반환
    row: 강의 행 딕셔너리
    df: 전체 보건스케줄 DataFrame (누적 시수 계산용)
    """
    agency   = str(row.get("의뢰기관", ""))
    location = str(row.get("방식/위치", ""))
    start    = str(row.get("시작", ""))
    wanted   = str(row.get("요청사항", ""))  # 원티드 강사

    # 1. 원티드 최우선
    for name in INSTRUCTOR_CONFIG:
        if name in wanted:
            return name

    zoom     = is_zoom(location)
    morning  = is_morning(start)

    # 우선순위 순으로 후보 정렬
    candidates = []
    for name, cfg in INSTRUCTOR_CONFIG.items():
        if cfg.get("backup"):
            continue

        # 줌 강의인데 줌 불가 강사 제외
        if zoom and not cfg.get("zoom"):
            continue

        # 오전만 가능한 강사인데 오후 강의면 제외
        if cfg.get("morning_only") and not morning:
            continue

        # 한도 체크
        limit = cfg.get("limit")
        if limit:
            used = get_used_hours(df, name, year, month)
            if used >= limit:
                continue

        # 선호 기관 점수
        preferred = cfg.get("preferred_agency", [])
        score = 2 if agency in preferred else 1

        candidates.append((score, name))

    # 점수 높은 순으로 정렬
    candidates.sort(key=lambda x: -x[0])

    if candidates:
        return candidates[0][1]

    # 모두 안 되면 백업(이다인)
    for name, cfg in INSTRUCTOR_CONFIG.items():
        if cfg.get("backup"):
            return name

    return ""


def auto_match(df: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
    """
    미배정 강의 자동매칭
    강사님이 비어있는 행만 배정
    """
    result = df.copy()
    changed = 0

    for idx in result.index:
        instructor = str(result.loc[idx, "강사님"]).strip()
        if instructor and instructor not in ("", "nan"):
            continue  # 이미 배정된 경우 스킵

        row = result.loc[idx].to_dict()
        matched = match_instructor(row, result, year, month)

        if matched:
            result.loc[idx, "강사님"] = matched
            changed += 1

    return result, changed


def check_overload(df: pd.DataFrame, year: int, month: int) -> dict:
    """
    한도 초과 강사 체크
    반환: {강사명: {"used": 사용시수, "limit": 한도, "over": 초과시수}}
    """
    warnings = {}
    for name, cfg in INSTRUCTOR_CONFIG.items():
        limit = cfg.get("limit")
        if not limit:
            continue
        used = get_used_hours(df, name, year, month)
        if used > limit:
            warnings[name] = {
                "used":  used,
                "limit": limit,
                "over":  used - limit,
            }
    return warnings
