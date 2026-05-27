pip install streamlit anthropic gspread oauth2client pandas
import streamlit as st
import pandas as pd
from anthropic import Anthropic
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

# --- 1. 보안 설정 (Secrets) ---
# 로컬 테스트 시 .streamlit/secrets.toml에 저장하거나 아래 직접 입력 가능
CLAUDE_API_KEY = st.secrets["CLAUDE_API_KEY"]
GOOGLE_SERVICE_ACCOUNT = st.secrets["GOOGLE_SERVICE_ACCOUNT"] # JSON 내용 전체

# --- 2. 구글 시트 연결 함수 ---
def connect_google_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(GOOGLE_SERVICE_ACCOUNT), scope)
    client = gspread.authorize(creds)
    # 스프레드시트 이름으로 열기
    sheet = client.open("2026_강의관리_마스터").sheet1 
    return sheet

# --- 3. Claude 파싱 함수 ---
def parse_schedule_text(raw_text):
    anthropic = Anthropic(api_key=CLAUDE_API_KEY)
    
    prompt = f"""
    당신은 강의 스케줄 분석 전문가입니다. 아래 텍스트에서 모든 강의 일정을 추출하여 JSON 배열로 응답하세요.
    
    [데이터 변환 규칙]
    1. '1월 20(화)-1' -> 날짜: 2026-01-20, 과목: '응급처치'
    2. '10월 15(목)-2' -> 날짜: 2026-10-15, 과목: '뇌심혈관'
    3. 시간 정보가 없으면 기본값 '14:00~16:00' 사용.
    4. 강사명이 이름 옆에 있으면 추출 (예: '김미림').
    5. JSON 필드명: 일자, 시작시간, 종료시간, 의뢰기관, 과정명, 과목명, 장소, 강사명, 비고

    텍스트: {raw_text}
    """
    
    response = anthropic.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=4000,
        system="반드시 오직 JSON 배열만 반환하세요.",
        messages=[{"role": "user", "content": prompt}]
    )
    return json.loads(response.content[0].text)

# --- 4. Streamlit UI ---
st.title("📅 강의 의뢰 -> 구글 시트 자동 저장")

raw_input = st.text_area("강의 의뢰 텍스트를 붙여넣으세요.", height=300)

if st.button("AI 분석 및 구글 시트 전송"):
    if raw_input:
        with st.spinner("AI 분석 중..."):
            try:
                # 1. AI 파싱
                parsed_data = parse_schedule_text(raw_input)
                df = pd.DataFrame(parsed_data)
                
                st.subheader("📋 분석 결과 미리보기")
                st.dataframe(df)
                
                # 2. 구글 시트 저장
                sheet = connect_google_sheet()
                
                # 데이터 변환 (리스트의 리스트 형태)
                values = df.values.tolist()
                
                # 시트에 추가 (append_rows 사용)
                sheet.append_rows(values)
                
                st.success(f"✅ 총 {len(values)}건의 일정이 구글 스프레드시트에 저장되었습니다!")
                
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")
