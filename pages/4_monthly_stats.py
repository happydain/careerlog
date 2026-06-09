import pandas as pd
import streamlit as st

from gsheet import load_gsheet_final

st.set_page_config(page_title="협회별 월별 스케줄", page_icon="📊", layout="wide")
st.sidebar.title("📅 CareerLog")
st.title("📊 협회별 월별 스케줄")

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
