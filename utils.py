import re
import pandas as pd
from datetime import datetime
from config import COLUMNS, DEFAULT_HOURLY_FEE, AGENCY_OPTIONS, LOCATION_OPTIONS

def parse_dates_from_text(text, year):
    dates = []
    
    # 기존: 6월 9일, 6월 9~12일
    for month, s, e in re.findall(r"(\d{1,2})월\s*(\d{1,2})\s*[~-]\s*(\d{1,2})일", text):
        for day in range(int(s), int(e) + 1):
            try:
                dates.append(datetime(year, int(month), day))
            except ValueError:
                pass
    for month, day in re.findall(r"(\d{1,2})월\s*(\d{1,2})일", text):
        try:
            d = datetime(year, int(month), int(day))
            if d not in dates:
                dates.append(d)
        except ValueError:
            pass

    # 추가: 2022.6.9 또는 6.9(목) 형식
    for y, m, d in re.findall(r"(\d{4})[./](\d{1,2})[./](\d{1,2})", text):
        try:
            dt = datetime(int(y), int(m), int(d))
            if dt not in dates:
                dates.append(dt)
        except ValueError:
            pass
    for m, d in re.findall(r"(\d{1,2})[./](\d{1,2})\s*\([월화수목금토일]\)", text):
        try:
            dt = datetime(year, int(m), int(d))
            if dt not in dates:
                dates.append(dt)
        except ValueError:
            pass

    return dates
    
def get_weekday(date_obj):
    return ["월", "화", "수", "목", "금", "토", "일"][date_obj.weekday()]


def normalize_time(hour):
    return f"{int(hour):02d}:00"


def parse_time_range(text):
    text = re.sub(r"\([^)]*\)", "", str(text)).strip()
    match = re.search(r"(\d{1,2}:\d{2})\s*[-~]\s*(\d{1,2}:\d{2})", text)
    if match:
        return match.group(1), match.group(2)
    match = re.search(r"(\d{1,2})\s*시\s*[-~]\s*(\d{1,2})\s*시?", text)
    if match:
        return normalize_time(match.group(1)), normalize_time(match.group(2))
    return None, None


def parse_time_range(text):
    text = re.sub(r"\([^)]*\)", "", str(text)).strip()
    
    # 기존: 15:00~18:00
    match = re.search(r"(\d{1,2}:\d{2})\s*[-~]\s*(\d{1,2}:\d{2})", text)
    if match:
        return match.group(1), match.group(2)
    
    # 기존: 15시~18시
    match = re.search(r"(\d{1,2})\s*시\s*[-~]\s*(\d{1,2})\s*시?", text)
    if match:
        return normalize_time(match.group(1)), normalize_time(match.group(2))

    # 추가: 15-18시
    match = re.search(r"(\d{1,2})\s*[-~]\s*(\d{1,2})\s*시", text)
    if match:
        return normalize_time(match.group(1)), normalize_time(match.group(2))

    return None, None

def calc_hours(start, end):
    try:
        return max(int(str(end).split(":")[0]) - int(str(start).split(":")[0]), 0)
    except (ValueError, IndexError):
        return 0


def calc_fee(hours, hourly_fee):
    try:
        return int(hours) * int(hourly_fee)
    except (ValueError, TypeError):
        return 0


def extract_instructor(text):
    match = re.search(r"([가-힣]{2,4})\s*강사", text)
    return match.group(1) if match else ""


def detect_agency(text):
    text = str(text)
    if "대한산안협" in text or "대한산업안전협회" in text:
        if "서울" in text: return "대한협서울"
        if "수원" in text: return "대한협수원"
        if "인천" in text: return "대한협인천"
        return "대한협"
    if "중대협" in text: return "중대협"
    if "한안협" in text: return "한안협"
    if "잡그레이드" in text: return "잡그레이드"
    return ""


def detect_target(text):
    if "안전관리자" in text: return "안전관리자"
    if "관리감독자" in text: return "관리감독자"
    if "보건관리자" in text: return "보건관리자"
    return ""


def detect_subject(text):
    text_upper = str(text).upper()
    if "동료를 살리는 응급처치" in text or "CPR" in text_upper or "AED" in text_upper or "-1" in text:
        return "응급처치 대한1"
    if "상황별 응급처치" in text or "사고별 응급처치" in text:
        return "응급처치 대한2"
    if "뇌심" in text or "뇌심혈관" in text or "-2" in text:
        return "뇌심혈관"
    if "직장" in text and "괴롭힘" in text:
        return "직장내괴롭힘"
    if "근골격계" in text:
        return "근골격계"
    if "건강진단" in text:
        return "건강진단"
    if "응급처치" in text:
        return "응급처치"
    return ""





def make_row(date_obj, start, end, agency, subject, target,
             industry, location, instructor, hourly_fee):
    hours = calc_hours(start, end)
    return {
        "강의일시": date_obj.strftime("%Y-%m-%d"),
        "요일": get_weekday(date_obj),
        "시작": start,
        "종료": end,
        "의뢰기관": agency,
        "과정명": subject,
        "대상자": target,
        "업종": industry,
        "방식/위치": location,
        "강사님": instructor,
        "시수": hours,
        "강의료(1시간)": hourly_fee,
        "강의료(1일)": calc_fee(hours, hourly_fee),
        "요청사항": "",
        "내부메모": "",
        "의뢰일": "",
        "의뢰인": "",
        "의뢰방법": "",
        "변경일자": "",
        "변경이력": "",
        "변경의뢰인": "",
        "증빙폴더": "",
    }


def get_column_config():
    import streamlit as st
    return {
        "강의일시": st.column_config.DateColumn("강의일시", format="YYYY-MM-DD"),
        "요일": st.column_config.TextColumn("요일"),
        "시작": st.column_config.TextColumn("시작"),
        "종료": st.column_config.TextColumn("종료"),
        "대상자": st.column_config.TextColumn("대상자"),
        "의뢰기관": st.column_config.SelectboxColumn("의뢰기관", options=AGENCY_OPTIONS),
        "강의료(1시간)": st.column_config.NumberColumn("강의료(1시간)", format="₩%d"),
        "강의료(1일)": st.column_config.NumberColumn("강의료(1일)", format="₩%d"),
        "시수": st.column_config.NumberColumn("시수", format="%d시간"),
        "방식/위치": st.column_config.SelectboxColumn("방식/위치", options=LOCATION_OPTIONS),
        "요청사항": st.column_config.TextColumn("의뢰업체메모", width="large"),
        "내부메모": st.column_config.TextColumn("내부메모", width="large"),
        "변경이력": st.column_config.TextColumn("변경이력", width="large"),
        "증빙폴더": st.column_config.LinkColumn("증빙폴더", display_text="📂 열기"),
    }
