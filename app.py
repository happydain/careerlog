import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import re
import io

# -----------------------------
# 1. 기본 설정
# -----------------------------
st.set_page_config(
    page_title="보건스케줄 자동정리",
    page_icon="📅",
    layout="wide"
)

SHEET_NAME = "보건스케쥴"

COLUMNS = [
    "강의일시", "요일", "시작", "종료", "의뢰기관", "과정명",
    "대상자", "업종", "방식/위치", "강사님", "시수",
    "강의료(1시간)", "강의료(1일)"
]

SUBJECT_MAP = {
    "뇌심": "뇌심혈관",
    "뇌심혈관": "뇌심혈관",
    "응급처치": "응급처치",
    "사고별 응급처치": "사고별 응급처치",
    "근골격계": "근골격계",
    "건강진단": "건강진단",
    "-1": "응급처치",
    "-2": "뇌심혈관",
}

DEFAULT_LOCATION = "줌"
DEFAULT_INDUSTRY = "기타업"
DEFAULT_HOURLY_FEE = 100000


# -----------------------------
# 2. 구글 시트 연결
# -----------------------------
def get_gsheet_client():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    credentials = dict(st.secrets["google_gsheets"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials, scope)
    return gspread.authorize(creds)


def append_to_gsheet(df):
    try:
        client = get_gsheet_client()
        sheet = client.open(SHEET_NAME).sheet1

        values = df[COLUMNS].values.tolist()
        sheet.append_rows(values, value_input_option="USER_ENTERED")
        return True

    except Exception as e:
        st.error(f"구글 시트 저장 오류: {e}")
        return False


def load_gsheet():
    client = get_gsheet_client()
    sheet = client.open(SHEET_NAME).sheet1
    data = sheet.get_all_records()
    return pd.DataFrame(data)


# -----------------------------
# 3. 유틸 함수
# -----------------------------
def get_weekday(date_obj):
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    return weekdays[date_obj.weekday()]


def normalize_time(hour):
    hour = int(hour)
    if hour < 8:
        hour += 12
    return f"{hour:02d}:00"


def calc_hours(start, end):
    s = int(start.split(":")[0])
    e = int(end.split(":")[0])
    return max(e - s, 0)


def calc_daily_fee(hours, hourly_fee):
    return hours * hourly_fee


def extract_instructor(text):
    match = re.search(r"([가-힣]{2,4})\s*강사", text)
    if match:
        return match.group(1)
    return ""


def extract_manager(text):
    match = re.search(r"담당자\s*[:：]\s*([가-힣]{2,4})", text)
    if match:
        return match.group(1)
    return ""


def detect_agency(line):
    agencies = ["서울", "수원", "인천", "중대협", "대한산안협", "대한산업안전협회"]
    for agency in agencies:
        if agency in line:
            if "서울" in line:
                return "중대협"
            if "수원" in line:
                return "수원"
            if "인천" in line:
                return "인천"
    return "중대협"


def detect_course(line):
    if "안전관리자" in line:
        return "안전관리자 보수교육"
    if "관리감독자" in line:
        return "관리감독자 교육"
    if "보건관리자" in line:
        return "보건관리자 교육"
    if "응급처치" in line:
        return "응급처치"
    return ""


def detect_target(line):
    if "안전관리자" in line:
        return "안전관리자"
    if "관리감독자" in line:
        return "관리감독자"
    if "보건관리자" in line:
        return "보건관리자"
    return ""


def detect_subject(text):
    for key, value in SUBJECT_MAP.items():
        if key in text:
            return value
    return "응급처치"


def parse_dates_from_line(line, year):
    dates = []

    # 예: 6월 30일, 9월 29일, 11월 24일
    pattern = r"(\d{1,2})월\s*(\d{1,2})일"
    matches = re.findall(pattern, line)

    for month, day in matches:
        date_obj = datetime(year, int(month), int(day))
        dates.append(date_obj)

    # 예: 2월 25~26일
    range_pattern = r"(\d{1,2})월\s*(\d{1,2})\s*[~\-]\s*(\d{1,2})일"
    range_matches = re.findall(range_pattern, line)

    for month, start_day, end_day in range_matches:
        for d in range(int(start_day), int(end_day) + 1):
            date_obj = datetime(year, int(month), d)
            dates.append(date_obj)

    return dates


def parse_time_from_line(line, default_start="14:00", default_end="16:00"):
    # 예: 13-15시, 8-10시, 15시-18시
    pattern = r"(\d{1,2})\s*시?\s*[-~]\s*(\d{1,2})\s*시"
    match = re.search(pattern, line)

    if match:
        start = normalize_time(match.group(1))
        end = normalize_time(match.group(2))
        return start, end

    return default_start, default_end


# -----------------------------
# 4. 핵심 파싱 함수
# -----------------------------
def parse_schedule_text(text, year):
    rows = []

    instructor = extract_instructor(text)
    manager = extract_manager(text)

    current_agency = "중대협"
    current_course = ""
    current_target = ""
    current_subject = "응급처치"
    current_start = "14:00"
    current_end = "16:00"

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for line in lines:
        clean_line = line.replace("*", "").replace("-", "").strip()

        # 교육 블록 제목 감지
        if "교육" in clean_line and not re.search(r"\d{1,2}월", clean_line):
            current_agency = detect_agency(clean_line)
            current_course = detect_course(clean_line)
            current_target = detect_target(clean_line)
            continue

        # 담당자 감지
        if "담당자" in clean_line:
            manager = extract_manager(clean_line)
            continue

        # 시간 동일 문장 감지
        if "시간" in clean_line and "동일" in clean_line:
            current_start, current_end = parse_time_from_line(clean_line, current_start, current_end)
            continue

        # 날짜 포함 라인 처리
        dates = parse_dates_from_line(clean_line, year)

        if dates:
            start, end = parse_time_from_line(clean_line, current_start, current_end)

            subject = detect_subject(clean_line)
            if subject:
                current_subject = subject

            for date_obj in dates:
                hours = calc_hours(start, end)
                daily_fee = calc_daily_fee(hours, DEFAULT_HOURLY_FEE)

                rows.append({
                    "강의일시": f"{date_obj.year}. {date_obj.month}. {date_obj.day}",
                    "요일": get_weekday(date_obj),
                    "시작": start,
                    "종료": end,
                    "의뢰기관": current_agency,
                    "과정명": current_subject,
                    "대상자": current_target,
                    "업종": DEFAULT_INDUSTRY,
                    "방식/위치": DEFAULT_LOCATION,
                    "강사님": instructor,
                    "시수": hours,
                    "강의료(1시간)": DEFAULT_HOURLY_FEE,
                    "강의료(1일)": daily_fee
                })

    return pd.DataFrame(rows, columns=COLUMNS)


# -----------------------------
# 5. 화면 UI
# -----------------------------
st.title("📅 보건스케줄 자동정리")
st.info("카톡/이메일로 받은 강의 의뢰 내용을 표준 스케줄 포맷으로 변환하고 구글시트에 저장합니다.")

tabs = st.tabs(["📥 일정 입력", "📊 구글시트 조회"])

with tabs[0]:
    st.markdown("### 1. 강의 요청 텍스트 입력")

    year = st.number_input(
        "기준 연도",
        min_value=2024,
        max_value=2035,
        value=2026,
        step=1
    )

    raw_text = st.text_area(
        "강의 요청 메시지를 붙여넣으세요.",
        height=320
    )

    if st.button("🪄 일정 자동 분석"):
        if not raw_text.strip():
            st.warning("분석할 텍스트를 입력하세요.")
        else:
            try:
                df = parse_schedule_text(raw_text, year)
                if df.empty:
                    st.warning("추출된 일정이 없습니다. 날짜 형식을 확인하세요.")
                else:
                    st.session_state["temp_df"] = df
                    st.success("분석 완료! 아래 표에서 최종 수정 후 저장하세요.")
            except Exception as e:
                st.error(f"분석 중 오류 발생: {e}")

    st.divider()

    st.markdown("### 2. 기존 엑셀 업로드")
    uploaded_file = st.file_uploader("정리된 엑셀(.xlsx)을 업로드하세요.", type=["xlsx"])

    if uploaded_file:
        df_upload = pd.read_excel(uploaded_file)

        for col in COLUMNS:
            if col not in df_upload.columns:
                df_upload[col] = ""

        st.session_state["temp_df"] = df_upload[COLUMNS]
        st.success("엑셀 파일 로드 완료!")

    if "temp_df" in st.session_state:
        st.markdown("### 📋 최종 확인 및 수정")

        edited_df = st.data_editor(
            st.session_state["temp_df"],
            use_container_width=True,
            num_rows="dynamic",
            column_config={
                "강의료(1시간)": st.column_config.NumberColumn(format="₩%d"),
                "강의료(1일)": st.column_config.NumberColumn(format="₩%d"),
                "시수": st.column_config.NumberColumn(format="%d"),
            }
        )

        col1, col2 = st.columns(2)

        with col1:
            if st.button("💾 구글 스프레드시트로 전송"):
                if append_to_gsheet(edited_df):
                    st.balloons()
                    st.success("구글 시트에 성공적으로 저장되었습니다.")
                    del st.session_state["temp_df"]

        with col2:
            towrite = io.BytesIO()
            edited_df.to_excel(towrite, index=False, engine="xlsxwriter")
            st.download_button(
                label="📥 엑셀로 다운로드",
                data=towrite.getvalue(),
                file_name=f"보건스케줄_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

with tabs[1]:
    st.markdown("### 📅 현재 구글 시트 데이터")

    if st.button("🔄 시트 데이터 불러오기"):
        try:
            df_view = load_gsheet()
            st.session_state["view_df"] = df_view
            st.success("구글 시트 데이터를 불러왔습니다.")
        except Exception as e:
            st.error(f"불러오기 오류: {e}")

    if "view_df" in st.session_state:
        st.dataframe(st.session_state["view_df"], use_container_width=True)
