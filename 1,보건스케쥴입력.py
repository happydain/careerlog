import io
import pandas as pd
import streamlit as st
from datetime import datetime

from config import COLUMNS, AGENCY_OPTIONS, LOCATION_OPTIONS
from utils import calc_hours, calc_fee, get_column_config
from gsheet import append_to_gsheet, load_gsheet_raw, append_evidence_to_sheet
from parsers import (
    parse_kakao_text, parse_seoul_kakao, parse_hanahn_kakao,
    parse_suwon_excel, parse_jungdae_excel, parse_incheon_excel,
)
from gdrive import create_request_folder, get_folder_url

st.set_page_config(page_title="보건스케줄", page_icon="📅", layout="wide")
st.sidebar.title("📅 CareerLog")

st.title("📥 보건스케줄 입력")
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
    year = st.selectbox("기준 연도", list(range(2022, 2036)),
                        index=list(range(2022, 2036)).index(datetime.now().year))
with col2:
    default_date = datetime(year, datetime.now().month, datetime.now().day)
    try:
        common_date = st.date_input("의뢰일", value=default_date, format="YYYY/MM/DD")
    except Exception:
        common_date = st.date_input("의뢰일", value=datetime.now(), format="YYYY/MM/DD")
with col3:
    @st.cache_data(ttl=300)
    def get_requester_list():
        df = load_gsheet_raw()
        names = df["의뢰인"].dropna().unique().tolist()
        return sorted([n for n in names if n.strip()])

    existing_requesters = get_requester_list()
    if existing_requesters:
        requester_options = existing_requesters + ["직접 입력"]
        selected_requester = st.selectbox("의뢰인", requester_options)
        if selected_requester == "직접 입력":
            common_requester = st.text_input("새 이름 입력")
        else:
            common_requester = selected_requester
    else:
        common_requester = st.text_input("의뢰인")
with col4:
    common_method = st.selectbox("의뢰방법", ["카카오톡", "카카오톡+엑셀", "이메일", "전화", "문자", "기타"])

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
            df_text = parse_hanahn_kakao(raw_text, year, common_requester, request_date_str, common_method)
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
st.markdown("### 📎 증빙 파일")
st.info("💡 저장 후 증빙폴더 링크를 클릭해서 파일을 직접 드라이브에 업로드하세요.")
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

# ── 저장 완료 후 안내 ──────────────────────
if st.session_state.get("saved_done"):
    st.success("✅ 저장 완료!")
    if st.button("📋 의뢰일별 스케줄 확인하기", key="go_to_raw"):
        st.session_state.pop("saved_done")
        st.switch_page("pages/2_raw_schedule.py")

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

    # 목록에 없는 방식/위치 알림
    unknown_locations = [
        l for l in edited_df["방식/위치"].dropna().unique()
        if str(l).strip() and str(l) not in LOCATION_OPTIONS
    ]
    if unknown_locations:
        st.warning(f"⚠️ 목록에 없는 방식/위치: **{', '.join(unknown_locations)}** — 직접 수정해주세요.")

    st.divider()
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("💾 저장", key="save_btn"):
            if not common_requester.strip():
                st.error("담당자 이름을 입력해주세요.")
            else:
                with st.spinner("저장 중..."):

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

                    try:
                        folder_id  = create_request_folder(year, common_agency, request_date_str, common_requester)
                        folder_url = get_folder_url(folder_id)
                        if evidence_files:
                            append_evidence_to_sheet(
                                f"{request_date_str}_{common_requester}",
                                evidence_files
                            )
                    except Exception as e:
                        folder_url = ""
                        drive_errors.append(f"폴더 생성 실패: {e}")

                    for idx in edited_df.index:
                        edited_df.loc[idx, "증빙폴더"] = folder_url

                    result = append_to_gsheet(edited_df)
                    if result:
                        if drive_errors:
                            st.warning("⚠️ 드라이브 폴더 생성 실패 (시트는 저장됨):\n" + "\n".join(drive_errors))
                        else:
                            st.success("✅ 구글시트 + 드라이브 저장 완료!")
                        del st.session_state["temp_df"]
                        st.session_state.pop("raw_text_for_drive", None)
                        st.session_state.pop("excel_file_for_drive", None)
                        st.session_state["saved_done"] = True
                        st.rerun()
                    else:
                        st.error("❌ 구글시트 저장 실패")
                        if drive_errors:
                            st.warning("드라이브 오류:\n" + "\n".join(drive_errors))

    with col2:
        buffer = io.BytesIO()
        edited_df.to_excel(buffer, index=False, engine="xlsxwriter")
        st.download_button(
            label="📥 엑셀 다운로드",
            data=buffer.getvalue(),
            file_name=f"보건스케줄_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_btn",
        )

    with col3:
        if st.button("🧹 초기화", key="reset_btn"):
            del st.session_state["temp_df"]
            st.session_state.pop("raw_text_for_drive", None)
            st.session_state.pop("excel_file_for_drive", None)
            st.rerun()
