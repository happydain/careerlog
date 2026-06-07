import io
import pandas as pd
import streamlit as st
from datetime import datetime

from config import COLUMNS, AGENCY_OPTIONS
from utils import calc_hours, calc_fee, get_column_config

#의뢰별 text,엑셀 분석함수
from parsers import (
    parse_kakao_text, parse_seoul_kakao, parse_hanahn_kakao,
    parse_suwon_excel, parse_jungdae_excel, parse_incheon_excel,
)

from gsheet import append_to_gsheet, load_gsheet_raw, load_gsheet_final, save_gsheet_final

from gdrive import (
    create_careerlog_structure, get_folder_url, append_change_log,
)

# gdrive API를 제어하는 함수가 구현되어 있다고 가정하거나 추가할 내용
from googleapiclient.http import MediaIoBaseUpload

def upload_file_to_folder(file_obj, folder_id):
    """
    Streamlit의 UploadedFile 객체를 구글 드라이브의 특정 folder_id 내부로 업로드합니다.
    """
    # 기존 코드에서 사용하는 drive service 객체를 가져옵니다.
    # 예: service = get_drive_service() 
    
    file_metadata = {
        'name': file_obj.name,
        'parents': [folder_id]
    }
    media = MediaIoBaseUpload(file_obj, mimetype=file_obj.type, resumable=True)
    
    # ⚠️ 아래 'drive_service' 부분은 작성하신 프로젝트의 구글 서비스 객체 변수명에 맞게 매칭해야 합니다.
    # file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    # return file.get('id')

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
        # ── 저장 ──
        with col1:
            if st.button("💾 저장", key="save_btn"):
                if not common_requester.strip():
                    st.error("담당자 이름을 입력해주세요.")
                else:
                    with st.spinner("구글 시트 기록 및 드라이브 파일 업로드 중..."):

                        # [기본 전처리 로직] 요일, 시수, 강의료 자동 계산
                        def auto_weekday(r):
                            try: return ["월","화","수","목","금","토","일"][pd.to_datetime(r["강의일시"]).weekday()]
                            except: return r.get("요일", "")

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
                        uploaded_files_count = 0

                        # 각 행(일정)을 돌면서 폴더 생성 및 파일 업로드
                        for idx in edited_df.index:
                            row = edited_df.loc[idx].to_dict()
                            try:
                                date_str = str(row.get("강의일시", ""))
                                agency   = str(row.get("의뢰기관", common_agency))
                                subject  = str(row.get("과정명", "")).replace(" ", "")
                                yr       = int(date_str[:4]) if len(date_str) >= 4 else year

                                # 1. 구글 드라이브에 해당 일정용 폴더 생성 (기존 함수 활용)
                                # 상위 모듈에서 folder_id를 반환하도록 설계되어 있어야 합니다.
                                folder_id  = create_careerlog_structure(yr, agency, date_str, subject)
                                folder_url = get_folder_url(folder_id)
                                edited_df.loc[idx, "증빙폴더"] = folder_url

                                # 2. 생성된 폴더에 증빙 파일 업로드 수행
                                # 2-1. 화면 상단 '증빙 파일 업로드'에 파일이 여러 개 있는 경우
                                if evidence_files:
                                    for f_obj in evidence_files:
                                        # 중요: 파일 객체는 한 번 읽으면 포인터가 끝으로 가므로 
                                        # 여러 폴더에 순회하며 업로드할 때는 시크(seek) 초기화가 필요할 수 있습니다.
                                        f_obj.seek(0) 
                                        upload_file_to_folder(f_obj, folder_id)
                                        uploaded_files_count += 1
                                
                                # 2-2. 엑셀 업로드 메뉴를 통해 들어온 원본 엑셀 파일도 증빙으로 같이 보관하고 싶다면
                                if st.session_state.get("excel_file_for_drive"):
                                    ex_file = st.session_state["excel_file_for_drive"]
                                    ex_file.seek(0)
                                    upload_file_to_folder(ex_file, folder_id)
                                    uploaded_files_count += 1

                            except Exception as e:
                                drive_errors.append(f"행 {idx}: {e}")

                        # 드라이브 오류와 무관하게 시트는 항상 저장
                        result = append_to_gsheet(edited_df)
                        if result:
                            if drive_errors:
                                st.warning("⚠️ 드라이브 폴더 생성 또는 파일 업로드 일부 실패 (시트는 저장됨):\n" + "\n".join(drive_errors))
                            else:
                                success_msg = "✅ 구글시트 저장 및 드라이브 폴더 생성 완료!"
                                if uploaded_files_count > 0:
                                    success_msg += f" (총 {uploaded_files_count}개의 증빙 파일 업로드 완료)"
                                st.success(success_msg)
                                
                            # 세션 상태 정리 및 페이지 리프레시
                            del st.session_state["temp_df"]
                            st.session_state.pop("raw_text_for_drive", None)
                            st.session_state.pop("excel_file_for_drive", None)
                            st.rerun()
                        else:
                            st.error("❌ 구글시트 저장 실패")
                            if drive_errors:
                                st.warning("드라이브 오류:\n" + "\n".join(drive_errors))

        # ── 엑셀 다운로드 ──
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

        # ── 초기화 ──
        with col3:
            if st.button("🧹 초기화", key="reset_btn"):
                del st.session_state["temp_df"]
                st.session_state.pop("raw_text_for_drive", None)
                st.session_state.pop("excel_file_for_drive", None)
                st.rerun()


