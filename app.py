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

SPREADSHEET_ID = "1AUnbvyn1Nx9JDUv-0MhhbYf3oziJ3CR_0ZgINq-G59M"

COLUMNS = [
    "강의일시", "요일", "시작", "종료", "의뢰기관", "과정명", "대상자", "업종",
    "방식/위치", "강사님", "시수", "강의료(1시간)", "강의료(1일)",
    "의뢰자", "의뢰일", "특이사항", "변경이력", "내부메모"
]

DEFAULT_HOURLY_FEE = 100000
DEFAULT_LOCATION = "줌"
DEFAULT_INDUSTRY = "기타업"


# -----------------------------
# Google Sheets
# -----------------------------
def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials = dict(st.secrets["google_gsheets"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials, scope)
    return gspread.authorize(creds)


def get_or_create_sheet(client, title):
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    try:
        return spreadsheet.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=1000, cols=30)


def ensure_header(sheet):
    existing = sheet.get_all_values()
    if not existing or existing[0] != COLUMNS:
        sheet.insert_row(COLUMNS, index=1)


def append_to_gsheet(df):
    try:
        client = get_gsheet_client()

        # Sheet1 - 의뢰일별
        sheet1 = get_or_create_sheet(client, "의뢰일별")
        ensure_header(sheet1)

        # Sheet2 - 최종
        sheet2 = get_or_create_sheet(client, "최종")
        ensure_header(sheet2)

        df_clean = df.fillna("").astype(str)
        values = df_clean.values.tolist()

        sheet1.append_rows(values)
        sheet2.append_rows(values)

        return True
    except Exception as e:
        st.exception(e)
        return False


def load_gsheet_raw():
    try:
        client = get_gsheet_client()
        sheet = get_or_create_sheet(client, "의뢰일별")
        data = sheet.get_all_records()
        if not data:
            return pd.DataFrame(columns=COLUMNS)
        df = pd.DataFrame(data)
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = ""
        return df
    except Exception as e:
        st.error(f"구글시트 불러오기 오류: {e}")
        return pd.DataFrame(columns=COLUMNS)


def load_gsheet_final():
    try:
        client = get_gsheet_client()
        sheet = get_or_create_sheet(client, "최종")
        data = sheet.get_all_records()
        if not data:
            return pd.DataFrame(columns=COLUMNS)
        df = pd.DataFrame(data)
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = ""
        # 날짜 오름차순 정렬
        df["강의일시_dt"] = pd.to_datetime(df["강의일시"], errors="coerce")
        df = df.sort_values("강의일시_dt").drop(columns=["강의일시_dt"])
        df = df.reset_index(drop=True)
        return df
    except Exception as e:
        st.error(f"구글시트 불러오기 오류: {e}")
        return pd.DataFrame(columns=COLUMNS)


def save_gsheet_final(df):
    try:
        client = get_gsheet_client()
        sheet = get_or_create_sheet(client, "최종")
        sheet.clear()
        sheet.append_row(COLUMNS)
        df_clean = df.fillna("").astype(str)
        sheet.append_rows(df_clean.values.tolist())
        return True
    except Exception as e:
        st.exception(e)
        return False


# -----------------------------
# Common utils
# -----------------------------
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
    if "상황별 응급처치" in text or "사고별 응급처치" in text: return "응급처치 대한2"
    if "뇌심" in text or "뇌심혈관" in text or "-2" in text: return "뇌심혈관"
    if "직장" in text and "괴롭힘" in text: return "직장내괴롭힘"
    if "근골격계" in text: return "근골격계"
    if "건강진단" in text: return "건강진단"
    if "응급처치" in text: return "응급처치"
    return ""


def parse_dates_from_text(text, year):
    dates = []
    for month, s, e in re.findall(r"(\d{1,2})월\s*(\d{1,2})\s*[~\-]\s*(\d{1,2})일", text):
        for day in range(int(s), int(e) + 1):
            try: dates.append(datetime(year, int(month), day))
            except ValueError: pass
    for month, day in re.findall(r"(\d{1,2})월\s*(\d{1,2})일", text):
        try:
            d = datetime(year, int(month), int(day))
            if d not in dates: dates.append(d)
        except ValueError: pass
    return dates


