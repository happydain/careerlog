"""
수원 대한협 - 강사별 일정 엑셀 파서
형식: 순번|구분|교육장|월|일수|강의날|요일|과목|시간1|강사
헤더: 2번째 행
"""
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
    "동탄": "수원동탄",
    "상공회의소": "수원상공회의소",
    "포은아트홀": "수원포은아트홀",
}


def _detect_industry(location: str) -> str:
    return "기타업"


def parse_suwon2_excel(uploaded_file, agency, target="관리감독자"):
    data = uploaded_file.read()
    wb = openpyxl.load_workbook(BytesIO(data))
    ws = wb.active

    all_rows = list(ws.iter_rows(values_only=True))

    # 헤더 행 찾기
    header_row_idx = None
    for idx, row in enumerate(all_rows):
        values = [str(v).strip() for v in row if v is not None]
        if "강의날" in values and "과목" in values and "강사" in values:
            header_row_idx = idx
            break

    if header_row_idx is None:
        raise ValueError("헤더를 찾지 못했습니다.")

    headers = [str(v).strip() if v else "" for v in all_rows[header_row_idx]]
    rows = []

    for row in all_rows[header_row_idx + 1:]:
        if not any(row):
            continue

        r = dict(zip(headers, row))

        # 강의날
        lecture_date = r.get("강의날")
        if lecture_date is None:
            continue
        if hasattr(lecture_date, 'strftime'):
            date_obj = lecture_date
        else:
            date_obj = pd.to_datetime(str(lecture_date), errors="coerce")
            if pd.isna(date_obj):
                continue

        # 시간
        time_str = str(r.get("시간1", "")).strip()
        start, end = parse_time_range(time_str)
        if not start:
            start, end = "14:00", "16:00"

        # 과목
        subject_raw = str(r.get("과목", "")).strip()
        subject = detect_subject(subject_raw) or subject_raw

        # 장소
        location_raw = str(r.get("교육장", "")).strip()
        location = _LOCATION_MAP.get(location_raw, location_raw if location_raw else "수원")

        # 강사
        instructor = str(r.get("강사", "")).strip() if r.get("강사") else ""

        # 업종 - 장소가 외부면 출강
        industry = "기타업"

        rows.append(make_row(
            date_obj, start, end, agency, subject,
            target, industry, location, instructor, DEFAULT_HOURLY_FEE
        ))

    return pd.DataFrame(rows, columns=COLUMNS)
