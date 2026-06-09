import io
import pandas as pd
import streamlit as st
from datetime import datetime

from config import COLUMNS, AGENCY_OPTIONS, LOCATION_OPTIONS
from utils import calc_hours, calc_fee, get_column_config
from gsheet import (
    append_to_gsheet, load_gsheet_raw, load_gsheet_final,
    save_gsheet_final, append_evidence_to_sheet,
)
from parsers import (
    parse_kakao_text, parse_seoul_kakao, parse_hanahn_kakao,
    parse_suwon_excel, parse_suwon2_excel, parse_jungdae_excel, parse_incheon_excel,
)
from gdrive import (
    create_request_folder, get_folder_url, append_change_log,
)

st.set_page_config(page_title="보건스케줄", page_icon="📅", layout="wide")

st.markdown("""
<style>
[data-testid="stSidebar"] {
    min-width: 230px !important;
    max-width: 230px !important;
}
[data-testid="stSidebar"] label p {
    font-size: 14px !important;
    font-weight: 500 !important;
    white-space: nowrap !important;
}
</style>
""", unsafe_allow_html=True)

st.sidebar.title("📅 CareerLog")
default_menu = st.session_state.pop("_menu", "📥 보건스케줄 입력")
menu_options = [
    "📥 보건스케줄 입력",
    "📋 의뢰일별 스케줄(취소,변경)",
    "📅 최종 스케줄 매칭시스템",
    "📊 협회별 월별 스케줄",
    "👨‍🏫 강사별 대시보드",
]
menu = st.sidebar.radio("메뉴 선택", menu_options, index=menu_options.index(default_menu))
st.title("📅 보건스케줄 자동정리")


