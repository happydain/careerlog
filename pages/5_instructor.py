import pandas as pd
import streamlit as st

from utils import get_column_config
from gsheet import load_gsheet_final

st.title("👨‍🏫 강사별 대시보드")
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
