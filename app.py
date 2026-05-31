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
    "강의일시",
    "요일",
    "시작",
    "종료",
    "의뢰기관",
    "과정명",
    "대상자",
    "업종",
    "방식/위치",
    "강사님",
    "시수",
    "강의료(1시간)",
    "강의료(1일)",
    "의뢰자",
    "의뢰일",
    "특이사항",
    "변경이력",
    "내부메모"
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
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1

        existing = sheet.get_all_values()

        # 헤더가 없거나 1행이 비어있으면 헤더 삽입
        if not existing or existing[0] != COLUMNS:
            sheet.insert_row(COLUMNS, index=1)  # 1행에 헤더 삽입 (기존 데이터 밀어냄)

        df_clean = df.fillna("").astype(str)
        values = df_clean.values.tolist()
        sheet.append_rows(values)
        return True

    except Exception as e:
        st.exception(e)
        return False


def load_gsheet():
    try:
        client = get_gsheet_client()
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1
        data = sheet.get_all_records()

        if not data:
            return pd.DataFrame(columns=COLUMNS)

        df = pd.DataFrame(data)

        # 필수 컬럼 누락 시 빈 컬럼 추가
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = ""

        return df

    except Exception as e:
        st.error(f"구글시트 불러오기 오류: {e}")
        return pd.DataFrame(columns=COLUMNS)


# -----------------------------
# Common utils
# -----------------------------
def get_weekday(date_obj):
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    return weekdays[date_obj.weekday()]


def normalize_time(hour):
    hour = int(hour)
    return f"{hour:02d}:00"


def parse_time_range(text):
    text = str(text)

    # 월일 패턴만 제거 (반드시 "월"이 있는 경우만)
    text = re.sub(r"\d{1,2}월\s*\d{1,2}일", "", text)
    # 괄호 안 내용 제거
    text = re.sub(r"\([^)]*\)", "", text)

    # 13:00~15:00 형태
    match = re.search(r"(\d{1,2}:\d{2})\s*[-~]\s*(\d{1,2}:\d{2})", text)
    if match:
        return match.group(1), match.group(2)

    # 15시-18시 / 13-15시 / 13시-15 형태
    match = re.search(r"(\d{1,2})\s*시?\s*[-~]\s*(\d{1,2})\s*시", text)
    if match:
        return normalize_time(match.group(1)), normalize_time(match.group(2))

    # 13-15 형태
    match = re.search(r"(\d{1,2})\s*[-~]\s*(\d{1,2})(?!\d)", text)
    if match:
        return normalize_time(match.group(1)), normalize_time(match.group(2))

    return default_start, default_end


def calc_hours(start, end):
    try:
        s = int(str(start).split(":")[0])
        e = int(str(end).split(":")[0])
        return max(e - s, 0)
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


def extract_manager(text):
    match = re.search(r"담당자\s*[:：]\s*([가-힣]{2,4})", text)
    return match.group(1) if match else ""


def detect_agency(text):
    text = str(text)

    if "대한산안협" in text or "대한산업안전협회" in text:
        if "서울" in text:
            return "대한협서울"
        if "수원" in text:
            return "대한협수원"
        if "인천" in text:
            return "대한협인천"
        return "대한협"

    if "중대협" in text:
        return "중대협"

    if "한안협" in text:
        return "한안협"

    if "잡그레이드" in text:
        return "잡그레이드"

    return ""


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
            try:
                dates.append(datetime(year, int(month), day))
            except ValueError:
                pass

    normal_matches = re.findall(r"(\d{1,2})월\s*(\d{1,2})일", text)
    for month, day in normal_matches:
        try:
            date_obj = datetime(year, int(month), int(day))
            if date_obj not in dates:
                dates.append(date_obj)
        except ValueError:
            pass

    return dates


