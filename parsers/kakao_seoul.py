import re
import pandas as pd
from datetime import datetime
from config import COLUMNS, DEFAULT_HOURLY_FEE, DEFAULT_INDUSTRY
from utils import detect_subject, parse_time_range, make_row

_SKIP = ["담당자", "교육장", "문의", "감사", "안녕", "확인부탁", "이상", "장소"]


def parse_seoul_kakao(text, year, requester, request_date):
    rows = []
    start_default = "14:00"
    end_default = "16:00"
    current_month = None

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for line in lines:
        clean = line.replace("*", "").replace("□", "").strip()
        if any(k in clean for k in _SKIP):
            continue

        # 월 헤더
        m = re.search(r"[-\s]*(\d{1,2})월", clean)
        if m:
            current_month = int(m.group(1))

        # 기본 시간 업데이트
        tm = re.search(r"(\d{1,2}:\d{2})\s*[-~]\s*(\d{1,2}:\d{2})", clean)
        if tm:
            start_default, end_default = tm.group(1), tm.group(2)

        # 3/6(금) 14:00~16:00 형식
        for mo, d in re.findall(r"(\d{1,2})/(\d{1,2})\s*\([월화수목금토일]\)", clean):
            try:
                date_obj = datetime(year, int(mo), int(d))
                start, end = parse_time_range(clean)
                if start is None:
                    start, end = start_default, end_default
                subject = detect_subject(clean) or "응급처치 대한1"
                instr_m = re.search(r"([가-힣]{2,3})\s*$", clean)
                instructor = instr_m.group(1) if instr_m else ""
                row = make_row(date_obj, start, end, "대한협서울", subject,
                               "관리감독자", DEFAULT_INDUSTRY, "출강", instructor, DEFAULT_HOURLY_FEE)
                row["의뢰인"] = requester
                row["의뢰일"] = request_date
                rows.append(row)
            except ValueError:
                pass

        # 20(화)-1 형식
        if current_month:
            for day, snum in re.findall(r"(\d{1,2})\([월화수목금토일]\)\s*[-]\s*(\d)", clean):
                try:
                    date_obj = datetime(year, current_month, int(day))
                    subject = "응급처치 대한1" if snum == "1" else "뇌심혈관"
                    start, end = parse_time_range(clean)
                    if start is None:
                        start, end = start_default, end_default
                    instr_m = re.search(r"([가-힣]{2,3})\s*(?:$|\+)", clean)
                    instructor = instr_m.group(1) if instr_m else ""
                    row = make_row(date_obj, start, end, "대한협서울", subject,
                                   "관리감독자", DEFAULT_INDUSTRY, "서울", instructor, DEFAULT_HOURLY_FEE)
                    row["의뢰인"] = requester
                    row["의뢰일"] = request_date
                    rows.append(row)
                except ValueError:
                    pass

    return pd.DataFrame(rows, columns=COLUMNS)
