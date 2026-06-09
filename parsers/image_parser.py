import streamlit as st
import google.generativeai as genai


def parse_image_schedule(img_file) -> str:
    """이미지에서 강의 일정 텍스트 추출 (Gemini Vision)"""
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-1.5-flash")

    img_file.seek(0)
    img_data = img_file.read()

    response = model.generate_content([
        """이 이미지는 강의 일정표입니다.
이미지에서 다음 정보를 텍스트로 추출해주세요:
- 날짜 (예: 2025년 10월 13일, 2025.10.13, 10월 13일 등)
- 시간 (예: 14:00~16:00, 14시~16시 등)
- 과목명
- 장소 또는 강의실
- 강사명 (있는 경우)

각 행을 줄바꿈으로 구분해서 원본 텍스트 그대로 출력해주세요.
분석이나 설명 없이 텍스트만 출력해주세요.""",
        {"mime_type": img_file.type or "image/png", "data": img_data}
    ])
    return response.text
