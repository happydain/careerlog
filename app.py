import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import re
import io

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

DEFAULT_HOURLY_FEE = 100000
DEFAULT_LOCATION = "줌"
DEFAULT_INDUSTRY = "기타업"


# -----------------------------
# Google Sheets
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

        st.write("1. 인증 성공")

        sheet = client.open(SHEET_NAME).sheet1

        st.write("2. 시트 연결 성공")

        values = df.values.tolist()

        sheet.append_rows(values)

        st.write("3. 저장 성공")

        return True

    except Exception as e:
        st.exception(e)
        return False


def load_gsheet():
    client = get_gsheet_client()
    sheet = client.open(SHEET_NAME).sheet1
    return pd.DataFrame(sheet.get_all_records())


# -----------------------------
# Common utils
# -----------------------------
def get_weekday(date_obj):
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    return weekdays[date_obj.weekday()]


def normalize_time(hour):
    hour = int(hour)
    return f"{hour:02d}:00"


def parse_time_range(text, default_start="14:00", default_end="16:00"):
    text = str(text)

    match = re.search(r"(\d{1,2})\s*시?\s*[-~]\s*(\d{1,2})\s*시?", text)
    if match:
        return normalize_time(match.group(1)), normalize_time(match.group(2))

    match = re.search(r"(\d{1,2}:\d{2})\s*[-~]\s*(\d{1,2}:\d{2})", text)
    if match:
        return match.group(1), match.group(2)

    return default_start, default_end


def calc_hours(start, end):
    s = int(str(start).split(":")[0])
    e = int(str(end).split(":")[0])
    return max(e - s, 0)


def calc_fee(hours, hourly_fee):
    return int(hours) * int(hourly_fee)


def extract_instructor(text):
    match = re.search(r"([가-힣]{2,4})\s*강사", text)
    return match.group(1) if match else ""


def extract_manager(text):
    match = re.search(r"담당자\s*[:：]\s*([가-힣]{2,4})", text)
    return match.group(1) if match else ""


def detect_agency(text):
    if "수원" in text:
        return "수원"
    if "인천" in text:
        return "인천"
    if "서울" in text or "중대협" in text:
        return "중대협"
    if "대한산안협" in text or "대한산업안전협회" in text:
        return "중대협"
    return "중대협"


def detect_target(text):
    if "안전관리자" in text:
        return "안전관리자"
    if "관리감독자" in text:
        return "관리감독자"
    if "보건관리자" in text:
        return "보건관리자"
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


def parse_dates_from_text(text, year):
    dates = []

    range_matches = re.findall(r"(\d{1,2})월\s*(\d{1,2})\s*[~\-]\s*(\d{1,2})일", text)
    for month, start_day, end_day in range_matches:
        for day in range(int(start_day), int(end_day) + 1):
            dates.append(datetime(year, int(month), day))

    normal_matches = re.findall(r"(\d{1,2})월\s*(\d{1,2})일", text)
    for month, day in normal_matches:
        date_obj = datetime(year, int(month), int(day))
        if date_obj not in dates:
            dates.append(date_obj)

    return dates


def make_row(date_obj, start, end, agency, subject, target, industry, location, instructor, hourly_fee):
    hours = calc_hours(start, end)
    return {
        "강의일시": f"{date_obj.year}. {date_obj.month}. {date_obj.day}",
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
        "강의료(1일)": calc_fee(hours, hourly_fee)
    }


# -----------------------------
# Kakao/Text parser
# -----------------------------
def parse_kakao_text(text, year):
    rows = []

    instructor = extract_instructor(text)
    agency = "중대협"
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
            agency = detect_agency(clean)
            detected_target = detect_target(clean)
            if detected_target:
                target = detected_target

            detected_subject = detect_subject(clean)
            if detected_subject:
                subject = detected_subject

            continue

        if "시간" in clean and "동일" in clean:
            start_default, end_default = parse_time_range(clean, start_default, end_default)
            continue

        if "담당자" in clean:
            continue

        dates = parse_dates_from_text(clean, year)

        if dates:
            start, end = parse_time_range(clean, start_default, end_default)

            detected_subject = detect_subject(clean)
            if detected_subject:
                subject = detected_subject

            if not subject:
                subject = "응급처치"

            for date_obj in dates:
                rows.append(
                    make_row(
                        date_obj=date_obj,
                        start=start,
                        end=end,
                        agency=agency,
                        subject=subject,
                        target=target,
                        industry=industry,
                        location=location,
                        instructor=instructor,
                        hourly_fee=DEFAULT_HOURLY_FEE
                    )
                )

    return pd.DataFrame(rows, columns=COLUMNS)


