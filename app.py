import streamlit as st
import pandas as pd
import google.generativeai as genai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import io
from datetime import datetime

# --- 1. 페이지 및 API 설정 ---
st.set_page_config(page_title="CareerLog AI (Gemini)", page_icon="🚀", layout="wide")

# Gemini 설정
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-1.5-flash') # 속도가 빠른 flash 모델 사용

# --- 2. 구글 시트 연결 함수 ---
def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials = dict(st.secrets["google_gsheets"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials, scope)
    client = gspread.authorize(creds)
    return client

def append_to_gsheet(df):
    try:
        client = get_gsheet_client()
        # 구글 드라이브에 미리 생성한 시트 이름
        sheet = client.open("보건강사스케쥴").sheet1
        values = df.values.tolist()
        sheet.append_rows(values)
        return True
    except Exception as e:
        st.error(f"구글 시트 저장 오류: {e}")
        return False

# --- 3. Gemini API 파싱 함수 ---
def parse_schedule_with_gemini(text):
    prompt = f"""
    당신은 강의 스케줄 데이터 정리 전문가입니다. 다음 강의 의뢰 텍스트를 분석하여 JSON 배열 포맷으로 변환하세요.
    마크다운 기호 없이 순수 JSON만 출력하세요.

    [추출 및 변환 규칙]
    1. '1월 20(화)-1' 형식에서 '-1'은 '동료를 살리는 응급처치(심폐소생술 및 AED)' 과목입니다.
    2. '10월 15(목)-2' 형식에서 '-2'은 '뇌심혈관질환의 위험요인과 예방대책' 과목입니다.
    3. 일정 범위가 '2월 25~26일'인 경우, 25일과 26일 각각 별도의 데이터 행으로 만드세요.
    4. 시간이 명시되지 않은 일반 일정은 '14:00~16:00'을 기본값으로 하세요.
    5. 장소 정보가 없으면 '대한산업안전협회 서울지역본부'를 기본값으로 합니다.
    6. 'SK TNS'나 '조선호텔' 같은 사업장명이 있으면 '의뢰기관'에 넣으세요.
    7. JSON 필드명: 일자(YYYY-MM-DD), 시작시간, 종료시간, 의뢰기관, 과정명, 과목명, 장소, 강사명, 비고

    텍스트:
    {text}
    """
    
    with st.spinner("Gemini AI가 일정을 구조화하고 있습니다..."):
        response = model.generate_content(prompt)
        # Gemini 응답에서 JSON만 추출 (혹시 모를 마크다운 제거)
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(clean_json)

# --- 4. 메인 UI ---
st.title("🎓 GitService CareerLog")
st.info("비정형 텍스트 일정을 Gemini AI가 분석하여 구글 스프레드시트에 저장합니다.")

tabs = st.tabs(["📥 의뢰 텍스트/파일 입력", "📊 마스터 시트 조회"])

# --- Tab 1: 데이터 입력 ---
with tabs[0]:
    st.markdown("### 1. 카톡/이메일 텍스트 분석")
    raw_text = st.text_area("강의 요청 메시지 전체를 복사해서 붙여넣으세요.", height=300)
    
    if st.button("🪄 Gemini AI로 분석하기"):
        if raw_text:
            try:
                parsed_result = parse_schedule_with_gemini(raw_text)
                st.session_state['temp_df'] = pd.DataFrame(parsed_result)
                st.success("분석 완료! 아래 표에서 내용을 확인하고 수정하세요.")
            except Exception as e:
                st.error(f"분석 중 오류 발생: {e}")
    
    st.divider()
    st.markdown("### 2. 기존 엑셀 파일 업로드")
    uploaded_file = st.file_uploader("정리된 엑셀(.xlsx)이 있다면 업로드하세요.", type=["xlsx"])
    if uploaded_file:
        df_upload = pd.read_excel(uploaded_file)
        st.session_state['temp_df'] = df_upload
        st.success("엑셀 파일 로드 완료!")

    # 결과 데이터 편집 및 저장
    if 'temp_df' in st.session_state:
        st.markdown("### 📋 최종 확인 및 수정")
        edited_df = st.data_editor(st.session_state['temp_df'], use_container_width=True, num_rows="dynamic")
        
        if st.button("💾 구글 스프레드시트로 전송"):
            if append_to_gsheet(edited_df):
                st.balloons()
                st.success("구글 시트에 성공적으로 저장되었습니다!")
                del st.session_state['temp_df']

# --- Tab 2: 시트 조회 ---
with tabs[1]:
    st.markdown("### 📅 현재 구글 시트 데이터")
    if st.button("🔄 시트 데이터 불러오기"):
        try:
            client = get_gsheet_client()
            sheet = client.open("강의운영_마스터_DB").sheet1
            data = sheet.get_all_records()
            if data:
                st.session_state['view_df'] = pd.DataFrame(data)
            else:
                st.warning("데이터가 비어있습니다.")
        except Exception as e:
            st.error(f"불러오기 오류: {e}")

    if 'view_df' in st.session_state:
        df_view = st.session_state['view_df']
        st.dataframe(df_view, use_container_width=True)
        
        # 엑셀 다운로드 버튼
        towrite = io.BytesIO()
        df_view.to_excel(towrite, index=False, engine='xlsxwriter')
        st.download_button(
            label="📥 전체 일정 엑셀 다운로드",
            data=towrite.getvalue(),
            file_name=f"강의마스터_{datetime.now().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.ms-excel"
        )