def make_row(date_obj, start, end, agency, subject, target, industry, location, instructor, hourly_fee):
    hours = calc_hours(start, end)
    return {
        "강의일시": date_obj.strftime("%Y-%m-%d"),
        "요일": get_weekday(date_obj),
        "시작": start, "종료": end,
        "의뢰기관": agency, "과정명": subject, "대상자": target,
        "업종": industry, "방식/위치": location, "강사님": instructor,
        "시수": hours, "강의료(1시간)": hourly_fee,
        "강의료(1일)": calc_fee(hours, hourly_fee),
        "의뢰자": "", "의뢰일": "", "특이사항": "", "변경이력": "", "내부메모": ""
    }


# -----------------------------
# Kakao/Text parser (일반)
# -----------------------------
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
            if s: start_default, end_default = s, e

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
                rows.append(make_row(date_obj, start, end, agency, final_subject, target, industry, location, instructor, DEFAULT_HOURLY_FEE))

    return pd.DataFrame(rows, columns=COLUMNS)


# -----------------------------
# 대한협서울 카톡 parser
# -----------------------------
def parse_seoul_kakao(text, year, requester, request_date):
    rows = []
    start_default = "14:00"
    end_default = "16:00"
    current_month = None

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for line in lines:
        clean = line.replace("*", "").replace("□", "").strip()

        if any(k in clean for k in ["담당자", "교육장", "문의", "감사", "안녕", "확인부탁", "이상", "장소"]):
            continue

        # 월 헤더: "- 1월", "1월"
        month_match = re.match(r"[-\s]*(\d{1,2})월\s*$", clean)
        if month_match:
            current_month = int(month_match.group(1))
            continue

        # 시간 감지
        time_match = re.search(r"(\d{1,2}:\d{2})\s*[-~]\s*(\d{1,2}:\d{2})", clean)
        if time_match:
            start_default = time_match.group(1)
            end_default = time_match.group(2)

        # 월/일 형태: 3/6(금) 14:00~16:00
        for m, d in re.findall(r"(\d{1,2})/(\d{1,2})\s*\([월화수목금토일]\)", clean):
            try:
                date_obj = datetime(year, int(m), int(d))
                start, end = parse_time_range(clean)
                if start is None:
                    start, end = start_default, end_default
                subject = detect_subject(clean) or "응급처치 대한1"
                instructor_match = re.search(r"([가-힣]{2,3})\s*$", clean)
                instructor = instructor_match.group(1) if instructor_match else ""
                row = make_row(date_obj, start, end, "대한협서울", subject, "관리감독자", DEFAULT_INDUSTRY, "출강", instructor, DEFAULT_HOURLY_FEE)
                row["의뢰자"] = requester
                row["의뢰일"] = request_date
                rows.append(row)
            except ValueError:
                pass

        # 일(요일)-과목번호 형태: 20(화)-1, 2(월)-1 김미림
        if current_month:
            for day, subject_num in re.findall(r"(\d{1,2})\([월화수목금토일]\)\s*[-]\s*(\d)", clean):
                try:
                    date_obj = datetime(year, current_month, int(day))
                    subject = "응급처치 대한1" if subject_num == "1" else "뇌심혈관"
                    start, end = parse_time_range(clean)
                    if start is None:
                        start, end = start_default, end_default
                    instructor_match = re.search(r"([가-힣]{2,3})\s*(?:$|\+)", clean)
                    instructor = instructor_match.group(1) if instructor_match else ""
                    row = make_row(date_obj, start, end, "대한협서울", subject, "관리감독자", DEFAULT_INDUSTRY, "출강", instructor, DEFAULT_HOURLY_FEE)
                    row["의뢰자"] = requester
                    row["의뢰일"] = request_date
                    rows.append(row)
                except ValueError:
                    pass

    return pd.DataFrame(rows, columns=COLUMNS)


