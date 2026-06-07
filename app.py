import io
import pandas as pd
import streamlit as st
from datetime import datetime

from config import COLUMNS, AGENCY_OPTIONS
from utils import calc_hours, calc_fee, get_column_config
from gsheet import append_to_gsheet, load_gsheet_raw, load_gsheet_final, save_gsheet_final
from parsers import (
    parse_kakao_text, parse_seoul_kakao, parse_hanahn_kakao,
    parse_suwon_excel, parse_jungdae_excel, parse_incheon_excel,
)
from gdrive import (
    create_careerlog_structure, get_folder_url, append_change_log,
)

# ─────────────────────────────────────────────
st.set_page_config(page_title="보건스케줄", page_icon="📅", layout="wide")
# ─────────────────────────────────────────────

st.sidebar.title("📅 CareerLog")
menu = st.sidebar.radio("메뉴 선택", [
    "📥 보건스케줄 입력",
    "📋 의뢰일별 스케줄",
    "📅 최종 스케줄(취소,변경반영)",
    "📊 협회별 월별 스케줄",
    "👨‍🏫 강사별 대시보드",
])

st.title("📅 보건스케줄 자동정리")


# ══════════════════════════════════════════════
# 📥 보건스케줄 입력
# ══════════════════════════════════════════════
if menu == "📥 보건스케줄 입력":
    st.header("📥 보건스케줄 입력")
    st.info(
        "카카오톡·이메일·엑셀로 받은 강의 의뢰를 붙여넣거나 업로드하세요.\n"
        "저장 시 구글시트 + 구글드라이브 폴더가 자동 생성됩니다."
    )

    # ── 기본 정보 ──────────────────────────────
    st.markdown("### ⚙️ 기본 정보")
    common_agency = st.selectbox(
        "🏢 의뢰기관 (필수)",
        AGENCY_OPTIONS,
        help="카톡/엑셀 모두 이 기관으로 처리됩니다."
    )
    st.info(f"📌 현재 선택된 의뢰기관: **{common_agency}**")
    st.divider()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        year = st.selectbox("기준 연도", list(range(2024, 2036)),
                            index=list(range(2024, 2036)).index(datetime.now().year))
    with col2:
        common_date = st.date_input("의뢰일", value=datetime.now(), format="YYYY/MM/DD")
    with col3:
        @st.cache_data(ttl=300)
        def get_requester_list():
            df = load_gsheet_raw()
            names = df["의뢰인"].dropna().unique().tolist()
            return sorted([n for n in names if n.strip()])

        existing_requesters = get_requester_list()
        requester_options = ["직접 입력"] + existing_requesters
        selected_requester = st.selectbox("의뢰인", requester_options)
        if selected_requester == "직접 입력":
            common_requester = st.text_input("이름 입력")
        else:
            common_requester = selected_requester
    with col4:
        common_method = st.selectbox("의뢰방법", ["카카오톡", "이메일", "전화", "문자", "기타"])

    request_date_str = common_date.strftime("%Y-%m-%d")

    st.divider()

    # ── 카톡 입력 ──────────────────────────────
    st.markdown("### 💬 카톡 / 이메일 텍스트 입력")
    st.info(f"📌 현재 의뢰기관: **{common_agency}** · 의뢰인: **{common_requester or '미입력'}** · {request_date_str}")
    raw_text = st.text_area("강의 요청 메시지를 붙여넣으세요.", height=220, key="raw_text_input")

    if st.button("🪄 카톡 일정 분석"):
        if not common_requester.strip():
            st.error("담당자 이름을 입력해주세요.")
        elif not raw_text.strip():
            st.warning("텍스트를 입력해주세요.")
        else:
            if common_agency == "대한협서울":
                df_text = parse_seoul_kakao(raw_text, year, common_requester, request_date_str)
            elif common_agency == "한안협":
                df_text = parse_hanahn_kakao(raw_text, year, common_requester, request_date_str)
            else:
                df_text = parse_kakao_text(raw_text, year)
                df_text["의뢰기관"] = common_agency
                df_text["의뢰인"] = common_requester
                df_text["의뢰일"] = request_date_str
                df_text["의뢰방법"] = common_method

            if df_text.empty:
                st.warning("날짜 정보를 찾지 못했습니다.")
            else:
                st.session_state["temp_df"] = df_text
                st.session_state["raw_text_for_drive"] = raw_text
                st.session_state.pop("excel_file_for_drive", None)
                st.success(f"✅ {len(df_text)}건 일정 생성 완료")

    st.divider()

    # ── 엑셀 업로드 ────────────────────────────
    st.markdown("### 📄 강의의뢰 엑셀 업로드")
    st.info(f"📌 현재 의뢰기관: **{common_agency}** · 의뢰인: **{common_requester or '미입력'}** · {request_date_str}")
    uploaded_file = st.file_uploader("엑셀 파일 (.xlsx)", type=["xlsx"])

    if uploaded_file:
        if st.button("📄 엑셀 일정 변환"):
            if not common_requester.strip():
                st.error("담당자 이름을 입력해주세요.")
            else:
                try:
                    if common_agency == "대한협인천":
                        df_excel = parse_incheon_excel(uploaded_file, common_agency,
                                                       common_requester, request_date_str)
                    elif common_agency == "중대협":
                        df_excel = parse_jungdae_excel(uploaded_file, common_requester,
                                                       request_date_str, year)
                    else:
                        df_excel = parse_suwon_excel(uploaded_file, common_agency)
                        df_excel["의뢰인"] = common_requester
                        df_excel["의뢰일"] = request_date_str
                        df_excel["의뢰방법"] = common_method

                    if df_excel.empty:
                        st.warning("변환된 일정이 없습니다.")
                    else:
                        st.session_state["temp_df"] = df_excel
                        st.session_state["raw_text_for_drive"] = ""
                        st.session_state["excel_file_for_drive"] = uploaded_file
                        st.success(f"✅ {len(df_excel)}건 일정 생성 완료")
                except Exception as e:
                    st.error(f"엑셀 변환 오류: {e}")

    st.divider()

    # ── 증빙 파일 업로드 ────────────────────────
    st.markdown("### 📎 증빙 파일 업로드 (카톡 캡처, PDF 등)")
    if st.session_state.get("excel_file_for_drive"):
        st.success(f"📎 엑셀 파일 자동 포함: **{st.session_state['excel_file_for_drive'].name}**")

    evidence_files = st.file_uploader(
        "추가 증빙자료 (캡처, PDF 등)",
        type=["png", "jpg", "jpeg", "pdf", "docx", "xlsx"],
        accept_multiple_files=True,
        key="evidence_uploader"
    )

    st.divider()

    # ── 수동 입력 ──────────────────────────────
    st.markdown("### ✍️ 수동으로 직접 입력하기")
    if st.button("➕ 빈 테이블 생성"):
        st.session_state["temp_df"] = pd.DataFrame(columns=COLUMNS)
        st.session_state["raw_text_for_drive"] = ""
        st.rerun()

    st.divider()

    # ── 최종 확인 및 저장 ──────────────────────
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
            column_config=get_column_config(),
        )

        st.divider()
        col1, col2, col3 = st.columns(3)

        # ── 저장 ──
        with col1:
            if st.button("💾 저장", key="save_btn"):
                if not common_requester.strip():
                    st.error("담당자 이름을 입력해주세요.")
                else:
                    with st.spinner("저장 중..."):

                        # 🛠️ 수정한 문법 오류 해결 영역
                        def auto_weekday(r):
                            try:
                                return ["월","화","수","목","금","토","일"][pd.to_datetime(r["강의일시"]).weekday()]
                            except:
                                return r.get("요일", "")

                        def auto_fee(r):
                            if str(r.get("의뢰기관", "")) == "한안협":
                                return 120000 if str(r.get("강사님", "")) == "이다인" else 110000
                            return r.get("강의료(1시간)", 100000)

                        edited_df["요일"] = edited_df.apply(auto_weekday, axis=1)
                        edited_df["시수"] = edited_df.apply(
                            lambda r: calc_hours(r["시작"], r["종료"])
                            if pd.notna(r.get("시작")) and pd.notna(r.get("종료")) else 0, axis=1
                        )
                        edited_df["강의료(1시간)"] = edited_df.apply(auto_fee, axis=1)
                        edited_df["강의료(1일)"] = edited_df.apply(
                            lambda r: calc_fee(r["시수"], r["강의료(1시간)"])
                            if pd.notna(r.get("시수")) and pd.notna(r.get("강의료(1시간)")) else 0, axis=1
                        )

                        drive_errors = []

                        for idx in edited_df.index:
                            row = edited_df.loc[idx].to_dict()
                            try:
                                date_str = str(row.get("강의일시", ""))
                                agency   = str(row.get("의뢰기관", common_agency))
                                subject  = str(row.get("과정명", "")).replace(" ", "")
                                yr       = int(date_str[:4]) if len(date_str) >= 4 else year

                                folder_id  = create_careerlog_structure(yr, agency, date_str, subject)
