"""
강사 자동매칭 엔진
"""
import pandas as pd
from config import INSTRUCTOR_CONFIG


def get_used_hours(df: pd.DataFrame, instructor: str, year: int, month: int) -> float:
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
    agency   = str(row.get("의뢰기관", ""))
    location = str(row.get("방식/위치", ""))
    start    = str(row.get("시작", ""))
    wanted   = str(row.get("요청사항", ""))

    for name in INSTRUCTOR_CONFIG:
        if name in wanted:
            return name

    zoom    = is_zoom(location)
    morning = is_morning(start)

    candidates = []
    for name, cfg in INSTRUCTOR_CONFIG.items():
        if cfg.get("backup"):
            continue
        if zoom and not cfg.get("zoom"):
            continue
        if cfg.get("morning_only") and not morning:
            continue

        limit = cfg.get("limit")
        if limit:
            used = get_used_hours(df, name, year, month)
            if used >= limit:
                continue

        preferred = cfg.get("preferred_agency", [])
        score = 2 if agency in preferred else 1
        candidates.append((score, name))

    candidates.sort(key=lambda x: -x[0])
    if candidates:
        return candidates[0][1]

    for name, cfg in INSTRUCTOR_CONFIG.items():
        if cfg.get("backup"):
            return name

    return ""


def auto_match(df: pd.DataFrame, year: int, month: int):
    result  = df.copy()
    changed = 0
    for idx in result.index:
        instructor = str(result.loc[idx, "강사님"]).strip()
        if instructor and instructor not in ("", "nan"):
            continue
        row     = result.loc[idx].to_dict()
        matched = match_instructor(row, result, year, month)
        if matched:
            result.loc[idx, "강사님"] = matched
            changed += 1
    return result, changed


def check_overload(df: pd.DataFrame, year: int, month: int) -> dict:
    warnings = {}
    for name, cfg in INSTRUCTOR_CONFIG.items():
        limit = cfg.get("limit")
        if not limit:
            continue
        used = get_used_hours(df, name, year, month)
        if used > limit:
            warnings[name] = {"used": used, "limit": limit, "over": used - limit}
    return warnings


def check_date_conflicts(df: pd.DataFrame, year: int, month: int) -> list:
    """같은 날 같은 강사 시간 겹침 체크"""
    conflicts = []
    try:
        df = df.copy()
        df["_dt"] = pd.to_datetime(df["강의일시"], errors="coerce")
        fdf = df[
            (df["_dt"].dt.year  == year) &
            (df["_dt"].dt.month == month) &
            (df.get("상태", pd.Series(["정상"] * len(df))) != "취소")
        ].copy()

        for date, day_df in fdf.groupby(fdf["_dt"].dt.date):
            for instructor, i_df in day_df.groupby("강사님"):
                if not instructor or str(instructor) in ("", "nan"):
                    continue
                if len(i_df) > 1:
                    times = i_df[["시작", "종료", "의뢰기관", "과정명"]].values.tolist()
                    conflicts.append({
                        "날짜":   str(date),
                        "강사":   instructor,
                        "건수":   len(i_df),
                        "강의":   times,
                    })
    except Exception:
        pass
    return conflicts

WANTED_NAME_MAP = {
    "주영": "송주영",
    "미림": "김미림",
    "하나": "문하나",
    "미영": "노미영",
    "길매": "여길매",
    "다인": "이다인",
}

def apply_calendar_wanted(fdf, events_by_instructor):
    result  = fdf.copy()
    applied = 0
    log     = []

    # 모든 강사 캘린더 이벤트 합치기
    all_events = []
    for cal_instructor, events in events_by_instructor.items():
        for e in events:
            all_events.append((cal_instructor, e))

    for cal_instructor, e in all_events:
        title = e.get("title", "")
        if "원티드" not in title and "원티드" not in title:
            continue

        date_str = e.get("date", "")
        if not date_str:
            continue

        # 강사 찾기
        instructor = None
        for key, name in WANTED_NAME_MAP.items():
            if key in title:
                instructor = name
                break
        if not instructor:
            instructor = cal_instructor  # 캘린더 주인

        # 시간대
        morning_only   = "오전" in title
        afternoon_only = "오후" in title
        # 전일이면 둘 다 해당

        mask = result["강의일시"].astype(str).str[:10] == date_str
        for idx in result[mask].index:
            try:
                hour = int(str(result.loc[idx, "시작"]).split(":")[0])
            except Exception:
                hour = 9

            if morning_only and hour >= 13:
                continue
            if afternoon_only and hour < 13:
                continue

            result.loc[idx, "강사님"] = instructor
            applied += 1
            log.append(f"{date_str} {result.loc[idx, '시작']} → {instructor} ({title})")

    return result, applied, log