# -----------------------------
# 대한산안협 일반 Excel parser
# -----------------------------
def parse_lecture_date(raw):
    s = re.sub(r"년\s*", "-", str(raw))
    s = re.sub(r"월\s*", "-", s)
    s = re.sub(r"일.*", "", s).strip()
    return pd.to_datetime(s, errors="coerce")


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
    df = raw.iloc[header_row_idx + 1:].copy()
    df.columns = raw.iloc[header_row_idx].tolist()
    rows = []
    for _, row in df.iterrows():
        if pd.isna(row.get("강의일")): continue
        lecture_date = parse_lecture_date(row.get("강의일"))
        if pd.isna(lecture_date): continue
        start, end = parse_time_range(str(row.get("강의시간", "")))
        instructor = str(row.get("주강사", "")) if pd.notna(row.get("주강사")) else ""
        subject_raw = str(row.get("과목", "")) if pd.notna(row.get("과목")) else ""
        subject = detect_subject(subject_raw) or subject_raw
        industry = str(row.get("업종")) if pd.notna(row.get("업종")) else DEFAULT_INDUSTRY
        room = str(row.get("지역", "")).strip() if pd.notna(row.get("지역")) else ""
        location = f"오프 ({room})" if room else "오프"
        rows.append(make_row(lecture_date, start, end, agency, subject, target, industry, location, instructor, DEFAULT_HOURLY_FEE))
    return pd.DataFrame(rows, columns=COLUMNS)


# -----------------------------
# 대한산안협 인천 Excel parser
# -----------------------------
def parse_incheon_excel(uploaded_file, agency, requester, request_date):
    raw = pd.read_excel(uploaded_file, sheet_name=0, header=None)
    header_row_idx = None
    for idx, row in raw.iterrows():
        values = [str(v).strip() for v in row.values]
        if "강의일" in values and "강의시간" in values:
            header_row_idx = idx
            break
    if header_row_idx is None:
        raise ValueError("엑셀에서 헤더를 찾지 못했습니다.")
    df = raw.iloc[header_row_idx + 1:].copy()
    df.columns = raw.iloc[header_row_idx].tolist()
    room_map = {"제1강의실": "인천 1강의실", "제2강의실": "인천 2강의실"}
    rows = []
    for _, row in df.iterrows():
        if pd.isna(row.get("강의일")): continue
        lecture_date = parse_lecture_date(row.get("강의일"))
        if pd.isna(lecture_date): continue
        start, end = parse_time_range(str(row.get("강의시간", "")))
        instructor = str(row.get("주강사", "")) if pd.notna(row.get("주강사")) else ""
        subject_raw = str(row.get("과목", "")) if pd.notna(row.get("과목")) else ""
        subject = detect_subject(subject_raw) or subject_raw
        industry = str(row.get("업종")) if pd.notna(row.get("업종")) else DEFAULT_INDUSTRY
        room = str(row.get("지역", "")).strip() if pd.notna(row.get("지역")) else ""
        location = room_map.get(room, room) if room else "오프"
        row_data = make_row(lecture_date, start, end, agency, subject, "관리감독자", industry, location, instructor, DEFAULT_HOURLY_FEE)
        row_data["의뢰자"] = requester
        row_data["의뢰일"] = request_date
        rows.append(row_data)
    return pd.DataFrame(rows, columns=COLUMNS)


# -----------------------------
# column_config 공통
# -----------------------------
def get_column_config():
    return {
        "강의일시": st.column_config.DateColumn("강의일시", format="YYYY-MM-DD"),
        "요일": st.column_config.TextColumn("요일"),
        "시작": st.column_config.TextColumn("시작"),
        "종료": st.column_config.TextColumn("종료"),
        "대상자": st.column_config.TextColumn("대상자"),
        "의뢰기관": st.column_config.SelectboxColumn("의뢰기관", options=["대한협수원", "대한협인천", "대한협서울", "중대협", "한안협", "잡그레이드"]),
        "강의료(1시간)": st.column_config.NumberColumn("강의료(1시간)", format="₩%d"),
        "강의료(1일)": st.column_config.NumberColumn("강의료(1일)", format="₩%d"),
        "시수": st.column_config.NumberColumn("시수", format="%d"),
        "방식/위치": st.column_config.SelectboxColumn("방식/위치", options=["동시송출", "줌", "인천 1강의실", "인천 2강의실", "수원 1층", "수원 5층", "서울 교육장", "출강", "기타"]),
        "특이사항": st.column_config.TextColumn("특이사항", width="large"),
        "변경이력": st.column_config.TextColumn("변경이력", width="large"),
        "내부메모": st.column_config.TextColumn("내부메모", width="large")
    }