# ══════════════════════════════════════════════
# 📥 보건스케줄 입력
# ══════════════════════════════════════════════
if menu == "📥 보건스케줄 입력":
    st.header("📥 보건스케줄 입력")

    # ── 기본 정보 ──────────────────────────────
    st.markdown("### ⚙️ 기본 정보")
    st.divider()

    @st.cache_data(ttl=300)
    def get_requester_list():
        df = load_gsheet_raw()
        names = df["의뢰인"].dropna().unique().tolist()
        return sorted([n for n in names if n.strip()])

    col1, col2, col3, col4, col5 = st.columns([2, 1, 2, 2, 2])
    with col1:
        common_agency = st.selectbox("🏢 의뢰기관", AGENCY_OPTIONS)
    with col2:
        year = st.selectbox("기준연도", list(range(2022, 2036)),
                            index=list(range(2022, 2036)).index(datetime.now().year))
    with col3:
        default_date = datetime(year, datetime.now().month, datetime.now().day)
        try:
            common_date = st.date_input("의뢰일", value=default_date, format="YYYY/MM/DD")
        except Exception:
            common_date = st.date_input("의뢰일", value=datetime.now(), format="YYYY/MM/DD")
    with col4:
        existing_requesters = get_requester_list()
        if existing_requesters:
            requester_options = existing_requesters + ["직접 입력"]
            selected_requester = st.selectbox("의뢰인", requester_options)
            if selected_requester == "직접 입력":
                common_requester = st.text_input("이름 입력")
            else:
                common_requester = selected_requester
        else:
            common_requester = st.text_input("의뢰인")
    with col5:
        common_method = st.selectbox("의뢰방법", ["카카오톡", "카카오톡+엑셀", "이메일", "전화", "문자", "기타"])

    request_date_str = common_date.strftime("%Y-%m-%d")
    st.info(f"📌 **{common_agency}** · {common_requester or '의뢰인 미입력'} · {common_date.strftime('%Y/%m/%d')}")
    st.divider()

    # ── 엑셀 / 카톡 나란히 ──────────────────────
    col_excel, col_kakao = st.columns(2)

    with col_excel:
        st.markdown("### 📄 강의의뢰 엑셀 업로드")
        uploaded_file = st.file_uploader("엑셀 파일 (.xlsx)", type=["xlsx"])

        if uploaded_file:
            if st.button("📄 엑셀 일정 변환"):
                if not common_requester.strip():
                    st.error("담당자 이름을 입력해주세요.")
                else:
                    try:
                        if common_agency == "인천대한협":
                            df_excel = parse_incheon_excel(uploaded_file, common_agency,
                                                           common_requester, request_date_str)
                        elif common_agency == "중대협":
                            df_excel = parse_jungdae_excel(uploaded_file, common_requester,
                                                           request_date_str, year)
                        else:
                            try:
                                df_excel = parse_suwon2_excel(uploaded_file, common_agency)
                                if df_excel.empty:
                                    raise ValueError("데이터 없음")
                            except Exception:
                                try:
                                    uploaded_file.seek(0)
                                    df_excel = parse_suwon_excel(uploaded_file, common_agency)
                                except Exception as e2:
                                    raise ValueError(f"파싱 실패: {e2}")
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

            if st.button("🔍 원본 엑셀 미리보기", key="preview_excel"):
                uploaded_file.seek(0)
                df_preview = pd.read_excel(uploaded_file, header=None)
                st.dataframe(df_preview, use_container_width=True, height=300)

    with col_kakao:
        tab_kakao, tab_image = st.tabs(["💬 카톡/이메일", "🖼️ 이미지"])

    with tab_kakao:
        raw_text = st.text_area("강의 요청 메시지를 붙여넣으세요.", height=220, key="raw_text_input")
        if st.button("🪄 카톡 일정 분석"):
            # 기존 카톡 분석 코드 그대로

    with tab_image:
        img_file = st.file_uploader("강의 일정 이미지", type=["png","jpg","jpeg"], key="img_upload")
        if img_file and st.button("🪄 이미지 분석", key="img_analyze"):
            from parsers.image_parser import parse_image_schedule
            with st.spinner("이미지 분석 중..."):
                try:
                    extracted = parse_image_schedule(img_file)
                    st.text_area("추출된 텍스트", extracted, height=150, key="extracted_text")
                    df_img = parse_kakao_text(extracted, year)
                    if not df_img.empty:
                        df_img["의뢰기관"] = common_agency
                        df_img["의뢰인"] = common_requester
                        df_img["의뢰일"] = request_date_str
                        df_img["의뢰방법"] = common_method
                        st.session_state["temp_df"] = df_img
                        st.session_state["raw_text_for_drive"] = extracted
                        st.success(f"✅ {len(df_img)}건 일정 생성 완료")
                    else:
                        st.warning("일정을 찾지 못했습니다. 추출된 텍스트를 확인해주세요.")
                except Exception as e:
                    st.error(f"이미지 분석 오류: {e}")

    st.divider()

    # ── 증빙 파일 ────────────────────────────
    st.markdown("### 📎 증빙 파일")
    st.info("💡 저장 후 생성된 드라이브 폴더 링크를 클릭해서 파일을 직접 업로드하세요.")
    st.warning("""
    ⚠️ **자동 파일 업로드 기능 준비 중**
    현재 서비스 계정 구글 드라이브 용량 제한으로 파일 자동 업로드가 제한됩니다.
    추후 업데이트 예정이며, 현재는 드라이브 폴더에 직접 업로드해 주세요.
    """)

    # evidence_files = st.file_uploader(
    #     "추가 증빙자료 (캡처, PDF 등)",
    #     type=["png", "jpg", "jpeg", "pdf", "docx", "xlsx"],
    #     accept_multiple_files=True,
    #     key="evidence_uploader"
    # )

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
            st.session_state["_menu"] = "📋 의뢰일별 스케줄(취소,변경)"
            st.rerun()

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

        unknown_locations = [
            l for l in edited_df["방식/위치"].dropna().unique()
            if str(l).strip() and str(l) not in LOCATION_OPTIONS
        ]
        if unknown_locations:
            st.warning(f"⚠️ 목록에 없는 방식/위치: **{', '.join(unknown_locations)}**")
            cols = st.columns(len(unknown_locations))
            for i, loc in enumerate(unknown_locations):
                with cols[i]:
                    if st.button(f"✅ {loc} 추가", key=f"add_loc_{i}"):
                        LOCATION_OPTIONS.append(loc)
                        st.success(f"{loc} 추가됨!")
                        st.rerun()

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
                        evidence_files = []  # 자동 업로드 비활성화

                        try:
                            lecture_count = len(edited_df)
                            folder_id  = create_request_folder(
                                year, common_agency, request_date_str, common_requester,
                                f"의뢰_{lecture_count}건"
                            )
                            folder_url = get_folder_url(folder_id)
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
                                st.success(f"✅ 저장 완료! 📂 [증빙폴더 열기]({folder_url})" if folder_url else "✅ 구글시트 저장 완료!")
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


