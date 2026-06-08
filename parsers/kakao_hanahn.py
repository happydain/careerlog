import re
import pandas as pd
from datetime import datetime
from config import COLUMNS, DEFAULT_INDUSTRY
from utils import detect_target, detect_subject, parse_time_range, make_row


def _get_hanahn_fee(instructor):
    return 120000 if instructor == "이다인" else 110000


def _convert_ampm(text):
    def replace(m):
        ampm, hour = m.group(1), int(m.group(2))
        if ampm == "오후" and hour != 12:
            hour += 12
        elif ampm == "오전" and hour == 12:
            hour = 0
        return f"{hour}시"
    return re.sub(r"(오전|오후)\s*(\d{1,2})시", replace, text)


def _parse_date(clean, year):
    """다양한 날짜 형식 파싱"""
    # 2022.6.9 또는 2022/6/9
    m = re.search(r"(\d{4})[./](\d{1,2})[./](\d{1,2})", clean)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # 6.9(목) 또는 6/9(목)
    m = re.search(r"(\d{1,2})[./](\d{1,2})\s*\([월화수목금토일]\)", clean)
    if m:
        try:
            return datetime(year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            pass

    # 6월 9일
    m = re.search(r"(\d{1,2})월\s*(\d{1,2})일", clean)
    if m:
        try:
            return datetime(year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            pass

    return None


def parse_hanahn_kakao(text, year, requester, request_date):
    rows = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    current_date = None
    current_target = ""
    current_industry = DEFAULT_INDUSTRY
    current_location = "서울"

    for line in lines:
        clean = line.replace("*", "").strip()

        # 날짜 줄 감지
        parsed_date = _parse_date(clean, year)
        if parsed_date:
            current_date = parsed_date
            current_target = detect_target(clean) or "안전관리자"
            if "건설" in clean: current_industry = "건설업"
            elif "제조" in clean: current_industry = "제조업"
            else: current_industry = DEFAULT_INDUSTRY
            current_location = "줌" if "비대면" in clean else "서울"

            # 한 줄에 날짜+시간+과목 모두 있는 경우 (2022.6.9(목) 15-18시 응급처치 ...)
            if re.search(r"\d{1,2}[-~]\d{1,2}시|\d{1,2}시[-~]\d{1,2}시|\d{1,2}:\d{2}", clean):
                converted = _convert_ampm(clean)
                start, end = parse_time_range(converted)
                if start:
                    subject_part = re.sub(r"\d{4}[./]\d{1,2}[./]\d{1,2}", "", converted)
                    subject_part = re.sub(r"\d{1,2}[./]\d{1,2}\s*\([월화수목금토일]\)", "", subject_part)
                    subject_part = re.sub(r"\d{1,2}시.*?[-~].*?\d{1,2}시", "", subject_part)
                    subject_part = re.sub(r"\d{1,2}[-~]\d{1,2}시", "", subject_part)
                    subject_part = re.sub(r"오전|오후|산업현장", "", subject_part).strip()
                    subject_part = re.sub(r"^[-\s]+", "", subject_part).strip()
                    final = detect_subject(subject_part) or subject_part or "응급처치"
                    row = make_row(current_date, start, end, "한안협", final,
                                   current_target, current_industry, current_location,
                                   "", _get_hanahn_fee(""))
                    row["의뢰인"] = requester
                    row["의뢰일"] = request_date
                    rows.append(row)
            continue

        # 시간+과목 줄 (날짜가 앞 줄에 있는 경우)
        if current_date and re.search(r"\d{1,2}시", clean):
            converted = _convert_ampm(clean)
            start, end = parse_time_range(converted)
            if not start:
                continue

            subject_part = re.sub(r"\d{1,2}시.*?[-~].*?\d{1,2}시", "", converted).strip()
            subject_part = re.sub(r"오전|오후|산업현장", "", subject_part).strip()
            subject_part = re.sub(r"^[-\s]+", "", subject_part).strip()
            subjects = [s.strip().lstrip("-").strip() for s in re.split(r"및|,", subject_part) if s.strip()]

            if len(subjects) >= 2:
                start_h = int(start.split(":")[0])
                end_h = int(end.split(":")[0])
                half = (end_h - start_h) // len(subjects)
                for i, subj in enumerate(subjects):
                    s = f"{start_h + i * half:02d}:00"
                    e = f"{start_h + (i + 1) * half:02d}:00"
                    final = detect_subject(subj) or subj
                    row = make_row(current_date, s, e, "한안협", final,
                                   current_target, current_industry, current_location,
                                   "", _get_hanahn_fee(""))
                    row["의뢰인"] = requester
                    row["의뢰일"] = request_date
                    rows.append(row)
            else:
                final = detect_subject(subject_part) or subject_part
                row = make_row(current_date, start, end, "한안협", final,
                               current_target, current_industry, current_location,
                               "", _get_hanahn_fee(""))
                row["의뢰인"] = requester
                row["의뢰일"] = request_date
                rows.append(row)

    return pd.DataFrame(rows, columns=COLUMNS)