# -----------------------------
# UI
# -----------------------------
st.sidebar.title("📅 CareerLog")
menu = st.sidebar.radio("메뉴 선택", [
    "📥 보건스케줄 입력",
    "📋 의뢰일별 스케쥴",
    "📅 최종 스케줄(취소,변경반영)",
    "📊 협회별 월별 스케줄",
    "👨‍🏫 강사별 대시보드"
])

st.title("📅 보건스케줄 자동정리")
st.info("카톡 텍스트와 협회별 엑셀 파일을 같은 포맷으로 정리해 구글시트에 저장합니다.")


# =====================
# 📥 보건스케줄 입력
# =====================
if menu == "📥 보건스케줄 입력":

    st.header("📥 보건스케줄 입력")
    st.info("""
    📝 입력 안내

    • 카카오톡, 문자, 이메일 등으로 받은 강의 의뢰 내용을 그대로 붙여넣어 주세요.  
    • 스케줄은 의뢰받은 날짜 기준으로 관리됩니다.  
    • 일정 변경 및 취소 건도 반드시 입력해 주세요.  
    • 변경·취소 이력은 원본 일정과 함께 저장되어 추후 확인이 가능합니다.  
    • 입력된 내용은 표준 형식으로 정리되어 구글시트에 저장됩니다.  
    """)  
    st.markdown("### ⚙️ 기본 정보 설정")
    # 의뢰기관을 크게 강조
    common_agency = st.selectbox(
        "🏢 의뢰기관 (필수 확인!)",
        ["대한협수원", "대한협인천", "대한협서울", "중대협", "한안협", "잡그레이드"],
        help="카톡/엑셀 모두 이 기관으로 처리됩니다. 반드시 먼저 확인하세요!"
    )
    
    st.info(f"📌 현재 선택된 의뢰기관: **{common_agency}**")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        common_requester = st.text_input("담당자 이름")
    with col2:
        common_date = st.date_input("의뢰일", value=datetime.now())
    with col3:
        year = st.number_input("기준 연도", min_value=2024, max_value=2035, value=datetime.now().year, step=1)
    
    st.divider()

    # --- 카톡 입력 ---
    st.markdown("### 카톡/이메일 강의 의뢰 텍스트")
    raw_text = st.text_area("강의 요청 메시지를 붙여넣으세요.", height=250)

    if st.button("🪄 카톡 일정 분석"):
        if raw_text.strip():
            if common_agency == "대한협서울":
                df_text = parse_seoul_kakao(raw_text, year, common_requester, common_date.strftime("%Y-%m-%d"))
            else:
                df_text = parse_kakao_text(raw_text, year)
                df_text["의뢰기관"] = common_agency
                df_text["의뢰자"] = common_requester
                df_text["의뢰일"] = common_date.strftime("%Y-%m-%d")
            if df_text.empty:
                st.warning("날짜 정보를 찾지 못했습니다.")
            else:
                st.session_state["temp_df"] = df_text
                st.success(f"{len(df_text)}건 일정 생성 완료")
        else:
            st.warning("텍스트를 입력해주세요.")

    st.divider()

    # --- 엑셀 업로드 ---
    st.markdown("### 강의의뢰 엑셀 업로드")
    uploaded_file = st.file_uploader("강의의뢰 엑셀 업로드", type=["xlsx"])

    if uploaded_file:
        if st.button("📄 엑셀 일정 변환"):
            try:
                if common_agency == "대한협인천":
                    df_excel = parse_incheon_excel(uploaded_file, common_agency, common_requester, common_date.strftime("%Y-%m-%d"))
                else:
                    df_excel = parse_daehan_excel(uploaded_file, common_agency, "")
                    df_excel["의뢰자"] = common_requester
                    df_excel["의뢰일"] = common_date.strftime("%Y-%m-%d")
                if df_excel.empty:
                    st.warning("변환된 일정이 없습니다.")
                else:
                    st.session_state["temp_df"] = df_excel
                    st.success(f"{len(df_excel)}건 일정 생성 완료")
            except Exception as e:
                st.error(f"엑셀 변환 오류: {e}")

    st.divider()

    # --- 수동 입력 ---
    st.markdown("### ✍️ 수동으로 직접 입력하기")
    if st.button("➕ 빈 테이블 생성 (직접 입력용)"):
        st.session_state["temp_df"] = pd.DataFrame(columns=COLUMNS)
        st.rerun()

    st.divider()
    st.header("📋 최종 확인 및 저장")

    if "temp_df" in st.session_state:
        try:
            st.session_state["temp_df"]["강의일시"] = pd.to_datetime(
                st.session_state["temp_df"]["강의일시"], errors="coerce"
            ).dt.date
        except Exception:
            pass

        edited_df = st.data_editor(
            st.session_state["temp_df"],
            use_container_width=True,
            num_rows="dynamic",
            column_config=get_column_config()
        )

        st.divider()
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if st.button("🔄 요일/시수 자동계산"):
                try:
                    def auto_weekday(r):
                        try:
                            return ["월", "화", "수", "목", "금", "토", "일"][pd.to_datetime(r["강의일시"]).weekday()]
                        except:
                            return r["요일"]
                    edited_df["요일"] = edited_df.apply(auto_weekday, axis=1)
                    edited_df["시수"] = edited_df.apply(lambda r: calc_hours(r["시작"], r["종료"]) if pd.notna(r["시작"]) and pd.notna(r["종료"]) else 0, axis=1)
                    edited_df["강의료(1일)"] = edited_df.apply(lambda r: calc_fee(r["시수"], r["강의료(1시간)"]) if pd.notna(r["시수"]) and pd.notna(r["강의료(1시간)"]) else 0, axis=1)
                    st.session_state["temp_df"] = edited_df
                    st.rerun()
                except Exception as e:
                    st.error(f"계산 오류: {e}")

        with col2:
            if st.button("💾 구글시트 저장"):
                if append_to_gsheet(edited_df):
                    st.success("의뢰일별 + 최종 시트에 저장 완료!")
                    del st.session_state["temp_df"]
                    st.rerun()

        with col3:
            buffer = io.BytesIO()
            edited_df.to_excel(buffer, index=False, engine="xlsxwriter")
            st.download_button(
                label="📥 엑셀 다운로드",
                data=buffer.getvalue(),
                file_name=f"보건스케줄_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        with col4:
            if st.button("🧹 초기화"):
                del st.session_state["temp_df"]
                st.rerun()


# =====================
# 📋 의뢰일별 (Sheet1 - 읽기 전용)
# =====================
elif menu == "📋 의뢰일별":
    st.header("📋 의뢰일별 (원본)")
    df = load_gsheet_raw()

    if df.empty:
        st.info("저장된 데이터가 없습니다.")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            agency_filter = st.selectbox("의뢰기관", ["전체"] + sorted(df["의뢰기관"].dropna().unique().tolist()))
        with col2:
            instructor_filter = st.selectbox("강사님", ["전체"] + sorted(df["강사님"].dropna().unique().tolist()))
        with col3:
            subject_filter = st.selectbox("과정명", ["전체"] + sorted(df["과정명"].dropna().unique().tolist()))

        filtered_df = df.copy()
        if agency_filter != "전체": filtered_df = filtered_df[filtered_df["의뢰기관"] == agency_filter]
        if instructor_filter != "전체": filtered_df = filtered_df[filtered_df["강사님"] == instructor_filter]
        if subject_filter != "전체": filtered_df = filtered_df[filtered_df["과정명"] == subject_filter]

        st.dataframe(filtered_df, use_container_width=True, height=700)


# =====================
# 📅 최종 스케줄 (Sheet2 - 편집 가능)
# =====================
elif menu == "📅 최종 스케줄":
    st.header("📅 최종 스케줄")
    df = load_gsheet_final()

    if df.empty:
        st.info("저장된 데이터가 없습니다.")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            agency_filter = st.selectbox("의뢰기관", ["전체"] + sorted(df["의뢰기관"].dropna().unique().tolist()))
        with col2:
            instructor_filter = st.selectbox("강사님", ["전체"] + sorted(df["강사님"].dropna().unique().tolist()))
        with col3:
            subject_filter = st.selectbox("과정명", ["전체"] + sorted(df["과정명"].dropna().unique().tolist()))

        filtered_df = df.copy()
        if agency_filter != "전체": filtered_df = filtered_df[filtered_df["의뢰기관"] == agency_filter]
        if instructor_filter != "전체": filtered_df = filtered_df[filtered_df["강사님"] == instructor_filter]
        if subject_filter != "전체": filtered_df = filtered_df[filtered_df["과정명"] == subject_filter]

        # 날짜 형식 변환
        try:
            filtered_df["강의일시"] = pd.to_datetime(filtered_df["강의일시"], errors="coerce").dt.date
        except Exception:
            pass

        original_df = filtered_df.copy()

        edited_gsheet_df = st.data_editor(
            filtered_df,
            use_container_width=True,
            height=700,
            num_rows="fixed",
            column_config=get_column_config()
        )

        if st.button("💾 변경사항 저장"):
            try:
                today = datetime.now().strftime("%Y-%m-%d")
                for idx in edited_gsheet_df.index:
                    changes = []
                    for col in COLUMNS:
                        if col == "변경이력":
                            continue
                        orig = str(original_df.loc[idx, col]) if idx in original_df.index else ""
                        new = str(edited_gsheet_df.loc[idx, col])
                        if orig != new:
                            changes.append(f"{col} {orig}→{new}")
                    if changes:
                        existing = str(edited_gsheet_df.loc[idx, "변경이력"]).strip()
                        new_history = f"[{today}] " + ", ".join(changes)
                        edited_gsheet_df.loc[idx, "변경이력"] = f"{existing} / {new_history}".strip(" /")

                # 필터된 행만 업데이트하고 전체 저장
                df.update(edited_gsheet_df)
                if save_gsheet_final(df):
                    st.success("변경사항 저장 완료!")
                    st.rerun()
            except Exception as e:
                st.error(f"저장 오류: {e}")


# =====================
# 📊 협회별 월별 스케줄
# =====================
elif menu == "📊 협회별 월별 스케줄":
    st.header("📊 협회별 월별 스케줄")
    df = load_gsheet_final()
    if df.empty:
        st.info("저장된 데이터가 없습니다.")
    else:
        try:
            df["강의일시_dt"] = pd.to_datetime(df["강의일시"], errors="coerce")
            df["월"] = df["강의일시_dt"].dt.month
            df["시수"] = pd.to_numeric(df["시수"], errors="coerce").fillna(0)
            pivot = df.pivot_table(index="의뢰기관", columns="월", values="시수", aggfunc="sum", fill_value=0)
            st.dataframe(pivot, use_container_width=True)
        except Exception as e:
            st.error(f"집계 오류: {e}")


# =====================
# 👨‍🏫 강사별 대시보드
# =====================
elif menu == "👨‍🏫 강사별 대시보드":
    st.header("👨‍🏫 강사별 대시보드")
    df = load_gsheet_final()
    if df.empty:
        st.info("저장된 데이터가 없습니다.")
    else:
        if "강사님" in df.columns:
            selected = st.selectbox("강사 선택", sorted(df["강사님"].dropna().unique().tolist()))
            instructor_df = df[df["강사님"] == selected].copy()
            st.subheader(f"{selected} 강사 일정")
            st.dataframe(instructor_df, use_container_width=True, height=500)
            try:
                total_hours = pd.to_numeric(instructor_df["시수"], errors="coerce").sum()
                total_fee = pd.to_numeric(instructor_df["강의료(1일)"], errors="coerce").sum()
                c1, c2 = st.columns(2)
                c1.metric("총 시수", f"{total_hours:.0f}시간")
                c2.metric("총 강의료", f"₩{total_fee:,.0f}")
            except Exception as e:
                st.error(f"집계 오류: {e}")
        else:
            st.warning("강사님 컬럼이 없습니다.")