# ══════════════════════════════════════════════
# 📋 의뢰일별
# ══════════════════════════════════════════════
elif menu == "📋 의뢰일별 스케줄(취소,변경)":
    st.header("📋 의뢰일별 스케줄(취소,변경)")
    st.info("""
    📌 **이 페이지에서 할 수 있는 것**
    - 🧑‍🏫 **강사님 지정** - 의뢰 건별로 강사님 이름 입력
    - 📝 **변경이력 확인** - 강사 변경, 시간 변경 등 이력 조회
    - 💾 저장 시 변경일자·변경이력·변경의뢰인 자동 기록
    """)
    df = load_gsheet_raw()

    if df.empty:
        st.info("저장된 데이터가 없습니다.")
    else:
        df["_년도"] = pd.to_datetime(df["강의일시"], errors="coerce").dt.year
        df["_월"]   = pd.to_datetime(df["강의일시"], errors="coerce").dt.month
        year_list  = ["전체"] + sorted(df["_년도"].dropna().unique().astype(int).tolist(), reverse=True)
        month_list = ["전체"] + sorted(df["_월"].dropna().unique().astype(int).tolist())

        col0, col1, col2, col3, col4 = st.columns([1, 2, 2, 2, 2])
        with col0:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if st.button("↺", key="reset_filter", help="전체 보기", use_container_width=True):
                for k in ["year_f", "month_f", "agency_f", "instr_f"]:
                    st.session_state.pop(k, None)
                st.rerun()
        with col1:
            year_f = st.selectbox("년도", year_list)
        with col2:
            month_f = st.selectbox("월", month_list)
        with col3:
            agency_f = st.selectbox("의뢰기관", ["전체"] + sorted(df["의뢰기관"].dropna().unique().tolist()))
        with col4:
            instr_f = st.selectbox("강사님", ["전체"] + sorted(df["강사님"].dropna().unique().tolist()))

        fdf = df.copy()
        if year_f   != "전체": fdf = fdf[fdf["_년도"] == int(year_f)]
        if month_f  != "전체": fdf = fdf[fdf["_월"]   == int(month_f)]
        if agency_f != "전체": fdf = fdf[fdf["의뢰기관"] == agency_f]
        if instr_f  != "전체": fdf = fdf[fdf["강사님"]   == instr_f]
        fdf = fdf.drop(columns=["_년도", "_월"], errors="ignore")
        df  = df.drop(columns=["_년도", "_월"], errors="ignore")

        total_hours = pd.to_numeric(fdf["시수"], errors="coerce").sum()
        total_fee   = pd.to_numeric(fdf["강의료(1일)"], errors="coerce").sum()

        st.markdown(f"""
        <div style="display:flex; gap:16px; margin-bottom:8px;">
            <div style="background:#f0f4ff; border-radius:10px; padding:12px 24px; text-align:center; flex:1;">
                <div style="font-size:12px; color:#666;">총 강의 건수</div>
                <div style="font-size:20px; font-weight:bold; color:#1a56db;">{len(fdf)}건</div>
            </div>
            <div style="background:#f0fff4; border-radius:10px; padding:12px 24px; text-align:center; flex:1;">
                <div style="font-size:12px; color:#666;">총 시수</div>
                <div style="font-size:20px; font-weight:bold; color:#0e9f6e;">{total_hours:.0f}시간</div>
            </div>
            <div style="background:#fff8f0; border-radius:10px; padding:12px 24px; text-align:center; flex:1;">
                <div style="font-size:12px; color:#666;">총 강의료</div>
                <div style="font-size:20px; font-weight:bold; color:#e3a008;">₩{total_fee:,.0f}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()

        try:
            fdf["강의일시"] = pd.to_datetime(fdf["강의일시"], errors="coerce").dt.date
        except Exception:
            pass

        original_fdf = fdf.copy()
        edited_raw_df = st.data_editor(
            fdf,
            use_container_width=True,
            height=600,
            num_rows="fixed",
            column_config=get_column_config(),
        )

        modifier = st.text_input("변경자 이름", placeholder="예: 이다인", key="raw_modifier")
        if st.button("💾 강사/메모 저장", key="raw_save_btn"):
            today = datetime.now().strftime("%Y-%m-%d")
            for idx in edited_raw_df.index:
                changes = []
                for col in ["강사님", "내부메모", "요청사항"]:
                    if col not in original_fdf.columns:
                        continue
                    orig = str(original_fdf.loc[idx, col]) if idx in original_fdf.index else ""
                    new  = str(edited_raw_df.loc[idx, col])
                    if orig != new:
                        changes.append(f"{col} {orig}→{new}")

                if changes:
                    summary  = ", ".join(changes)
                    existing = str(edited_raw_df.loc[idx, "변경이력"]).strip()
                    new_hist = f"[{today}] {summary}"
                    edited_raw_df.loc[idx, "변경이력"]   = f"{existing} / {new_hist}".strip(" /")
                    edited_raw_df.loc[idx, "변경일자"]   = today
                    edited_raw_df.loc[idx, "변경의뢰인"] = modifier or "미입력"

                    folder_url = str(edited_raw_df.loc[idx, "증빙폴더"])
                    if folder_url.startswith("https://drive.google.com"):
                        try:
                            folder_id = folder_url.split("/")[-1]
                            append_change_log(folder_id, summary, modifier or "미입력")
                        except Exception:
                            pass

            df.update(edited_raw_df)
            from gsheet import save_gsheet_raw
            if save_gsheet_raw(df):
                st.success("✅ 저장 완료!")
                st.rerun()


# ══════════════════════════════════════════════
# 📅 최종 스케줄 매칭시스템
# ══════════════════════════════════════════════
elif menu == "📅 최종 스케줄 매칭시스템":
    st.header("📅 최종 스케줄 매칭시스템")

    start_year, start_month = 2022, 1
    end_year, end_month = 2027, 12

    months = []
    y, m = start_year, start_month
    while (y, m) <= (end_year, end_month):
        months.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1

    year_colors = {
        2022: "#FF6B6B",
        2023: "#FF9F43",
        2024: "#54A0FF",
        2025: "#5F27CD",
        2026: "#00D2D3",
        2027: "#1DD1A1",
    }

    years = sorted(set(y for y, m in months))
    for yr in years:
        yr_months = [mo for y, mo in months if y == yr]
        color = year_colors.get(yr, "#888")

        st.markdown(f"""
        <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
            <span style="background:{color}; color:white; border-radius:6px;
                         padding:2px 10px; font-size:12px; font-weight:bold;
                         min-width:50px; text-align:center;">{yr}년</span>
        </div>
        """, unsafe_allow_html=True)

        cols = st.columns(len(yr_months))
        for i, mo in enumerate(yr_months):
            with cols[i]:
                selected = (
                    st.session_state.get("filter_year") == yr and
                    st.session_state.get("filter_month") == mo
                )
                if st.button(
                    f"{mo}월",
                    key=f"month_{yr}_{mo}",
                    use_container_width=True,
                    type="primary" if selected else "secondary"
                ):
                    st.session_state["filter_year"] = yr
                    st.session_state["filter_month"] = mo
                    st.rerun()

    st.divider()

    filter_year  = st.session_state.get("filter_year")
    filter_month = st.session_state.get("filter_month")

    if not filter_year or not filter_month:
        st.info("위에서 월을 선택하세요.")
    else:
        st.markdown(f"### 📅 {filter_year}년 {filter_month}월 강의 일정")

        df = load_gsheet_final()
        if df.empty:
            st.info("저장된 데이터가 없습니다.")
        else:
            df["_dt"] = pd.to_datetime(df["강의일시"], errors="coerce")
            fdf = df[
                (df["_dt"].dt.year  == filter_year) &
                (df["_dt"].dt.month == filter_month)
            ].drop(columns=["_dt"]).copy()

            if fdf.empty:
                st.info(f"{filter_year}년 {filter_month}월 데이터가 없습니다.")
            else:
                total_hours = pd.to_numeric(fdf["시수"], errors="coerce").sum()
                total_fee   = pd.to_numeric(fdf["강의료(1일)"], errors="coerce").sum()
                c1, c2, c3 = st.columns(3)
                c1.metric("총 강의 건수", f"{len(fdf)}건")
                c2.metric("총 시수", f"{total_hours:.0f}시간")
                c3.metric("총 강의료", f"₩{total_fee:,.0f}")
                st.divider()

                if "auto_matched_df" in st.session_state:
                    fdf = st.session_state.pop("auto_matched_df")

                try:
                    fdf["강의일시"] = pd.to_datetime(fdf["강의일시"], errors="coerce").dt.date
                except Exception:
                    pass

                original_fdf = fdf.copy()
                edited_fdf = st.data_editor(
                    fdf,
                    use_container_width=True,
                    height=500,
                    num_rows="fixed",
                    column_config=get_column_config(),
                )

                col_m1, col_m2, col_m3 = st.columns([2, 2, 4])
                with col_m1:
                    if st.button("🤖 강사 자동매칭", key="auto_match_btn"):
                        count = 0
                        for idx in edited_fdf.index:
                            instructor = str(edited_fdf.loc[idx, "강사님"]).strip()
                            if not instructor or instructor in ("nan", ""):
                                edited_fdf.loc[idx, "강사님"] = "송주영"
                                count += 1
                        st.session_state["auto_matched_df"] = edited_fdf
                        st.success(f"✅ {count}건 → 송주영 자동 배정!")
                        st.rerun()

                with col_m2:
                    modifier = st.text_input("변경자", placeholder="이름 입력", key="match_modifier")

                with col_m3:
                    if st.button("💾 저장", key="match_save_btn"):
                        today = datetime.now().strftime("%Y-%m-%d")
                        for idx in edited_fdf.index:
                            changes = []
                            for col in COLUMNS:
                                if col in ("변경이력", "증빙폴더"):
                                    continue
                                orig = str(original_fdf.loc[idx, col]) if idx in original_fdf.index else ""
                                new  = str(edited_fdf.loc[idx, col])
                                if orig != new:
                                    changes.append(f"{col} {orig}→{new}")
                            if changes:
                                summary  = ", ".join(changes)
                                existing = str(edited_fdf.loc[idx, "변경이력"]).strip()
                                new_hist = f"[{today}] {summary}"
                                edited_fdf.loc[idx, "변경이력"]   = f"{existing} / {new_hist}".strip(" /")
                                edited_fdf.loc[idx, "변경일자"]   = today
                                edited_fdf.loc[idx, "변경의뢰인"] = modifier or "미입력"

                                folder_url = str(edited_fdf.loc[idx, "증빙폴더"])
                                if folder_url.startswith("https://drive.google.com"):
                                    try:
                                        folder_id = folder_url.split("/")[-1]
                                        append_change_log(folder_id, summary, modifier or "미입력")
                                    except Exception:
                                        pass

                        df.update(edited_fdf)
                        if save_gsheet_final(df):
                            st.success("✅ 저장 완료!")
                            st.rerun()


# ══════════════════════════════════════════════
# 📊 협회별 월별 스케줄
# ══════════════════════════════════════════════
elif menu == "📊 협회별 월별 스케줄":
    st.header("📊 협회별 월별 스케줄")
    df = load_gsheet_final()
    if df.empty:
        st.info("저장된 데이터가 없습니다.")
    else:
        try:
            df["_dt"] = pd.to_datetime(df["강의일시"], errors="coerce")
            df["월"]  = df["_dt"].dt.month
            df["시수"] = pd.to_numeric(df["시수"], errors="coerce").fillna(0)
            pivot = df.pivot_table(index="의뢰기관", columns="월", values="시수",
                                   aggfunc="sum", fill_value=0)
            st.dataframe(pivot, use_container_width=True)

            st.subheader("💰 협회별 월별 강의료 합계")
            df["강의료(1일)"] = pd.to_numeric(df["강의료(1일)"], errors="coerce").fillna(0)
            pivot_fee = df.pivot_table(index="의뢰기관", columns="월", values="강의료(1일)",
                                       aggfunc="sum", fill_value=0)
            st.dataframe(pivot_fee.style.format("₩{:,.0f}"), use_container_width=True)
        except Exception as e:
            st.error(f"집계 오류: {e}")


# ══════════════════════════════════════════════
# 👨‍🏫 강사별 대시보드
# ══════════════════════════════════════════════
elif menu == "👨‍🏫 강사별 대시보드":
    from gcalendar import get_events
    from config import INSTRUCTOR_CALENDARS
    import calendar as cal_module

    st.header("👨‍🏫 강사별 대시보드")
    df = load_gsheet_final()

    if df.empty:
        st.info("저장된 데이터가 없습니다.")
    elif "강사님" not in df.columns:
        st.warning("강사님 컬럼이 없습니다.")
    else:
        selected = st.selectbox("강사 선택", sorted(df["강사님"].dropna().unique().tolist()))
        idf = df[df["강사님"] == selected].copy()
        cal_id = INSTRUCTOR_CALENDARS.get(selected, "")

        try:
            total_hours = pd.to_numeric(idf["시수"], errors="coerce").sum()
            total_fee   = pd.to_numeric(idf["강의료(1일)"], errors="coerce").sum()
            c1, c2, c3 = st.columns(3)
            c1.metric("총 강의 건수", f"{len(idf)}건")
            c2.metric("총 시수", f"{total_hours:.0f}시간")
            c3.metric("총 강의료", f"₩{total_fee:,.0f}")
        except Exception as e:
            st.error(f"집계 오류: {e}")

        st.divider()

        tab1, tab2 = st.tabs(["📥 캘린더 전체 가져오기", "📅 이번달 스케줄"])

        with tab1:
            st.markdown("2022년부터 현재까지 캘린더 일정을 가져와 엑셀로 저장합니다.")
            if not cal_id:
                st.warning(f"⚠️ {selected} 강사님 캘린더가 연동되지 않았습니다.")
            else:
                if st.button("📥 전체 일정 가져오기", key="import_cal_btn"):
                    with st.spinner("2022년부터 전체 일정 가져오는 중..."):
                        all_events = []
                        y, m = 2022, 1
                        now = datetime.now()
                        while (y, m) <= (now.year, now.month):
                            first_day = f"{y}-{m:02d}-01"
                            last_day  = f"{y}-{m:02d}-{cal_module.monthrange(y, m)[1]:02d}"
                            events = get_events(first_day, last_day, calendar_id=cal_id)
                            all_events.extend(events)
                            m += 1
                            if m > 12:
                                m = 1
                                y += 1

                        rows = []
                        for e in all_events:
                            start = e.get("start", {}).get("dateTime", e.get("start", {}).get("date", ""))
                            end   = e.get("end",   {}).get("dateTime", e.get("end",   {}).get("date", ""))
                            rows.append({
                                "강의일시": start[:10] if start else "",
                                "시작":    start[11:16] if len(start) > 10 else "",
                                "종료":    end[11:16]   if len(end)   > 10 else "",
                                "제목":    e.get("summary", ""),
                                "장소":    e.get("location", ""),
                                "이벤트ID": e.get("id", ""),
                            })

                        st.session_state["cal_imported"] = pd.DataFrame(rows)
                        st.session_state["cal_imported_name"] = selected
                        st.success(f"✅ {len(rows)}건 가져왔어요!")
                        st.rerun()

                if "cal_imported" in st.session_state:
                    cal_df = st.session_state["cal_imported"]
                    name   = st.session_state.get("cal_imported_name", selected)
                    st.dataframe(cal_df, use_container_width=True, height=400)
                    col1, col2 = st.columns(2)
                    with col1:
                        buffer = io.BytesIO()
                        cal_df.to_excel(buffer, index=False, engine="xlsxwriter")
                        st.download_button(
                            label="📥 엑셀 다운로드",
                            data=buffer.getvalue(),
                            file_name=f"캘린더_{name}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="cal_download_btn",
                        )
                    with col2:
                        if st.button("🗑️ 초기화", key="cal_reset_btn"):
                            del st.session_state["cal_imported"]
                            st.rerun()

        with tab2:
            if not cal_id:
                st.warning(f"⚠️ {selected} 강사님 캘린더가 연동되지 않았습니다.")
            else:
                now = datetime.now()
                col1, col2 = st.columns(2)
                with col1:
                    view_year = st.selectbox("년도", list(range(2022, 2028)),
                                             index=list(range(2022, 2028)).index(now.year),
                                             key="view_year")
                with col2:
                    view_month = st.selectbox("월", list(range(1, 13)),
                                              index=now.month - 1,
                                              key="view_month")

                first_day = f"{view_year}-{view_month:02d}-01"
                last_day  = f"{view_year}-{view_month:02d}-{cal_module.monthrange(view_year, view_month)[1]:02d}"

                with st.spinner("일정 가져오는 중..."):
                    events = get_events(first_day, last_day, calendar_id=cal_id)

                if not events:
                    st.info(f"{view_year}년 {view_month}월 일정이 없습니다.")
                else:
                    rows = []
                    for e in events:
                        start = e.get("start", {}).get("dateTime", e.get("start", {}).get("date", ""))
                        end   = e.get("end",   {}).get("dateTime", e.get("end",   {}).get("date", ""))
                        rows.append({
                            "날짜":  start[:10] if start else "",
                            "시작": start[11:16] if len(start) > 10 else "",
                            "종료": end[11:16]   if len(end)   > 10 else "",
                            "제목": e.get("summary", ""),
                            "장소": e.get("location", ""),
                        })
                    month_df = pd.DataFrame(rows)
                    st.markdown(f"#### {view_year}년 {view_month}월 — {len(rows)}건")
                    st.dataframe(month_df, use_container_width=True, height=500)