def make_row(
    date_obj,
    start,
    end,
    agency,
    subject,
    target,
    industry,
    location,
    instructor,
    hourly_fee
):
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
        "강의료(1일)": calc_fee(hours, hourly_fee),
        "의뢰자": "",
        "의뢰일": "",
        "특이사항": "",
        "변경이력": "",
        "내부메모": ""
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

        # 교육 정보 헤더 줄 (날짜 없는 줄)
        if "교육" in clean and not re.search(r"\d{1,2}월", clean):
            detected_agency = detect_agency(clean)
            if detected_agency:
                agency = detected_agency

            detected_target = detect_target(clean)
            if detected_target:
                target = detected_target

            detected_subject = detect_subject(clean)
            if detected_subject:
                subject = detected_subject

            continue

        # 시간 기본값 업데이트
        if "동일" in clean and re.search(r"\d{1,2}시", clean):
            clean_for_time = re.sub(r"\([^)]*\)", "", clean)  # (3시간) 제거
            start_default, end_default = parse_time_range(clean_for_time, start_default, end_default)
            continue

        # 담당자 줄 스킵
        if "담당자" in clean:
            continue

        dates = parse_dates_from_text(clean, year)

        if dates:
            start, end = parse_time_range(clean, start_default, end_default)
            detected_subject = detect_subject(clean)
            # ✅ 수정: 줄별 과목 감지 → 없으면 헤더 과목 → 없으면 기본값
            final_subject = detected_subject or subject or "응급처치"

            for date_obj in dates:
                rows.append(
                    make_row(
                        date_obj=date_obj,
                        start=start,
                        end=end,
                        agency=agency,
                        subject=final_subject,
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
        if "강의일" not in df.columns:
            continue

        lecture_date_raw = row.get("강의일")
        if pd.isna(lecture_date_raw):
            continue

        lecture_date = pd.to_datetime(lecture_date_raw, errors="coerce")
        if pd.isna(lecture_date):
            continue

        time_text = str(row.get("강의시간", ""))
        start, end = parse_time_range(time_text)

        instructor = str(row.get("주강사", "")) if pd.notna(row.get("주강사")) else ""
        subject_raw = str(row.get("과목", "")) if pd.notna(row.get("과목")) else ""
        subject = detect_subject(subject_raw) or subject_raw

        industry_raw = row.get("업종")
        industry = str(industry_raw) if pd.notna(industry_raw) else DEFAULT_INDUSTRY

        room_raw = row.get("지역")
        room = str(room_raw).strip() if pd.notna(room_raw) else ""
        location = f"오프 ({room})" if room else "오프"

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

st.sidebar.title("📅 CareerLog")

menu = st.sidebar.radio(
    "메뉴 선택",
    [
        "📥 보건스케줄 입력",
        "📋 보건스케줄 보기",
        "📊 협회별 월별 스케줄",
        "👨‍🏫 강사별 대시보드"
    ]
)

st.title("📅 보건스케줄 자동정리")
st.info("카톡 텍스트와 협회별 엑셀 파일을 같은 포맷으로 정리해 구글시트에 저장합니다.")


# =====================
# 📥 보건스케줄 입력
# =====================
if menu == "📥 보건스케줄 입력":

    st.header("📥 보건스케줄 입력")

    # --- 카톡 입력 ---
    st.markdown("### 카톡/이메일 강의 의뢰 텍스트")

    year = st.number_input(
        "기준 연도",
        min_value=2024,
        max_value=2035,
        value=datetime.now().year,
        step=1
    )

    raw_text = st.text_area(
        "강의 요청 메시지를 붙여넣으세요.",
        height=250
    )

    if st.button("🪄 카톡 일정 분석"):
        if raw_text.strip():
            df_text = parse_kakao_text(raw_text, year)
            if df_text.empty:
                st.warning("날짜 정보를 찾지 못했습니다. 텍스트를 확인해주세요.")
            else:
                st.session_state["temp_df"] = df_text
                st.success(f"{len(df_text)}건 일정 생성 완료")
        else:
            st.warning("텍스트를 입력해주세요.")

    st.divider()

    # --- 엑셀 업로드 ---
    st.markdown("### 강의의뢰 엑셀 업로드")

    uploaded_file = st.file_uploader(
        "강의의뢰 엑셀 업로드",
        type=["xlsx"]
    )

    col1, col2 = st.columns(2)

    with col1:
        excel_agency = st.selectbox(
            "의뢰기관",
            [
                "대한협수원",
                "대한협인천",
                "대한협서울",
                "중대협",
                "한안협",
                "잡그레이드"
            ]
        )

   
    if uploaded_file:
        if st.button("📄 엑셀 일정 변환"):
            try:
                df_excel = parse_daehan_excel(
                    uploaded_file,
                    excel_agency,
                    excel_target   # ✅ 수정: "" → excel_target
                )
                if df_excel.empty:
                    st.warning("변환된 일정이 없습니다. 엑셀 형식을 확인해주세요.")
                else:
                    st.session_state["temp_df"] = df_excel
                    st.success(f"{len(df_excel)}건 일정 생성 완료")
            except Exception as e:
                st.error(f"엑셀 변환 오류: {e}")

    st.divider()

    # =====================
    # 수동 직접 입력 활성화 버튼
    # =====================
    st.markdown("### ✍️ 수동으로 직접 입력하기")
    if st.button("➕ 빈 테이블 생성 (직접 입력용)"):
        # COLUMNS 구조를 가진 빈 데이터프레임을 생성하여 세션에 저장
        df_empty = pd.DataFrame(columns=COLUMNS)
        st.session_state["temp_df"] = df_empty
        st.rerun()

    st.divider()

    # =====================
    # 최종 확인 (기존 코드 수정)
    # =====================
    st.header("📋 최종 확인 및 저장")

    if "temp_df" in st.session_state:
        # 데이터 편집기 호출
        edited_df = st.data_editor(
            st.session_state["temp_df"],
            use_container_width=True,
            num_rows="dynamic",  # 이 옵션 덕분에 직접 행 추가/삭제가 가능합니다.
            column_config={
                "강의일시": st.column_config.TextColumn("강의일시"),
                "요일": st.column_config.SelectboxColumn("요일", options=["월", "화", "수", "목", "금", "토", "일"]),
                "시작": st.column_config.TextColumn("시작"),
                "종료": st.column_config.TextColumn("종료"),
                "의뢰기관": st.column_config.SelectboxColumn("의뢰기관", options=["대한협수원", "대한협인천", "대한협서울", "중대협", "한안협", "잡그레이드"]),
                
                # (기존에 작성하신 기존 column_config 내용들을 이어서 쭉 적어주세요)
                "강의료(1시간)": st.column_config.NumberColumn("강의료(1시간)", format="₩%d"),
                "강의료(1일)": st.column_config.NumberColumn("강의료(1일)", format="₩%d"),
                "시수": st.column_config.NumberColumn("시수", format="%d"),
                "방식/위치": st.column_config.SelectboxColumn("방식/위치", options=["동시송출","줌","인천 1강의실","인천 2강의실","수원 1층","수원 5층","서울 교육장","기타"]),
                "특이사항": st.column_config.TextColumn("특이사항", width="large"),
                "변경이력": st.column_config.TextColumn("변경이력", width="large"),
                "내부메모": st.column_config.TextColumn("내부메모", width="large")
            }
        )
        
        # [중요] 사용자가 직접 입력할 때 '시수'와 '강의료(1일)'가 자동 계산되도록 보완
        if not edited_df.empty:
            try:
                # 시작/종료 시간을 기반으로 시수 계산
                edited_df["시수"] = edited_df.apply(lambda r: calc_hours(r["시작"], r["종료"]) if pd.notna(r["시작"]) and pd.notna(r["종료"]) else 0, axis=1)
                # 시수와 시간당 강의료를 기반으로 1일 강의료 계산
                edited_df["강의료(1일)"] = edited_df.apply(lambda r: calc_fee(r["시수"], r["강의료(1시간)"]) if pd.notna(r["시수"]) and pd.notna(r["강의료(1시간)"]) else 0, axis=1)
            except Exception:
                pass
    
        st.divider()
        
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("💾 구글시트 저장"):
                if append_to_gsheet(edited_df):
                    st.success("구글시트 저장 완료")
                    del st.session_state["temp_df"]
                    st.rerun()
    
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
            if st.button("🧹 초기화"):
                del st.session_state["temp_df"]
                st.rerun()


# =====================
# 📋 보건스케줄 보기
# =====================
elif menu == "📋 보건스케줄 보기":

    st.header("📋 보건스케줄 보기")

    df = load_gsheet()

    if df.empty:
        st.info("저장된 데이터가 없습니다.")
    else:
        # ✅ 수정: 컬럼 존재 여부 확인 후 필터 생성
        col1, col2, col3 = st.columns(3)

        with col1:
            agency_options = sorted(df["의뢰기관"].dropna().unique().tolist()) if "의뢰기관" in df.columns else []
            agency_filter = st.selectbox("의뢰기관", ["전체"] + agency_options)

        with col2:
            instructor_options = sorted(df["강사님"].dropna().unique().tolist()) if "강사님" in df.columns else []
            instructor_filter = st.selectbox("강사님", ["전체"] + instructor_options)

        with col3:
            subject_options = sorted(df["과정명"].dropna().unique().tolist()) if "과정명" in df.columns else []
            subject_filter = st.selectbox("과정명", ["전체"] + subject_options)

        filtered_df = df.copy()

        if agency_filter != "전체" and "의뢰기관" in filtered_df.columns:
            filtered_df = filtered_df[filtered_df["의뢰기관"] == agency_filter]

        if instructor_filter != "전체" and "강사님" in filtered_df.columns:
            filtered_df = filtered_df[filtered_df["강사님"] == instructor_filter]

        if subject_filter != "전체" and "과정명" in filtered_df.columns:
            filtered_df = filtered_df[filtered_df["과정명"] == subject_filter]

        st.dataframe(filtered_df, use_container_width=True, height=700)


# =====================
# 📊 협회별 월별 스케줄
# =====================
elif menu == "📊 협회별 월별 스케줄":

    st.header("📊 협회별 월별 스케줄")

    df = load_gsheet()

    if df.empty:
        st.info("저장된 데이터가 없습니다.")
    else:
        if "강의일시" in df.columns and "의뢰기관" in df.columns and "시수" in df.columns:
            try:
                df["강의일시_dt"] = pd.to_datetime(df["강의일시"], errors="coerce")
                df["월"] = df["강의일시_dt"].dt.month
                df["시수"] = pd.to_numeric(df["시수"], errors="coerce").fillna(0)

                pivot = df.pivot_table(
                    index="의뢰기관",
                    columns="월",
                    values="시수",
                    aggfunc="sum",
                    fill_value=0
                )
                st.dataframe(pivot, use_container_width=True)
            except Exception as e:
                st.error(f"집계 오류: {e}")
        else:
            st.warning("필요한 컬럼(강의일시, 의뢰기관, 시수)이 없습니다.")


# =====================
# 👨‍🏫 강사별 대시보드
# =====================
elif menu == "👨‍🏫 강사별 대시보드":

    st.header("👨‍🏫 강사별 대시보드")

    df = load_gsheet()

    if df.empty:
        st.info("저장된 데이터가 없습니다.")
    else:
        if "강사님" in df.columns:
            instructor_list = sorted(df["강사님"].dropna().unique().tolist())
            selected = st.selectbox("강사 선택", instructor_list)

            instructor_df = df[df["강사님"] == selected].copy()

            st.subheader(f"{selected} 강사 일정")
            st.dataframe(instructor_df, use_container_width=True, height=500)

            if "시수" in instructor_df.columns and "강의료(1일)" in instructor_df.columns:
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
