import re
import pandas as pd
from config import COLUMNS, DEFAULT_HOURLY_FEE, DEFAULT_INDUSTRY
from utils import detect_subject, parse_time_range, make_row


def _parse_lecture_date(raw):
    s = re.sub(r"년\s*", "-", str(raw))
    s = re.sub(r"월\s*", "-", s)
    s = re.sub(r"일.*", "", s).strip()
    return pd.to_datetime(s, errors="coerce")


def parse_suwon_excel(uploaded_file, agency, target ="관리감독자"):
    raw = pd.read_excel(uploaded_file, sheet_name=0, header=None)
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
        if pd.isna(row.get("강의일")): continue
        lecture_date = _parse_lecture_date(row.get("강의일"))
        if pd.isna(lecture_date): continue
        start, end = parse_time_range(str(row.get("강의시간", "")))
        instructor = str(row.get("주강사", "")) if pd.notna(row.get("주강사")) else ""
        subject_raw = str(row.get("과목", "")) if pd.notna(row.get("과목")) else ""
        subject = detect_subject(subject_raw) or subject_raw
        industry = str(row.get("업종")) if pd.notna(row.get("업종")) else DEFAULT_INDUSTRY
        room = str(row.get("지역", "")).strip() if pd.notna(row.get("지역")) else ""
        location = f"오프 ({room})" if room else "오프"
        rows.append(make_row(lecture_date, start, end, agency, subject,
                             target, industry, location, instructor, DEFAULT_HOURLY_FEE))
    return pd.DataFrame(rows, columns=COLUMNS)
