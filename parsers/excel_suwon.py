import re
import pandas as pd
import openpyxl
from io import BytesIO
from config import COLUMNS, DEFAULT_HOURLY_FEE
from utils import detect_subject, parse_time_range, make_row

_LOCATION_MAP = {
    "2층": "수원2층",
    "5층": "수원5층",
    "광교": "수원광교",
}


def _detect_industry(text: str) -> str:
    if "제조업" in text: return "제조업"
    if "건설업" in text: return "건설업"
    return "기타업"


def _parse_date(raw):
    if hasattr(raw, 'strftime'):
        return raw
    s = re.sub(r"년\s*", "-", str(raw))
    s = re.sub(r"월\s*", "-", s)
    s = re.sub(r"일.*", "", s).strip()
    dt = pd.to_datetime(s, errors="coerce")
    return dt if not pd.isna(dt) else None


def parse_suwon_excel(uploaded_file, agency, target="관리감독자"):
    data = uploaded_file.read()
    wb = openpyxl.load_workbook(BytesIO(data))
    ws = wb.active

    all_rows = list(ws.iter_rows(values_only=True))

    # ── 헤더 있는 형식 감지 ──
    header_row_idx = None
    for idx, row in enumerate(all_rows):
        values = [str(v).strip() for v in row if v is not None]
        if "강의일" in values and "강의시간" in values:
            header_row_idx = idx
            break

    if header_row_idx is not None:
        # 기존 헤더 있는 형식
        headers = [str(v).strip() if v else "" for v in all_rows[header_row_idx]]
        rows = []
        for row in all_rows[header_row_idx + 1:]:
            if not any(row):
                continue
            r = dict(zip(headers, row))
            date_obj = _parse_date(r.get("강의일"))
            if not date_obj:
                continue
            start, end = parse_time_range(str(r.get("강의시간", "")))
            instructor = str(r.get("주강사", "")) if r.get("주강사") else ""
            subject_raw = str(r.get("과목", "")) if r.get("과목") else ""
            subject = detect_subject(subject_raw) or subject_raw
            industry = str(r.get("업종", "")) if r.get("업종") else "기타업"
            room = str(r.get("지역", "")).strip() if r.get("지역") else ""
            location = _LOCATION_MAP.get(room, f"수원{room}" if room else "수원")
            rows.append(make_row(date_obj, start, end, agency, subject,
                                 target, industry, location, instructor, DEFAULT_HOURLY_FEE))
        return pd.DataFrame(rows, columns=COLUMNS)

    else:
        # 헤더 없는 새 형식
        # 컬럼: 번호|구분|과정명|장소|날짜|인원|기간|강의일|요일|과목|시간|시수
        rows = []
        for row in all_rows:
            if not row or row[0] is None:
                continue
            date_obj = _parse_date(row[7]) if len(row) > 7 else None
            if not date_obj:
                continue
            time_str = str(row[10]) if len(row) > 10 and row[10] else ""
            start, end = parse_time_range(time_str)
            if not start:
                start, end = "14:00", "16:00"
            subject_raw = str(row[9]) if len(row) > 9 and row[9] else ""
            subject = detect_subject(subject_raw) or "뇌심혈관"
            course_name = str(row[2]) if len(row) > 2 and row[2] else ""
            industry = _detect_industry(course_name)
            location_raw = str(row[3]).strip() if len(row) > 3 and row[3] else ""
            location = _LOCATION_MAP.get(location_raw, f"수원{location_raw}" if location_raw else "수원")
            rows.append(make_row(date_obj, start, end, agency, subject,
                                 target, industry, location, "", DEFAULT_HOURLY_FEE))
        return pd.DataFrame(rows, columns=COLUMNS)