# -----------------------------
# 대한산안협 Excel parser
# -----------------------------
def parse_daehan_excel(uploaded_file, agency, target):
    raw = pd.read_excel(uploaded_file, sheet_name=0, header=None)

    header_row_idx = None
    for idx, row in raw.iterrows():
        values = [str(v).strip() for v in row.values]
        if "강의일" in values and "강의시간" in values:
            header_row_idx = idx
            break

    if header_row_idx is None:
        raise ValueError("엑셀에서 '강의일', '강의시간' 헤더를 찾지 못했습니다.")

    headers = raw.iloc[header_row_idx].tolist()
    df = raw.iloc[header_row_idx + 1:].copy()
    df.columns = headers

    rows = []

    for _, row in df.iterrows():
        if "강의일" not in df.columns or pd.isna(row.get("강의일")):
            continue

        lecture_date = pd.to_datetime(row.get("강의일"), errors="coerce")
        if pd.isna(lecture_date):
            continue

        time_text = row.get("강의시간", "")
        start, end = parse_time_range(time_text)

        instructor = row.get("주강사", "")
        subject_raw = str(row.get("과목", ""))
        subject = detect_subject(subject_raw) or subject_raw

        industry = row.get("업종", DEFAULT_INDUSTRY)
        room = row.get("지역", "")

        location = "오프" if pd.notna(room) and str(room).strip() else "오프"

        rows.append(
            make_row(
                date_obj=lecture_date,
                start=start,
                end=end,
                agency=agency,
                subject=subject,
                target=target,
                industry=industry,
                location=location,
                instructor=instructor,
                hourly_fee=DEFAULT_HOURLY_FEE
            )
        )

    return pd.DataFrame(rows, columns=COLUMNS)


# -----------------------------
# UI
# -----------------------------
st.title("📅 보건스케줄 자동정리")
st.info("카톡/이메일 텍스트와 대한산안협 엑셀 파일을 같은 포맷으로 정리해 구글시트에 저장합니다.")

tabs = st.tabs(["📥 카톡/이메일 입력", "📄 엑셀 업로드", "📊 최종 확인/저장", "🔎 구글시트 조회"])

with tabs[0]:
    st.markdown("### 카톡/이메일 강의 의뢰 텍스트")

    year = st.number_input("기준 연도", min_value=2024, max_value=2035, value=2026, step=1)

    raw_text = st.text_area("강의 요청 메시지를 붙여넣으세요.", height=320)

    if st.button("카톡/이메일 일정 분석"):
        if not raw_text.strip():
            st.warning("분석할 텍스트를 입력하세요.")
        else:
            df = parse_kakao_text(raw_text, year)

            if df.empty:
                st.warning("추출된 일정이 없습니다. 날짜 형식을 확인하세요.")
            else:
                st.session_state["temp_df"] = df
                st.success("텍스트 일정 분석 완료!")

with tabs[1]:
    st.markdown("### 대한산안협 엑셀 업로드")

    uploaded_file = st.file_uploader("대한산안협 엑셀 파일을 업로드하세요.", type=["xlsx"])

    col1, col2 = st.columns(2)
    with col1:
        excel_agency = st.selectbox("의뢰기관", ["수원", "인천", "중대협", "서울", "기타"], index=1)
    with col2:
        excel_target = st.selectbox("대상자", ["관리감독자", "안전관리자", "보건관리자", "근로자"], index=0)

    if uploaded_file and st.button("엑셀 일정 변환"):
        try:
            df_excel = parse_daehan_excel(uploaded_file, excel_agency, excel_target)

            if df_excel.empty:
                st.warning("엑셀에서 변환된 일정이 없습니다.")
            else:
                st.session_state["temp_df"] = df_excel
                st.success("엑셀 일정 변환 완료!")

        except Exception as e:
            st.error(f"엑셀 변환 오류: {e}")

with tabs[2]:
    st.markdown("### 최종 확인 및 수정")

    if "temp_df" not in st.session_state:
        st.info("먼저 카톡/이메일 또는 엑셀을 분석하세요.")
    else:
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

        st.session_state["temp_df"] = edited_df

        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("💾 구글 스프레드시트로 전송"):
                if append_to_gsheet(edited_df):
                    st.balloons()
                    st.success("구글 시트에 저장되었습니다.")
                    del st.session_state["temp_df"]

        with col2:
            buffer = io.BytesIO()
            edited_df.to_excel(buffer, index=False, engine="xlsxwriter")
            st.download_button(
                label="📥 엑셀 다운로드",
                data=buffer.getvalue(),
                file_name=f"보건스케줄_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        with col3:
            if st.button("🗑️ 현재 작업 초기화"):
                del st.session_state["temp_df"]
                st.rerun()

with tabs[3]:
    st.markdown("### 구글시트 데이터 조회")

    if st.button("🔄 시트 데이터 불러오기"):
        try:
            df_view = load_gsheet()
            st.session_state["view_df"] = df_view
            st.success("구글시트 데이터를 불러왔습니다.")
        except Exception as e:
            st.error(f"불러오기 오류: {e}")

    if "view_df" in st.session_state:
        st.dataframe(st.session_state["view_df"], use_container_width=True)
