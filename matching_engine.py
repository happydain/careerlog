"""
강사 자동매칭 엔진
- 강사별 설정(한도, 줌가능, 선호기관, 오전만)
- 캘린더 원티드(불가 날짜/시간) 반영
- 한도 초과, 날짜 충돌 체크
"""
import pandas as pd
from config import INSTRUCTOR_CONFIG

# 캘린더 원티드 제목에서 강사 이름 매핑
WANTED_NAME_MAP = {
    "주영": "송주영",
    "미림": "김미림",
    "하나": "문하나",
    "미영": "노미영",
    "길매": "여길매",
    "다인": "이다인",
}


# ── 헬퍼 ──────────────────────────────────────

def get_used_hours(df: pd.DataFrame, instructor: str, year: int, month: int) -> float:
    try:
        mask = (
            (df["강사님"] == instructor) &
            (pd.to_datetime(df["강의일시"], errors="coerce").dt.year  == year) &
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
        return int(str(start_time).split(":")[0]) < 13
    except Exception:
        return True


# ── 캘린더 원티드 → 불가 딕셔너리 ───────────────

def build_unavailable(events_by_instructor: dict) -> dict:
    """
    캘린더 원티드 이벤트 → 강사별 불가 날짜/시간
    반환: {강사명: [{"date": "2026-06-10", "morning": bool, "afternoon": bool}]}
    """
    unavailable = {}

    for cal_instructor, events in events_by_instructor.items():
        for e in events:
            title = e.get("title", "")
            if "원티드" not in title:
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
                instructor = cal_instructor

            has_morning   = "오전" in title
            has_afternoon = "오후" in title
            has_jeonil    = "전일" in title

            # 오전/오후 명시 없으면 전일 불가
            if has_jeonil or (not has_morning and not has_afternoon):
                morning_block   = True
                afternoon_block = True
            else:
                morning_block   = has_morning
                afternoon_block = has_afternoon

            if instructor not in unavailable:
                unavailable[instructor] = []
            unavailable[instructor].append({
                "date":      date_str,
                "morning":   morning_block,
                "afternoon": afternoon_block,
                "title":     title,
            })

    return unavailable


def is_blocked(instructor: str, date_str: str, start_time: str,
               unavailable: dict) -> bool:
    """해당 강사가 해당 날짜/시간에 불가인지 체크"""
    if not unavailable or instructor not in unavailable:
        return False
    morning = is_morning(start_time)
    for block in unavailable[instructor]:
        if block["date"] == date_str:
            if morning and block["morning"]:
                return True
            if not morning and block["afternoon"]:
                return True
    return False


# ── 매칭 로직 ─────────────────────────────────

def match_instructor(row: dict, df: pd.DataFrame, year: int, month: int,
                     unavailable: dict = None) -> str:
    agency   = str(row.get("의뢰기관", ""))
    location = str(row.get("방식/위치", ""))
    start    = str(row.get("시작", ""))
    date_str = str(row.get("강의일시", ""))[:10]
    wanted   = str(row.get("요청사항", ""))

    # 1. 요청사항에 강사 원티드
    for name in INSTRUCTOR_CONFIG:
        if name in wanted:
            return name

    zoom    = is_zoom(location)
    morning = is_morning(start)

    candidates = []
    for name, cfg in INSTRUCTOR_CONFIG.items():
        if cfg.get("backup"):
            continue

        # 줌 불가 강사
        if zoom and not cfg.get("zoom"):
            continue

        # 오전만 가능한데 오후 강의
        if cfg.get("morning_only") and not morning:
            continue

        # 캘린더 불가 날짜/시간
        if is_blocked(name, date_str, start, unavailable):
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

    candidates.sort(key=lambda x: -x[0])
    if candidates:
        return candidates[0][1]

    # 백업 강사
    for name, cfg in INSTRUCTOR_CONFIG.items():
        if cfg.get("backup"):
            if not is_blocked(name, date_str, start, unavailable):
                return name

    return ""


def auto_match(df: pd.DataFrame, year: int, month: int,
               unavailable: dict = None):
    """미배정 강의 자동매칭"""
    result  = df.copy()
    changed = 0
    for idx in result.index:
        instructor = str(result.loc[idx, "강사님"]).strip()
        if instructor and instructor not in ("", "nan"):
            continue
        row     = result.loc[idx].to_dict()
        matched = match_instructor(row, result, year, month, unavailable)
        if matched:
            result.loc[idx, "강사님"] = matched
            changed += 1
    return result, changed


# ── 체크 함수들 ────────────────────────────────

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
    """같은 날 같은 강사 중복 배정 체크"""
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
                    conflicts.append({
                        "날짜":  str(date),
                        "강사":  instructor,
                        "건수":  len(i_df),
                        "강의":  i_df[["시작", "종료", "의뢰기관", "과정명"]].values.tolist(),
                    })
    except Exception:
        pass
    return conflicts
