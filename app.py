import streamlit as st
import pandas as pd
from supabase import create_client, Client
from anthropic import Anthropic
import json
from datetime import datetime, timedelta

# --- 1. 설정 및 초기화 ---
st.set_page_config(page_title="GitService CareerLog", layout="wide")

# Secrets에서 API 키 로드 (Streamlit Cloud 환경 기준)
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    CLAUDE_API_KEY = st.secrets["CLAUDE_API_KEY"]
except KeyError:
    st.error("Secrets 설정이 누락되었습니다. .streamlit/secrets.toml 파일을 확인하세요.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
anthropic = Anthropic(api_key=CLAUDE_API_KEY)

# --- 2. 비즈니스 로직 함수 ---

def parse_request_with_claude(text):
    """Claude API를 사용하여 강의 의뢰 텍스트 구조화"""
    system_prompt = "당신은 강의 의뢰 추출 전문가입니다. 입력된 텍스트에서 정보를 추출하여 오직 JSON으로만 응답하세요."
    user_prompt = f"""
    아래 텍스트에서 다음 정보를 추출하세요:
    - org_name (기관명)
    - lecture_date (YYYY-MM-DD)
    - start_time (HH:MM)
    - duration_hours (숫자)
    - location (지역명)
    - budget (전체 예산 숫자)

    텍스트: {text}
    """
    
    response = anthropic.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=1000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}]
    )
    return json.loads(response.content[0].text)

def get_matching_instructors(req_data):
    """조건 기반 강사 추천 (단순 필터링 로직)"""
    instructors = supabase.table("instructors").select("*").execute().data
    
    scored_instructors = []
    for inst in instructors:
        score = 0
        # 지역 매칭 (장소 키워드가 선호 지역에 포함되는지 확인)
        if any(loc in req_data['location'] for loc in inst['preferred_locations']):
            score += 50
        # 예산 매칭
        if inst['min_rate'] <= (req_data['budget'] / req_data['duration_hours']):
            score += 30
        
        scored_instructors.append({"instructor": inst, "score": score})
    
    # 점수 높은 순 정렬
    return sorted(scored_instructors, key=lambda x: x['score'], reverse=True)

# --- 3. Streamlit UI 레이아웃 ---

st.title("🚀 CareerLog: AI 강의 매칭 시스템")
st.sidebar.header("Navigation")
menu = st.sidebar.radio("이동", ["의뢰 등록", "강사 매칭 및 배정", "강사 경력 관리"])

# --- 메뉴 1: 의뢰 등록 ---
if menu == "의뢰 등록":
    st.header("📥 새로운 강의 의뢰 등록")
    st.write("카톡, 이메일 등에서 받은 의뢰 텍스트를 그대로 복사해 넣으세요.")
    
    raw_text = st.text_area("의뢰 원문 입력", height=200, placeholder="예: [에이전시] 5월 20일 강남역 인근에서 파이썬 강의 3시간 가능하신 분 찾습니다. 예산은 30만원입니다.")
    
    if st.button("AI 분석 실행"):
        if raw_text:
            with st.spinner("Claude AI가 데이터를 분석 중입니다..."):
                try:
                    parsed = parse_request_with_claude(raw_text)
                    st.session_state['last_parsed'] = parsed
                    st.success("분석 완료!")
                    
                    # 분석 결과 보여주기
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("### 추출된 정보")
                        st.json(parsed)
                    with col2:
                        if st.button("DB에 최종 저장"):
                            res = supabase.table("lecture_requests").insert({
                                "raw_text": raw_text,
                                "org_name": parsed['org_name'],
                                "lecture_date": parsed['lecture_date'],
                                "start_time": parsed['start_time'],
                                "duration_hours": parsed['duration_hours'],
                                "location": parsed['location'],
                                "budget": parsed['budget']
                            }).execute()
                            st.info("데이터베이스 저장 성공!")
                except Exception as e:
                    st.error(f"오류 발생: {e}")
        else:
            st.warning("텍스트를 입력해주세요.")

# --- 메뉴 2: 강사 매칭 및 배정 ---
elif menu == "강사 매칭 및 배정":
    st.header("🤝 적합 강사 추천 및 확정")
    
    # 대기 중인 의뢰 가져오기
    requests = supabase.table("lecture_requests").select("*").eq("status", "pending").execute().data
    
    if not requests:
        st.info("현재 처리할 대기 의뢰가 없습니다.")
    else:
        req_options = {f"[{r['org_name']}] {r['lecture_date']}": r for r in requests}
        selected_label = st.selectbox("매칭할 강의 선택", list(req_options.keys()))
        selected_req = req_options[selected_label]
        
        st.divider()
        
        # 매칭 로직 실행
        recommends = get_matching_instructors(selected_req)
        
        st.subheader("💡 추천 강사 리스트")
        for item in recommends:
            inst = item['instructor']
            score = item['score']
            
            with st.expander(f"{inst['name']} (매칭 점수: {score}점)"):
                col1, col2 = st.columns([3, 1])
                col1.write(f"**가능 과목:** {', '.join(inst['subjects'])}")
                col1.write(f"**희망 지역:** {', '.join(inst['preferred_locations'])}")
                col2.metric("최소 시급", f"{inst['min_rate']:,}원")
                
                if st.button(f"{inst['name']} 강사 확정", key=f"btn_{inst['id']}"):
                    # 1. 배정 이력 기록
                    supabase.table("assignments").insert({
                        "instructor_id": inst['id'],
                        "request_id": selected_req['id']
                    }).execute()
                    
                    # 2. 의뢰 상태 변경
                    supabase.table("lecture_requests").update({"status": "matched"}).eq("id", selected_req['id']).execute()
                    
                    st.success(f"{inst['name']} 강사님 배정이 완료되었습니다!")
                    st.balloons()

# --- 메뉴 3: 강사 경력 관리 (Dashboard) ---
elif menu == "강사 경력 관리":
    st.header("📊 강사별 배정 현황 및 경력 데이터")
    
    # 조인 쿼리를 통해 배정 데이터 가져오기
    query = """
        id,
        instructors ( name, email ),
        lecture_requests ( org_name, lecture_date, duration_hours, budget, location )
    """
    history = supabase.table("assignments").select(query).execute().data
    
    if history:
        df_list = []
        for h in history:
            df_list.append({
                "강사명": h['instructors']['name'],
                "기관명": h['lecture_requests']['org_name'],
                "강의일자": h['lecture_requests']['lecture_date'],
                "시간": h['lecture_requests']['duration_hours'],
                "지역": h['lecture_requests']['location'],
                "금액": h['lecture_requests']['budget']
            })
        df = pd.DataFrame(df_list)
        
        # 필터링 UI
        selected_inst = st.selectbox("강사 필터", ["전체"] + list(df["강사명"].unique()))
        if selected_inst != "전체":
            df = df[df["강사명"] == selected_inst]
            
        st.dataframe(df, use_container_width=True)
        
        # 통계
        st.sidebar.metric("총 강의 횟수", len(df))
        st.sidebar.metric("총 매출", f"{df['금액'].sum():,}원")
        
        # CSV 다운로드 (경력증명서 기초 데이터)
        csv = df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("데이터 다운로드 (CSV)", csv, "career_data.csv", "text/csv")
    else:
        st.info("누적된 배정 데이터가 없습니다.")
