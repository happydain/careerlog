import re
import pandas as pd
from config import COLUMNS, DEFAULT_INDUSTRY, DEFAULT_LOCATION
from utils import detect_subject, parse_time_range, make_row


def _parse_jungdae_date(raw, year):
    dt = pd.to_datetime(raw, errors="coerce")
    if pd.notna(dt):
        return dt
    s = str(raw).strip()
    m = re.search(r"(\d{1,2})\s*[./]\s*(\d{1,2})", s)
    if m:
        return pd.to_datetime(f"{year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}", errors="coerce")
    m = re.search(r"(\d{1,2})월\s*(\d{1,2})일", s)
    if m:
        return pd.to_datetime(f"{year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}", errors="coerce")
    return pd.NaT


def _detect_target(industry_text):
    t = str(industry_text)
    if "책임자" in t: return "관리책임자"
    if "보건" in t: return "보건관리자"
    if "관리감독자" in t: return "관리감독자"
    return "안전관리자"


def parse_jungdae_excel(uploaded_file, requester, request_date, year):
    raw = pd.read_excel(uploaded_file, sheet_name=0, header=None)
    header_row_idx = None
    for idx, row in raw.iterrows():
        values = [str(v).strip() for v in row.values]
        if "날짜" in values and "시간" in values and "과정명" in values:
            header_row_idx = idx
            break
    if header_row_idx is None:
        raise ValueError("엑셀에서 '날짜, 시간, 과정명' 헤더를 찾지 못했습니다.")

    df = raw.iloc[header_row_idx + 1:].copy()
    df.columns = [str(c).strip() for c in raw.iloc[header_row_idx].tolist()]
    rows = []
    for _, row in df.iterrows():
        lecture_date = _parse_jungdae_date(row.get("날짜"), year)
        if pd.isna(lecture_date): continue
        start, end = parse_time_range(str(row.get("시간", "")))
        if not start or not end: continue
        subject_raw = str(row.get("과정명", "")).strip()
        subject = detect_subject(subject_raw) or subject_raw
        industry = str(row.get("업태", "")).strip() if pd.notna(row.get("업태")) else DEFAULT_INDUSTRY
        target = _detect_target(industry)
        location = str(row.get("방식", "")).strip() if pd.notna(row.get("방식")) else DEFAULT_LOCATION
        hourly_fee = 100000 if "동시송출" in location else 80000
        row_data = make_row(lecture_date, start, end, "중대협", subject,
                            target, industry, location, "", hourly_fee)
        row_data["의뢰인"] = requester
        row_data["의뢰일"] = request_date
        rows.append(row_data)
    return pd.DataFrame(rows, columns=COLUMNS)
