import pandas as pd
import streamlit as st
from datetime import datetime

from config import COLUMNS
from utils import get_column_config
from gsheet import load_gsheet_raw, save_gsheet_raw
from gdrive import append_change_log

st.title("📋 의뢰일별 스케줄")
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

    original_fdf = fdf.copy()

    edited_raw_df = st.data_editor(
        fdf,
        use_container_width=True,
        height=700,
        num_rows="fixed",
        column_config=get_column_config(),
    )

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
                summary = ", ".join(changes)
                existing = str(edited_raw_df.loc[idx, "내부메모"]).strip()
                history  = f"[{today}] {summary}"
                edited_raw_df.loc[idx, "내부메모"] = f"{existing} / {history}".strip(" /")

                # 드라이브 변경이력 기록
                folder_url = str(edited_raw_df.loc[idx, "증빙폴더"])
                if folder_url.startswith("https://drive.google.com"):
                    try:
                        folder_id = folder_url.split("/")[-1]
                        append_change_log(folder_id, summary, "직접입력")
                    except Exception:
                        pass

        df.update(edited_raw_df)
        if save_gsheet_raw(df):
            st.success("✅ 저장 완료!")
            st.rerun()
