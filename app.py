import streamlit as st
from supabase import create_client, Client
from anthropic import Anthropic
import json
import datetime

# 1. 초기 설정 (Secrets 관리 필수)
# Streamlit Cloud 설정에서 해당 키들을 등록해야 합니다.
url: str = st.secrets["SUPABASE_URL"]
key: str = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)
anthropic = Anthropic(api_key=st.secrets["CLAUDE_API_KEY"])

st.set_page_config(page_title="CareerLog AI", layout="wide")

# --- Helper Functions ---

def parse_with_claude(raw_text):
    """Claude API를 사용하여 비정형 텍스트를 JSON으로 변환"""
    prompt = f"""
    당신은 강의 의뢰 전문 비서입니다. 아래 텍스트에서 정보를 추출해 JSON 형식으로만 응답하세요.
    필드: org_name, lecture_date(YYYY-MM-DD), start_time(HH:MM), duration_hours(숫자), location, budget(숫자)
    텍스트: {raw_text}
    """
    response = anthropic.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    # JSON 파싱
    content = response.content[0].text
    return json.loads(content)

def get_recommended_instructors(request_data):
    """DB에서 조건에 맞는 강사 필터링 (간단한 매칭 로직)"""
    # 실제로는 더 복잡한 SQL 쿼리나 가중치 계산 가능
    query = supabase.table("instructors").select("*")
    # 예: 위치 기반 필터링 (Postgres의 배열 포함 연산 사용 가능)
    instructors = query.execute().data
    
    scored_list = []
    for inst in instructors:
        score = 0
        if request_data['location'] in inst['preferred_locations']: score += 50
        if inst['min_rate'] <= request_data['budget']: score += 30
        scored_list.append({"instructor": inst, "score": score})
    
    return sorted(scored_list, key=lambda x: x['score'], reverse=True)

# --- UI Layout ---

st.title("🎓 GitService CareerLog")
st.subheader("LLM 활용 강의 운영 자동 매칭 시스템")

tab1, tab2, tab3 = st.tabs(["의뢰 등록", "강사 매칭", "운영 대시보드"])

with tab1:
    st.write("### 📩 강의 의뢰 입력")
    raw_input = st.text_area("카카오톡이나 이메일 의뢰 전문을 붙여넣으세요.", height=200)
    
    if st.button("AI 구조화 및 저장"):
        with st.spinner("Claude가 분석 중..."):
            parsed_data = parse_with_claude(raw_input)
            st.json(parsed_data)
            
            # DB 저장
            data, count = supabase.table("lecture_requests").insert({
                "raw_text": raw_input,
                "org_name": parsed_data['org_name'],
                "lecture_date": parsed_data['lecture_date'],
                "start_time": parsed_data['start_time'],
                "duration_hours": parsed_data['duration_hours'],
                "location": parsed_data['location'],
                "budget": parsed_data['budget']
            }).execute()
            st.success("의뢰 데이터가 Supabase에 기록되었습니다.")

with tab2:
    st.write("### 🤝 강사 추천 및 배정")
    # 대기 중인 의뢰 불러오기
    pending_requests = supabase.table("lecture_requests").select("*").eq("status", "pending").execute().data
    
    if pending_requests:
        selected_req = st.selectbox("매칭할 의뢰 선택", pending_requests, format_func=lambda x: f"[{x['org_name']}] {x['lecture_date']}")
        
        if selected_req:
            st.info(f"📍 장소: {selected_req['location']} | 💰 예산: {selected_req['budget']}원")
            recommends = get_recommended_instructors(selected_req)
            
            for item in recommends:
                inst = item['instructor']
                col1, col2, col3 = st.columns([3, 1, 1])
                col1.write(f"**{inst['name']}** (점수: {item['score']})")
                col2.write(f"시급: {inst['min_rate']}원")
                if col3.button("확정", key=inst['id']):
                    # 배정 로직: assignments 테이블 저장 & 의뢰 상태 변경
                    supabase.table("assignments").insert({
                        "instructor_id": inst['id'],
                        "request_id": selected_req['id']
                    }).execute()
                    supabase.table("lecture_requests").update({"status": "matched"}).eq("id", selected_req['id']).execute()
                    st.balloons()
                    st.success(f"{inst['name']} 강사님으로 확정되었습니다!")
    else:
        st.write("현재 매칭 대기 중인 의뢰가 없습니다.")

with tab3:
    st.write("### 📊 운영 현황")
    # 간단한 데이터 시각화
    all_assignments = supabase.table("assignments").select("*, instructors(name), lecture_requests(*)").execute().data
    if all_assignments:
        import pandas as pd
        df = pd.json_normalize(all_assignments)
        st.dataframe(df)
    else:
        st.write("배정 이력이 없습니다.")