# ══════════════════════════════════════════════
# 📋 의뢰일별
# ══════════════════════════════════════════════
elif menu == "📋 의뢰일별 스케줄":
    st.header("📋 의뢰일별 (원본)")
    df = load_gsheet_raw()

    if df.empty:
        st.info("저장된 데이터가 없습니다.")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            agency_f = st.selectbox("의뢰기관", ["전체"] + sorted(df["의뢰기관"].dropna().unique().tolist()))
        with col2:
            instr_f = st.selectbox("강사님", ["전체"] + sorted(df["강사님"].dropna().unique().tolist()))
        with col3:
            subj_f = st.selectbox("과정명", ["전체"] + sorted(df["과정명"].dropna().unique().tolist()))

        fdf = df.copy()
        if agency_f != "전체": fdf = fdf[fdf["의뢰기관"] == agency_f]
        if instr_f  != "전체": fdf = fdf[fdf["강사님"]   == instr_f]
        if subj_f   != "전체": fdf = fdf[fdf["과정명"]   == subj_f]

        st.dataframe(fdf, use_container_width=True, height=700,
                     column_config=get_column_config())


# ══════════════════════════════════════════════
# 📅 최종 스케줄
# ══════════════════════════════════════════════
elif menu == "📅 최종 스케줄(취소,변경반영)":
    st.header("📅 최종 스케줄")
    df = load_gsheet_final()

    if df.empty:
        st.info("저장된 데이터가 없습니다.")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            agency_f = st.selectbox("의뢰기관", ["전체"] + sorted(df["의뢰기관"].dropna().unique().tolist()))
        with col2:
            instr_f = st.selectbox("강사님", ["전체"] + sorted(df["강사님"].dropna().unique().tolist()))
        with col3:
            subj_f = st.selectbox("과정명", ["전체"] + sorted(df["과정명"].dropna().unique().tolist()))

        fdf = df.copy()
        if agency_f != "전체": fdf = fdf[fdf["의뢰기관"] == agency_f]
        if instr_f  != "전체": fdf = fdf[fdf["강사님"]   == instr_f]
        if subj_f   != "전체": fdf = fdf[fdf["과정명"]   == subj_f]

        try:
            fdf["강의일시"] = pd.to_datetime(fdf["강의일시"], errors="coerce").dt.date
        except Exception:
            pass

        original_df = fdf.copy()

        edited_gsheet_df = st.data_editor(
            fdf,
            use_container_width=True,
            height=700,
            num_rows="fixed",
            column_config=get_column_config(),
        )

        col_save, col_modifier = st.columns([2, 2])
        with col_modifier:
            modifier = st.text_input("변경 담당자 이름", placeholder="변경 저장 시 입력")

        with col_save:
            if st.button("💾 변경사항 저장", key="final_save_btn"):
                today = datetime.now().strftime("%Y-%m-%d")
                for idx in edited_gsheet_df.index:
                    changes = []
                    for col in COLUMNS:
                        if col in ("변경이력", "증빙폴더"):
                            continue
                        orig = str(original_df.loc[idx, col]) if idx in original_df.index else ""
                        new  = str(edited_gsheet_df.loc[idx, col])
                        if orig != new:
                            changes.append(f"{col} {orig}→{new}")

                    if changes:
                        summary = ", ".join(changes)
                        existing = str(edited_gsheet_df.loc[idx, "변경이력"]).strip()
                        new_hist = f"[{today}] {summary}"
                        edited_gsheet_df.loc[idx, "변경이력"] = f"{existing} / {new_hist}".strip(" /")
                        edited_gsheet_df.loc[idx, "변경일자"] = today
                        edited_gsheet_df.loc[idx, "변경의뢰인"] = modifier

                        folder_url = str(edited_gsheet_df.loc[idx, "증빙폴더"])
                        if folder_url.startswith("https://drive.google.com"):
                            try:
                                folder_id = folder_url.split("/")[-1]
                                append_change_log(folder_id, summary, modifier or "미입력")
                            except Exception:
                                pass

                df.update(edited_gsheet_df)
                if save_gsheet_final(df):
                    st.success("✅ 변경사항 저장 완료!")
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
    st.header("👨‍🏫 강사별 대시보드")
    df = load_gsheet_final()
    if df.empty:
        st.info("저장된 데이터가 없습니다.")
    elif "강사님" not in df.columns:
        st.warning("강사님 컬럼이 없습니다.")
    else:
        selected = st.selectbox("강사 선택", sorted(df["강사님"].dropna().unique().tolist()))
        idf = df[df["강사님"] == selected].copy()
        st.subheader(f"{selected} 강사 일정")
        st.dataframe(idf, use_container_width=True, height=500,
                     column_config=get_column_config())
        try:
            total_hours = pd.to_numeric(idf["시수"], errors="coerce").sum()
            total_fee   = pd.to_numeric(idf["강의료(1일)"], errors="coerce").sum()
            c1, c2 = st.columns(2)
            c1.metric("총 시수", f"{total_hours:.0f}시간")
            c2.metric("총 강의료", f"₩{total_fee:,.0f}")
        except Exception as e:
            st.error(f"집계 오류: {e}")
