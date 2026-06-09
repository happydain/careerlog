import io
import pandas as pd
import streamlit as st
from datetime import datetime

from config import COLUMNS, AGENCY_OPTIONS, LOCATION_OPTIONS
from utils import calc_hours, calc_fee, get_column_config

from gsheet import (
    append_to_gsheet, load_gsheet_raw, load_gsheet_final,
    save_gsheet_final, append_evidence_to_sheet, replace_gsheet
)

from parsers import (
    parse_kakao_text, parse_seoul_kakao, parse_hanahn_kakao,
    parse_suwon_excel, parse_suwon2_excel, parse_jungdae_excel,
    parse_incheon_excel, parse_incheon_kakao,
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
    "🏠 대시보드",
    "📥 보건스케줄 입력",
    "🗓️ 강사 매칭 시스템",
    "📊 강의 현황",
    "👨‍🏫 강사별 대시보드",
]
menu = st.sidebar.radio("메뉴 선택", menu_options, index=menu_options.index(default_menu))
st.title("📅 보건스케줄 자동정리")

# ══════════════════════════════════════════════
# 🏠 대시보드
# ══════════════════════════════════════════════

if menu == "🏠 대시보드":
    from streamlit_calendar import calendar as st_calendar
    
    st.header("🏠 대시보드")
    st.info("""
    📌 **한눈에 보는 월별 스케줄**
    - 📅 월별 강의 일정을 캘린더로 확인
    - 👤 강사별 색상으로 한눈에 파악
    - ✏️ 날짜 클릭 → 강사변경 / 날짜변경 / 취소 등 즉시 반영
    - 📊 하단에서 해당 월 강의 건수 / 시수 / 강의료 집계 확인
    """)
    st.divider()
    now = datetime.now()
    df  = load_gsheet_final()

    if not df.empty:
        df = df[df["상태"] != "취소"]  # ← fdf 만들기 전에 취소 제거
    fdf = df.copy()
    

    # ── 년/월 선택 + 필터 ──
    col_y, col_m, col_a, col_i = st.columns(4)
    with col_y:
        cal_year = st.selectbox("년도", list(range(2022, 2028)),
                                index=list(range(2022, 2028)).index(now.year),
                                key="cal_year_sel")
    with col_m:
        cal_month = st.selectbox("월", list(range(1, 13)),
                                 index=now.month - 1,
                                 key="cal_month_sel")
    with col_a:
        agency_f = st.selectbox("의뢰기관", ["전체"] + (sorted(df["의뢰기관"].dropna().unique().tolist()) if not df.empty else []), key="cal_agency")
    with col_i:
        instr_f = st.selectbox("강사님", ["전체"] + (sorted(df["강사님"].dropna().unique().tolist()) if not df.empty else []), key="cal_instr")

    fdf = df.copy() if not df.empty else pd.DataFrame()
    if not fdf.empty:
        if agency_f != "전체": fdf = fdf[fdf["의뢰기관"] == agency_f]
        if instr_f  != "전체": fdf = fdf[fdf["강사님"]   == instr_f]

    # ── 강사 색상 ──
    INSTRUCTOR_COLORS = {
        "송주영": "#54A0FF",
        "문하나":  "#5F27CD",
        "김미림":  "#00D2D3",
        "노미영":  "#FF9F43",
        "이다인":  "#FF6B6B",
        "여길매":  "#1DD1A1",
        "이순영":  "#FF9FF3",
    }

    # ── 범례 ──
    legend_html = " ".join([
        f'<span style="background:{c}; color:white; padding:2px 10px; border-radius:12px; font-size:12px; margin-right:4px;">{n}</span>'
        for n, c in INSTRUCTOR_COLORS.items()
    ])
    st.markdown(legend_html + '<span style="background:#888; color:white; padding:2px 10px; border-radius:12px; font-size:12px;">미배정</span>', unsafe_allow_html=True)
    st.divider()

    # ── 이벤트 생성 ──
    events = []
    if not fdf.empty:
        for _, row in fdf.iterrows():
            try:
                date       = str(row["강의일시"])[:10]
                start_time = str(row["시작"]) if str(row["시작"]) not in ("", "nan") else "09:00"
                end_time   = str(row["종료"]) if str(row["종료"]) not in ("", "nan") else "11:00"
                instructor = str(row["강사님"]) if str(row["강사님"]) not in ("", "nan") else "미배정"
                status     = str(row.get("상태", "정상"))
                location   = str(row["방식/위치"]) if str(row["방식/위치"]) not in ("", "nan") else ""
                color      = INSTRUCTOR_COLORS.get(instructor, "#888")
                if status == "취소": 
                    continue

                start_h     = start_time[:2].lstrip("0") or "0"
                end_h       = end_time[:2].lstrip("0") or "0"
                instr_short = instructor[1:] if instructor != "미배정" else "미배정"
                outco = str(row.get("출강기업", "")) if str(row.get("출강기업", "")) not in ("", "nan") else ""
                agency_str = f"{row['의뢰기관']}_{outco}" if outco else str(row['의뢰기관'])
                title = f"{start_h}-{end_h} {instr_short} | {agency_str} | {location} | {row['과정명']}"

                events.append({
                    "title": title,
                    "start": f"{date}T{start_time}",
                    "end":   f"{date}T{end_time}",
                    "backgroundColor": color,
                    "borderColor": color,
                    "extendedProps": {
                        "강사님":   instructor,
                        "의뢰기관": str(row["의뢰기관"]),
                        "과정명":   str(row["과정명"]),
                        "방식위치": location,
                        "상태":     status,
                    }
                })
            except Exception as e:
                st.write(f"오류: {e}, row: {row.get('의뢰기관', '')}")
                pass

    # ── 캘린더 옵션 ──
    calendar_options = {
        "headerToolbar": {
            "left":   "prev,next today",
            "center": "title",
            "right":  "dayGridMonth,timeGridWeek,listMonth"
        },
        "initialView":  "dayGridMonth",
        "initialDate":  f"{cal_year}-{cal_month:02d}-01",
        "locale":       "ko",
        "height":       700,
        "selectable":   True,
        "editable":     False,
        "eventDisplay": "block",
        "dayMaxEvents": False,
        "displayEventTime": False,
        "eventTextColor": "white",
    }

    custom_css = """
        .fc-event-title {
            font-size: 10px !important;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
    """

    # ── 캘린더 + 날짜 상세 ──
    col_cal, col_detail = st.columns([3, 1])
    

    with col_cal:
        cal_result = st_calendar(
            events=events,
            options=calendar_options,
            custom_css=custom_css,
            key=f"main_calendar_{cal_year}_{cal_month}"  # ← 이렇게 되어 있나요?
        )

    with col_detail:
        if cal_result and cal_result.get("dateClick"):
            clicked = cal_result["dateClick"]["date"]  # 전체 문자열
            clicked_dt = pd.to_datetime(clicked, utc=True).tz_convert("Asia/Seoul")
            st.session_state["selected_date"] = clicked_dt.strftime("%Y-%m-%d")
        if st.session_state.get("selected_date") and not fdf.empty:
            sel_date = st.session_state["selected_date"]
            day_df   = fdf[fdf["강의일시"].astype(str).str[:10] == sel_date]

            st.markdown(f"#### 📅 {sel_date}")
            if not day_df.empty:
                for instructor, idf in day_df.groupby("강사님"):
                    st.markdown(f"**{instructor}**")
                    for _, row in idf.sort_values("시작").iterrows():
                        start_h = str(row["시작"])[:2].lstrip("0") or "0"
                        end_h   = str(row["종료"])[:2].lstrip("0") or "0"
                        st.markdown(f"**{start_h}-{end_h}** {row['의뢰기관']} {row['방식/위치']} {row['과정명']}")

                        with st.expander("✏️ 변경/취소"):
                            change_type = st.selectbox(
                                "변경 유형",
                                ["강사변경", "날짜변경", "과목변경", "장소변경", "취소"],
                                key=f"type_{row.name}"
                            )

                            if change_type == "강사변경":
                                new_val = st.selectbox("새 강사", list(INSTRUCTOR_COLORS.keys()), key=f"val_{row.name}")
                            elif change_type == "날짜변경":
                                new_val = st.date_input("새 날짜", key=f"val_{row.name}")
                            elif change_type == "과목변경":
                                new_val = st.text_input("새 과목명", key=f"val_{row.name}")
                            elif change_type == "장소변경":
                                new_val = st.selectbox("새 장소", LOCATION_OPTIONS, key=f"val_{row.name}")
                            elif change_type == "취소":
                                new_val = "취소"
                                st.caption("해당 강의를 취소 처리합니다.")

                            st.divider()
                            change_date = st.date_input("변경일", value=now.date(), key=f"date_{row.name}")
                            modifier    = st.text_input("변경인", placeholder="이름 입력", key=f"mod_{row.name}")
                            reason      = st.text_input("관련 근거", placeholder="예: 강사 일정 충돌", key=f"reason_{row.name}")

                            if st.button("💾 저장", key=f"save_{row.name}"):
                                full_df = load_gsheet_final()
                                today_str = change_date.strftime("%Y-%m-%d")

                                col_map = {
                                    "강사변경": "강사님",
                                    "날짜변경": "강의일시",
                                    "과목변경": "과정명",
                                    "장소변경": "방식/위치",
                                    "취소":     "상태",
                                }
                                target_col = col_map[change_type]
                                full_df.loc[row.name, target_col]   = str(new_val)
                                full_df.loc[row.name, "상태"]       = change_type
                                full_df.loc[row.name, "변경일자"]   = today_str
                                full_df.loc[row.name, "변경의뢰인"] = modifier or "미입력"

                                existing = str(full_df.loc[row.name, "변경이력"]).strip()
                                new_hist = f"[{today_str}] {change_type}: {new_val} / 근거: {reason or '없음'} / 변경인: {modifier or '미입력'}"
                                full_df.loc[row.name, "변경이력"] = f"{existing} / {new_hist}".strip(" /")

                                if save_gsheet_final(full_df):
                                    st.success("✅ 저장 완료!")
                                    st.cache_data.clear()  # ← 캐시 클리어
                                    st.rerun()

                    st.divider()
            else:
                st.info("강의 없음")
        else:
            st.caption("날짜를 클릭하면 상세 일정이 표시됩니다.")

    # ── 월별 현황 ──
    st.divider()
    st.markdown(f"### {cal_year}년 {cal_month}월 현황")

    total_count = total_hours = total_fee = 0
    if not df.empty:
        df["_dt"] = pd.to_datetime(df["강의일시"], errors="coerce")
        this_month = df[
            (df["_dt"].dt.year  == cal_year) &
            (df["_dt"].dt.month == cal_month) &
            (df["상태"] != "취소")  # ← 추가
        ]
        total_count = len(this_month)
        total_hours = pd.to_numeric(this_month["시수"], errors="coerce").sum()
        total_fee   = pd.to_numeric(this_month["강의료(1일)"], errors="coerce").sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("강의 건수", f"{total_count}건")
    c2.metric("총 시수",   f"{total_hours:.0f}시간")
    c3.metric("총 강의료", f"₩{total_fee:,.0f}")
    
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
        common_method = st.selectbox("의뢰방법", ["카카오톡+엑셀", "카카오톡", "이메일", "전화", "문자", "기타"])

    request_date_str = common_date.strftime("%Y-%m-%d")
    st.info(f"📌 **{common_agency}** · {common_requester or '의뢰인 미입력'} · {common_date.strftime('%Y/%m/%d')}")
    st.divider()

   # ── 3단 입력 ──────────────────────────────
    col_excel, col_kakao, col_image = st.columns(3)

    with col_excel:
        st.markdown("### 📄 엑셀")
        uploaded_file = st.file_uploader("엑셀 파일 (.xlsx)", type=["xlsx"])

        if uploaded_file:
            if st.button("📄 변환"):
                if not common_requester.strip() and not st.session_state.get("is_bulk_upload"):
                    st.error("담당자 이름을 입력해주세요.")
                else:
                    try:
                        if common_agency == "인천대한협":
                            df_excel = parse_incheon_excel(uploaded_file, common_agency,
                                                           common_requester, request_date_str,
                                                           request_method=common_method)
                        elif common_agency == "중대협":
                            df_excel = parse_jungdae_excel(uploaded_file, common_requester,
                                                           request_date_str, year)
                            df_excel["의뢰방법"] = common_method
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
                            st.success(f"✅ {len(df_excel)}건")
                    except Exception as e:
                        st.error(f"오류: {e}")


    with col_kakao:
        st.markdown("### 💬 카톡 / 이메일")
        raw_text = st.text_area("메시지를 붙여넣으세요.", height=200, key="raw_text_input")

        if st.button("🪄 분석"):
            if not common_requester.strip():
                st.error("담당자 이름을 입력해주세요.")
            elif not raw_text.strip():
                st.warning("텍스트를 입력해주세요.")
            else:
                if common_agency == "서울대한협":
                    df_text = parse_seoul_kakao(raw_text, year, common_requester, request_date_str)
                elif common_agency == "한안협":
                    df_text = parse_hanahn_kakao(raw_text, year, common_requester, request_date_str, common_method)
                elif common_agency == "인천대한협":
                    df_text = parse_incheon_kakao(raw_text, year, common_requester, request_date_str, request_method=common_method)
                else:
                    df_text = parse_kakao_text(raw_text, year)
                    df_text["의뢰기관"] = common_agency
                    df_text["의뢰인"] = common_requester
                    df_text["의뢰일"] = request_date_str
                    df_text["의뢰방법"] = common_method

                if df_text.empty:
                    st.warning("날짜를 찾지 못했습니다.")
                else:
                    st.session_state["temp_df"] = df_text
                    st.session_state["raw_text_for_drive"] = raw_text
                    st.session_state.pop("excel_file_for_drive", None)
                    st.success(f"✅ {len(df_text)}건")

    with col_image:
        st.markdown("### 🖼️ 이미지")
        img_file = st.file_uploader("이미지 파일", type=["png", "jpg", "jpeg"], key="img_upload")

        if img_file:
            if st.button("🪄 이미지 분석", key="img_analyze"):
                from parsers.image_parser import parse_image_schedule
                with st.spinner("분석 중..."):
                    try:
                        extracted = parse_image_schedule(img_file)
                        st.text_area("추출된 텍스트", extracted, height=100, key="extracted_text")
                        if common_agency == "인천대한협":
                            df_img = parse_incheon_kakao(extracted, year, common_requester,
                                                         request_date_str, request_method=common_method)
                        else:
                            df_img = parse_kakao_text(extracted, year)
                            df_img["의뢰기관"] = common_agency
                            df_img["의뢰인"] = common_requester
                            df_img["의뢰일"] = request_date_str
                            df_img["의뢰방법"] = common_method

                        if not df_img.empty:
                            st.session_state["temp_df"] = df_img
                            st.session_state["raw_text_for_drive"] = extracted
                            st.success(f"✅ {len(df_img)}건")
                        else:
                            st.warning("일정을 찾지 못했습니다.")
                    except Exception as e:
                        st.error(f"오류: {e}")

    st.divider()
    st.markdown("### 📂 전체 스케줄 일괄 가져오기")
    st.caption("월별 시트가 있는 엑셀 파일을 업로드하세요.")
    uploaded_bulk = st.file_uploader("월별 시트 엑셀", type=["xlsx"], key="bulk_upload")
    if uploaded_bulk:
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            if st.button("📥 일괄 변환", key="bulk_btn"):
                from import_schedule import parse_all_sheets
                with st.spinner("파싱 중..."):
                    df_bulk = parse_all_sheets(uploaded_bulk)
                    st.session_state["temp_df"] = df_bulk
                    st.session_state["is_bulk_upload"] = True
                    st.success(f"✅ {len(df_bulk)}건 로드 완료!")
                    st.rerun()
        with col_b2:
            if st.button("🔍 미리보기", key="bulk_preview"):
                uploaded_bulk.seek(0)
                df_preview = pd.read_excel(uploaded_bulk, sheet_name=0, header=None)
                st.dataframe(df_preview, use_container_width=True, height=200)
    st.divider()

    # ── 증빙 파일 ────────────────────────────
    st.markdown("### 📎 증빙 파일")
    st.info("💡 저장 후 생성된 드라이브 폴더 링크를 클릭해서 파일을 직접 업로드하세요.")
    st.warning("""
    ⚠️ **자동 파일 업로드 기능 준비 중**
    현재 서비스 계정 구글 드라이브 용량 제한으로 파일 자동 업로드가 제한됩니다.
    추후 업데이트 예정이며, 현재는 드라이브 폴더에 직접 업로드해 주세요.
    """)

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
            if st.button("✅ 전체 추가", key="add_all_locations"):
                for loc in unknown_locations:
                    if loc not in LOCATION_OPTIONS:
                        LOCATION_OPTIONS.append(loc)
                st.success(f"✅ {len(unknown_locations)}개 추가됨!")
                st.rerun()

        st.divider()
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("💾 저장", key="save_btn"):

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
                        evidence_files = []

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

                        if st.session_state.get("is_bulk_upload"):
                            from gsheet import replace_gsheet_final
                            result = replace_gsheet_final(edited_df)
                            st.session_state.pop("is_bulk_upload", None)
                        else:
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
# 🗓️ 강사 매칭 시스템
# ══════════════════════════════════════════════
elif menu == "🗓️ 강사 매칭 시스템":
    from matching_engine import auto_match, check_overload
    from config import INSTRUCTOR_CONFIG

    st.header("🤖 강사 매칭 시스템")
    st.info("월별 미배정 강의에 강사를 자동 매칭합니다. 원티드 강사, 기관 우선순위, 한도를 고려해 배정합니다.")

    df = load_gsheet_final()

    if df.empty:
        st.info("저장된 데이터가 없습니다.")
    else:
        now = datetime.now()

        # ── 년도/월 선택 ──
        col1, col2 = st.columns(2)
        with col1:
            sel_year = st.selectbox("년도", list(range(2022, 2028)),
                                    index=list(range(2022, 2028)).index(now.year),
                                    key="ms_year")
        with col2:
            sel_month = st.selectbox("월", list(range(1, 13)),
                                     index=now.month - 1,
                                     key="ms_month")

        # ── 해당 월 데이터 ──
        df["_dt"] = pd.to_datetime(df["강의일시"], errors="coerce")
        fdf = df[
            (df["_dt"].dt.year  == sel_year) &
            (df["_dt"].dt.month == sel_month)
        ].drop(columns=["_dt"]).copy()

        if fdf.empty:
            st.info(f"{sel_year}년 {sel_month}월 데이터가 없습니다.")
        else:
            # ── 강사 설정 현황 ──
            st.markdown("### ⚙️ 강사 설정")
            cfg_rows = []
            for name, cfg in INSTRUCTOR_CONFIG.items():
                used = pd.to_numeric(
                    df[
                        (df["강사님"] == name) &
                        (pd.to_datetime(df["강의일시"], errors="coerce").dt.year == sel_year) &
                        (pd.to_datetime(df["강의일시"], errors="coerce").dt.month == sel_month)
                    ]["시수"], errors="coerce"
                ).sum()
                limit = cfg.get("limit")
                cfg_rows.append({
                    "강사":     name,
                    "줌 가능":  "✅" if cfg.get("zoom") else "❌",
                    "오전만":   "✅" if cfg.get("morning_only") else "❌",
                    "선호기관": ", ".join(cfg.get("preferred_agency", [])) or "전체",
                    "한도(시수)": f"{limit}h" if limit else "무제한",
                    "이번달 사용": f"{used:.0f}h",
                    "남은 한도":  f"{limit - used:.0f}h" if limit else "무제한",
                    "백업":     "✅" if cfg.get("backup") else "",
                })
            st.dataframe(pd.DataFrame(cfg_rows), use_container_width=True, hide_index=True)

            st.divider()

            # ── 미배정 현황 ──
            unassigned = fdf[fdf["강사님"].astype(str).str.strip().isin(["", "nan"])]
            assigned   = fdf[~fdf["강사님"].astype(str).str.strip().isin(["", "nan"])]

            col_a, col_b = st.columns(2)
            col_a.metric("미배정", f"{len(unassigned)}건")
            col_b.metric("배정완료", f"{len(assigned)}건")

            # ── 한도 초과 경고 ──
            overloads = check_overload(df, sel_year, sel_month)
            if overloads:
                for name, info in overloads.items():
                    st.warning(f"⚠️ **{name}** 한도 초과! 사용 {info['used']:.0f}h / 한도 {info['limit']}h (초과 {info['over']:.0f}h)")

            st.divider()

            # ── 자동매칭 ──
            st.markdown("### 🤖 자동 매칭")
            
            col_btn1, col_btn2 = st.columns(2)
            
            with col_btn1:
                if st.button("📅 캘린더 원티드 반영", key="cal_wanted"):
                    from gcalendar import get_events
                    from config import INSTRUCTOR_CALENDARS
                    from matching_engine import apply_calendar_wanted
                    import calendar as cal_module
            
                    with st.spinner("캘린더 읽는 중..."):
                        first_day = f"{sel_year}-{sel_month:02d}-01"
                        last_day  = f"{sel_year}-{sel_month:02d}-{cal_module.monthrange(sel_year, sel_month)[1]:02d}"
            
                        events_by_instructor = {}
                        for instructor, cal_id in INSTRUCTOR_CALENDARS.items():
                            if not cal_id:
                                continue
                            events = get_events(first_day, last_day, calendar_id=cal_id)
                            events_by_instructor[instructor] = [
                                {
                                    "date":  e.get("start", {}).get("dateTime", e.get("start", {}).get("date", ""))[:10],
                                    "start": e.get("start", {}).get("dateTime", "")[11:16] if e.get("start", {}).get("dateTime") else "",
                                    "title": e.get("summary", ""),
                                }
                                for e in events
                            ]
            
                        result, applied, log = apply_calendar_wanted(fdf, events_by_instructor)
                        if applied > 0:
                            st.session_state["matched_df"] = result
                            st.session_state["wanted_log"] = log
                            st.success(f"✅ 원티드 {applied}건 반영!")
                            # st.rerun() 제거
                        else:
                            st.info("이번달 원티드 일정이 없습니다.")
                        
                        # ← 여기 아래에 추가
                        if st.session_state.get("wanted_log"):
                            st.markdown("**원티드 반영 내역:**")
                            for l in st.session_state["wanted_log"]:
                                st.caption(l)
            
            with col_btn2:
                if st.button("🤖 미배정 강의 자동매칭", key="auto_match_engine"):
                    with st.spinner("매칭 중..."):
                        matched_df, changed = auto_match(fdf, sel_year, sel_month)
                        st.session_state["matched_df"] = matched_df
                        st.success(f"✅ {changed}건 자동 배정 완료!")
                        st.rerun()

            # ── 매칭 결과 편집 ──
            if "matched_df" in st.session_state:
                fdf = st.session_state["matched_df"]

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

            # ── 저장 ──
            col_s1, col_s2 = st.columns([2, 4])
            with col_s1:
                modifier = st.text_input("변경자", placeholder="이름 입력", key="ms_modifier")
            with col_s2:
                if st.button("💾 저장", key="ms_save"):
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

                    df.update(edited_fdf)
                    if save_gsheet_final(df):
                        st.success("✅ 저장 완료!")
                        st.session_state.pop("matched_df", None)
                        st.rerun()


