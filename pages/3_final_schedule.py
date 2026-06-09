import pandas as pd
import streamlit as st
from datetime import datetime

from config import COLUMNS
from utils import get_column_config
from gsheet import load_gsheet_final, save_gsheet_final
from gdrive import append_change_log

st.set_page_config(page_title="최종 스케줄", page_icon="📅", layout="wide")
st.sidebar.title("📅 CareerLog")
st.title("📅 최종 스케줄 (취소, 변경반영)")

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
                    summary  = ", ".join(changes)
                    existing = str(edited_gsheet_df.loc[idx, "변경이력"]).strip()
                    new_hist = f"[{today}] {summary}"
                    edited_gsheet_df.loc[idx, "변경이력"]   = f"{existing} / {new_hist}".strip(" /")
                    edited_gsheet_df.loc[idx, "변경일자"]   = today
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
