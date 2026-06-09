import re
import pandas as pd
from config import COLUMNS, DEFAULT_HOURLY_FEE
from utils import detect_subject, parse_time_range, make_row, get_weekday

# 장소 매핑
_LOCATION_MAP = {
    "2층": "수원2층",
    "5층": "수원5층",
    "광교": "수원광교",
}


def _detect_industry(course_name: str) -> str:
    """과정명에서 업종 추출"""
    if "제조업" in course_name:
        return "제조업"
    if "건설업" in course_name:
        return "건설업"
    return "기타업"


def parse_suwon_excel(uploaded_file, agency, target="관리감독자"):
    """
    헤더 없는 수원 대한협 엑셀 파서
    컬럼 순서: 번호|구분|과정명|장소|날짜(미사용)|인원|기간|강의일|요일|과목|시간|시수
    """
    import openpyxl
    from io import BytesIO

    data = uploaded_file.read()
    wb = openpyxl.load_workbook(BytesIO(data))
    ws = wb.active

    rows = []

    for row in ws.iter_rows(values_only=True):
        # 빈 행 스킵
        if not row or row[0] is None:
            continue

        # 강의일 (col index 7)
        lecture_date = row[7] if len(row) > 7 else None
        if lecture_date is None:
            continue

        # datetime 타입 처리
        if hasattr(lecture_date, 'strftime'):
            date_obj = lecture_date
        else:
            date_obj = pd.to_datetime(str(lecture_date), errors="coerce")
            if pd.isna(date_obj):
                continue

        # 시간 (col index 10)
        time_str = str(row[10]) if len(row) > 10 and row[10] else ""
        start, end = parse_time_range(time_str)
        if not start:
            start, end = "14:00", "16:00"

        # 과목 (col index 9)
        subject_raw = str(row[9]) if len(row) > 9 and row[9] else ""
        subject = detect_subject(subject_raw) or "뇌심혈관"

        # 과정명에서 업종 추출 (col index 2)
        course_name = str(row[2]) if len(row) > 2 and row[2] else ""
        industry = _detect_industry(course_name)

        # 장소 (col index 3)
        location_raw = str(row[3]).strip() if len(row) > 3 and row[3] else ""
        location = _LOCATION_MAP.get(location_raw, f"수원{location_raw}" if location_raw else "수원")

        rows.append(make_row(
            date_obj, start, end, agency, subject,
            target, industry, location, "", DEFAULT_HOURLY_FEE
        ))

    return pd.DataFrame(rows, columns=COLUMNS)
