"""
인천대한협 전용 파서
- parse_incheon_excel: 엑셀 파일 파싱
- parse_incheon_kakao: 카톡/텍스트 파싱
공통 규칙:
- 대상자: 관리감독자 (고정)
- 강의실: 제1강의실→인천1, 제2강의실→인천2
- 업종: 기타업/제조업/건설업 자동 감지
"""
import re
import pandas as pd
from config import COLUMNS, DEFAULT_HOURLY_FEE, DEFAULT_INDUSTRY
from utils import detect_subject, parse_time_range, make_row

AGENCY = "인천대한협"
TARGET = "관리감독자"

_ROOM_MAP = {
    "제1강의실": "인천1",
    "제2강의실": "인천2",
    "1강의실":   "인천1",
    "2강의실":   "인천2",
    "제1":       "인천1",
    "제2":       "인천2",
}

def _detect_industry(text: str) -> str:
    if "제조업" in text: return "제조업"
    if "건설업" in text: return "건설업"
    return "기타업"

def _detect_room(text: str) -> str:
    for k, v in _ROOM_MAP.items():
        if k in text:
            return v
    return "인천"

def _parse_date_str(raw) -> pd.Timestamp:
    s = re.sub(r"년\s*", "-", str(raw))
    s = re.sub(r"월\s*", "-", s)
    s = re.sub(r"일.*", "", s).strip()
    return pd.to_datetime(s, errors="coerce")


# ── 엑셀 파싱 ──────────────────────────────
def parse_incheon_excel(uploaded_file, agency=AGENCY, requester="", request_date=""):
    raw = pd.read_excel(uploaded_file, sheet_name=0, header=None)

    # 헤더 찾기
    header_row_idx = None
    for idx, row in raw.iterrows():
        values = [str(v).strip() for v in row.values]
        if "강의일" in values and "강의시간" in values:
            header_row_idx = idx
            break
    if header_row_idx is None:
        raise ValueError("엑셀에서 '강의일', '강의시간' 헤더를 찾지 못했습니다.")

    df = raw.iloc[header_row_idx + 1:].copy()
    df.columns = raw.iloc[header_row_idx].tolist()

    rows = []
    for _, row in df.iterrows():
        if pd.isna(row.get("강의일")):
            continue
        date_obj = _parse_date_str(row.get("강의일"))
        if pd.isna(date_obj):
            continue

        start, end = parse_time_range(str(row.get("강의시간", "")))
        instructor  = str(row.get("주강사", "")) if pd.notna(row.get("주강사")) else ""
        subject_raw = str(row.get("과목", ""))   if pd.notna(row.get("과목"))    else ""
        subject     = detect_subject(subject_raw) or subject_raw

        # 업종: 컬럼 있으면 사용, 없으면 텍스트에서 감지
        if pd.notna(row.get("업종")) and str(row.get("업종")).strip():
            industry = str(row.get("업종")).strip()
        else:
            industry = _detect_industry(subject_raw)

        # 강의실
        room_raw = str(row.get("지역", "")).strip() if pd.notna(row.get("지역")) else ""
        location = _ROOM_MAP.get(room_raw, _detect_room(room_raw)) if room_raw else "인천"

        r = make_row(date_obj, start, end, agency, subject,
                     TARGET, industry, location, instructor, DEFAULT_HOURLY_FEE)
        r["의뢰인"] = requester
        r["의뢰일"] = request_date
        rows.append(r)

    return pd.DataFrame(rows, columns=COLUMNS)


# ── 카톡/텍스트 파싱 ───────────────────────
def parse_incheon_kakao(text, year, requester="", request_date="", agency=AGENCY):
    rows = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    for line in lines:
        # 날짜 파싱 (4자리 연도 또는 월일)
        m = re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", line)
        if m:
            try:
                date_obj = pd.Timestamp(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except:
                continue
        else:
            m = re.search(r"(\d{1,2})월\s*(\d{1,2})일", line)
            if m:
                try:
                    date_obj = pd.Timestamp(year, int(m.group(1)), int(m.group(2)))
                except:
                    continue
            else:
                continue

        start, end = parse_time_range(line)
        if not start:
            continue

        industry = _detect_industry(line)
        location = _detect_room(line)

        # 과목 추출 (날짜, 시간, 업종, 강의실, 요일, 시간수 제거)
        subject_raw = line
        subject_raw = re.sub(r"\d{4}년\s*\d{1,2}월\s*\d{1,2}일", "", subject_raw)
        subject_raw = re.sub(r"\d{1,2}월\s*\d{1,2}일", "", subject_raw)
        subject_raw = re.sub(r"\([월화수목금토일]\)", "", subject_raw)
        subject_raw = re.sub(r"\d{1,2}:\d{2}\s*~\s*\d{1,2}:\d{2}", "", subject_raw)
        subject_raw = re.sub(r"(기타업|제조업|건설업)", "", subject_raw)
        subject_raw = re.sub(r"(제[12]강의실|[12]강의실)", "", subject_raw)
        subject_raw = re.sub(r"\d+시간", "", subject_raw).strip()
        subject = detect_subject(subject_raw) or "뇌심혈관"

        r = make_row(date_obj, start, end, agency, subject,
                     TARGET, industry, location, "", DEFAULT_HOURLY_FEE)
        r["의뢰인"] = requester
        r["의뢰일"] = request_date
        rows.append(r)

    return pd.DataFrame(rows, columns=COLUMNS)