# ══════════════════════════════════════════════
# 📊 강의 현황
# ══════════════════════════════════════════════
elif menu == "📊 강의 현황":
    st.header("📊 강의 현황")

    df = load_gsheet_final()

    if not df.empty and "상태" in df.columns:
        df_active = df[df["상태"] != "취소"].copy()
    else:
        df_active = df.copy()

    # ── 헬퍼: 통계 카드 ──
    def stat_cards(data_df, prefix=""):
        if data_df.empty:
            return ""
        cnt  = len(data_df)
        hrs  = pd.to_numeric(data_df["시수"], errors="coerce").sum()
        fee  = pd.to_numeric(data_df["강의료(1일)"], errors="coerce").sum()
        days = data_df["강의일시"].astype(str).str[:10].nunique()
        avg_daily = fee / days if days > 0 else 0
        hourly    = fee / hrs if hrs > 0 else 0
        return f"""
        <div style="display:flex; gap:12px; margin:8px 0 16px;">
            <div style="background:#f0f4ff; border-radius:10px; padding:12px 18px; text-align:center; flex:1;">
                <div style="font-size:11px; color:#666;">{prefix}강의 건수</div>
                <div style="font-size:20px; font-weight:bold; color:#1a56db;">{cnt}건</div>
            </div>
            <div style="background:#f0fff4; border-radius:10px; padding:12px 18px; text-align:center; flex:1;">
                <div style="font-size:11px; color:#666;">{prefix}총 시수</div>
                <div style="font-size:20px; font-weight:bold; color:#0e9f6e;">{hrs:.0f}시간</div>
            </div>
            <div style="background:#fff8f0; border-radius:10px; padding:12px 18px; text-align:center; flex:1;">
                <div style="font-size:11px; color:#666;">{prefix}총 강의료</div>
                <div style="font-size:20px; font-weight:bold; color:#e3a008;">₩{fee:,.0f}</div>
            </div>
            <div style="background:#fdf0ff; border-radius:10px; padding:12px 18px; text-align:center; flex:1;">
                <div style="font-size:11px; color:#666;">{prefix}참여일</div>
                <div style="font-size:20px; font-weight:bold; color:#7c3aed;">{days}일</div>
            </div>
            <div style="background:#fff0f0; border-radius:10px; padding:12px 18px; text-align:center; flex:1;">
                <div style="font-size:11px; color:#666;">{prefix}일당</div>
                <div style="font-size:20px; font-weight:bold; color:#e02424;">₩{avg_daily:,.0f}</div>
            </div>
            <div style="background:#f0f9ff; border-radius:10px; padding:12px 18px; text-align:center; flex:1;">
                <div style="font-size:11px; color:#666;">{prefix}시간당</div>
                <div style="font-size:20px; font-weight:bold; color:#0369a1;">₩{hourly:,.0f}</div>
            </div>
        </div>
        """

    def month_buttons(key_prefix, sel_key):
        cols = st.columns(12)
        for i, mo in enumerate(range(1, 13)):
            with cols[i]:
                is_sel = st.session_state.get(sel_key) == mo
                if st.button(f"{mo}월", key=f"{key_prefix}_{mo}",
                             use_container_width=True,
                             type="primary" if is_sel else "secondary"):
                    st.session_state[sel_key] = mo if not is_sel else None
                    st.rerun()

    # ── 버튼 스타일 ──
    st.markdown("""
    <style>
    div[data-testid="column"] button {
        padding: 3px 4px !important; font-size: 12px !important;
        min-height: 28px !important; height: 28px !important;
        border-radius: 6px !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # ══════════════════════════════════
    # 년도 선택
    # ══════════════════════════════════
    now = datetime.now()
    available_years = sorted(
        [y for y in df_active["강의일시"].str[:4].dropna().unique().tolist() if str(y).isdigit()],
        reverse=True
    ) if not df_active.empty else [str(now.year)]

    col_yr, _ = st.columns([1, 5])
    with col_yr:
        selected_year = st.selectbox("", available_years, index=0, key="match_year_sel",
                                     label_visibility="collapsed")
    sel_year = int(selected_year)
    st.markdown(f"<div style='font-size:32px; font-weight:500; color:var(--color-text-primary); margin-bottom:4px;'>{sel_year}</div>", unsafe_allow_html=True)

    # ── 연간 통계 ──
    if not df_active.empty:
        df_active["_dt"] = pd.to_datetime(df_active["강의일시"], errors="coerce")
        df_year   = df_active[df_active["_dt"].dt.year == sel_year].copy()
        df_active = df_active.drop(columns=["_dt"])
        st.markdown(stat_cards(df_year, f"{sel_year}년 "), unsafe_allow_html=True)
    else:
        df_year = pd.DataFrame()

    # ══════════════════════════════════
    # 월별 현황
    # ══════════════════════════════════
    st.markdown("### 월별 현황")
    col_all, _ = st.columns([1, 11])
    with col_all:
        if st.button("전체", key="month_all",
                     type="primary" if not st.session_state.get("sel_month") else "secondary"):
            st.session_state["sel_month"] = None
            st.rerun()
    
    month_buttons("mon", "sel_month")

    sel_month = st.session_state.get("sel_month")
    if sel_month and not df_active.empty:
        df_active["_dt"] = pd.to_datetime(df_active["강의일시"], errors="coerce")
        m_df = df_active[
            (df_active["_dt"].dt.year == sel_year) &
            (df_active["_dt"].dt.month == sel_month)
        ].copy()
        df_active = df_active.drop(columns=["_dt"])
        st.markdown(f"**{sel_month}월 통계**")
        st.markdown(stat_cards(m_df), unsafe_allow_html=True)

    # ══════════════════════════════════
    # 강사별 현황
    # ══════════════════════════════════
    st.divider()
    st.markdown("### 강사별 현황")

    if not df_active.empty:
        instructors = sorted([i for i in df_active["강사님"].dropna().unique().tolist()
                              if str(i).strip() and str(i) != "nan"])
        instr_cols = st.columns(len(instructors) + 1)
        with instr_cols[0]:
            if st.button("전체", key="instr_all",
                         type="primary" if not st.session_state.get("sel_instructor") else "secondary"):
                st.session_state["sel_instructor"]       = None
                st.session_state["sel_instructor_month"] = None
                st.rerun()
        for i, instr in enumerate(instructors):
            with instr_cols[i + 1]:
                sel_i = st.session_state.get("sel_instructor") == instr
                if st.button(instr, key=f"instr_{instr}",
                             type="primary" if sel_i else "secondary"):
                    st.session_state["sel_instructor"]       = instr
                    st.session_state["sel_instructor_month"] = None
                    st.rerun()

    sel_instructor = st.session_state.get("sel_instructor")
    if sel_instructor and not df_active.empty:
        df_active["_dt"] = pd.to_datetime(df_active["강의일시"], errors="coerce")
        i_df = df_active[
            (df_active["_dt"].dt.year == sel_year) &
            (df_active["강사님"] == sel_instructor)
        ].copy()
        df_active = df_active.drop(columns=["_dt"])
        st.markdown(f"**👤 {sel_instructor} — {sel_year}년 전체**")
        st.markdown(stat_cards(i_df), unsafe_allow_html=True)

        st.caption("월별 상세")
        month_buttons("imon", "sel_instructor_month")

        sel_i_month = st.session_state.get("sel_instructor_month")
        if sel_i_month and not df_active.empty:
            df_active["_dt"] = pd.to_datetime(df_active["강의일시"], errors="coerce")
            im_df = df_active[
                (df_active["_dt"].dt.year == sel_year) &
                (df_active["강사님"] == sel_instructor) &
                (df_active["_dt"].dt.month == sel_i_month)
            ].copy()
            df_active = df_active.drop(columns=["_dt"])
            st.markdown(f"**👤 {sel_instructor} — {sel_i_month}월**")
            st.markdown(stat_cards(im_df), unsafe_allow_html=True)

    # ══════════════════════════════════
    # 의뢰기관별 현황
    # ══════════════════════════════════
    st.divider()
    st.markdown("### 의뢰기관별 현황")

    if not df_active.empty:
        agencies = sorted(df_active["의뢰기관"].dropna().unique().tolist())
        agency_cols = st.columns(len(agencies) + 1)
        with agency_cols[0]:
            if st.button("전체", key="agency_all",
                         type="primary" if not st.session_state.get("sel_agency") else "secondary"):
                st.session_state["sel_agency"]       = None
                st.session_state["sel_agency_month"] = None
                st.rerun()
        for i, agency in enumerate(agencies):
            with agency_cols[i + 1]:
                sel_a = st.session_state.get("sel_agency") == agency
                if st.button(agency, key=f"agency_{agency}",
                             type="primary" if sel_a else "secondary"):
                    st.session_state["sel_agency"]       = agency
                    st.session_state["sel_agency_month"] = None
                    st.rerun()

    sel_agency = st.session_state.get("sel_agency")
    if sel_agency and not df_active.empty:
        df_active["_dt"] = pd.to_datetime(df_active["강의일시"], errors="coerce")
        a_df = df_active[
            (df_active["_dt"].dt.year == sel_year) &
            (df_active["의뢰기관"] == sel_agency)
        ].copy()
        df_active = df_active.drop(columns=["_dt"])
        st.markdown(f"**🏢 {sel_agency} — {sel_year}년 전체**")
        st.markdown(stat_cards(a_df), unsafe_allow_html=True)

        st.caption("월별 상세")
        month_buttons("amon", "sel_agency_month")

        sel_a_month = st.session_state.get("sel_agency_month")
        if sel_a_month and not df_active.empty:
            df_active["_dt"] = pd.to_datetime(df_active["강의일시"], errors="coerce")
            am_df = df_active[
                (df_active["_dt"].dt.year == sel_year) &
                (df_active["의뢰기관"] == sel_agency) &
                (df_active["_dt"].dt.month == sel_a_month)
            ].copy()
            df_active = df_active.drop(columns=["_dt"])
            st.markdown(f"**🏢 {sel_agency} — {sel_a_month}월**")
            st.markdown(stat_cards(am_df), unsafe_allow_html=True)

    # ══════════════════════════════════
    # 데이터프레임 (읽기 전용)
    # ══════════════════════════════════
    st.divider()
    st.markdown("#### 📋 강의 데이터")

    if not df.empty:
        df["_dt"] = pd.to_datetime(df["강의일시"], errors="coerce")
        view_df = df[df["_dt"].dt.year == sel_year].drop(columns=["_dt"]).copy()

        if sel_instructor:
            view_df = view_df[view_df["강사님"] == sel_instructor]
        if sel_agency:
            view_df = view_df[view_df["의뢰기관"] == sel_agency]

        final_month = (
            st.session_state.get("sel_instructor_month") or
            st.session_state.get("sel_agency_month") or
            sel_month
        )
        if final_month:
            view_df["_dt2"] = pd.to_datetime(view_df["강의일시"], errors="coerce")
            view_df = view_df[view_df["_dt2"].dt.month == final_month].drop(columns=["_dt2"])

        try:
            view_df["강의일시"] = pd.to_datetime(view_df["강의일시"], errors="coerce").dt.date
        except Exception:
            pass

        st.dataframe(view_df, use_container_width=True, height=400,
                     column_config=get_column_config())

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
