import re
import pandas as pd
from config import COLUMNS, DEFAULT_HOURLY_FEE, DEFAULT_LOCATION, DEFAULT_INDUSTRY
from utils import (
    extract_instructor, detect_agency, detect_target, detect_subject,
    parse_dates_from_text, parse_time_range, make_row
)


def parse_kakao_text(text, year):
    rows = []
    instructor = extract_instructor(text)
    agency = ""
    target = ""
    subject = ""
    location = DEFAULT_LOCATION
    industry = DEFAULT_INDUSTRY
    start_default = "14:00"
    end_default = "16:00"

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for line in lines:
        clean = line.replace("*", "").strip()
        if "교육" in clean and not re.search(r"\d{1,2}월", clean):
            a = detect_agency(clean)
            if a: agency = a
            t = detect_target(clean)
            if t: target = t
            s = detect_subject(clean)
            if s: subject = s
        if "동일" in clean and re.search(r"\d{1,2}시", clean):
            s, e = parse_time_range(re.sub(r"\([^)]*\)", "", clean))
            if s:
                start_default, end_default = s, e

    for line in lines:
        clean = line.replace("*", "").strip()
        if "담당자" in clean:
            continue
        dates = parse_dates_from_text(clean, year)
        if dates:
            start, end = parse_time_range(clean)
            if start is None:
                start, end = start_default, end_default
            final_subject = detect_subject(clean) or subject or "응급처치"
            for date_obj in dates:
                rows.append(make_row(
                    date_obj, start, end, agency, final_subject,
                    target, industry, location, instructor, DEFAULT_HOURLY_FEE
                ))

    return pd.DataFrame(rows, columns=COLUMNS)
