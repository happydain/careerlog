import streamlit as st

st.set_page_config(page_title="보건스케줄", page_icon="📅", layout="wide")
st.sidebar.title("📅 CareerLog")

menu = st.sidebar.radio("메뉴 선택", [
    "📥 보건스케줄 입력",
    "📋 의뢰일별 스케줄",
    "📅 최종 스케줄",
    "📊 협회별 월별",
    "👨‍🏫 강사별 대시보드",
])


if menu == "📥 보건스케줄 입력":
    st.switch_page("pages/2_raw_schedule.py")
elif menu == "📋 의뢰일별 스케줄":
    st.switch_page("pages/3_final_schedule.py")
elif menu == "📅 최종 스케줄":
    st.switch_page("pages/4_monthly_stats.py")
elif menu == "📊 협회별 월별":
    st.switch_page("pages/5_instructor.py")

st.switch_page("pages/1_input.py")
