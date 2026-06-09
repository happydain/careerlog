"""
Google Calendar 연동 모듈
- 강의 일정을 구글 캘린더에 자동 등록
- 캘린더 일정 조회
"""

import streamlit as st
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from config import CALENDAR_ID

SCOPES = ["https://www.googleapis.com/auth/calendar"]

_calendar_service = None


def get_calendar_service():
    global _calendar_service
    if _calendar_service is None:
        creds = Credentials.from_service_account_info(
            dict(st.secrets["google_gsheets"]),
            scopes=SCOPES
        )
        _calendar_service = build("calendar", "v3", credentials=creds)
    return _calendar_service


def add_event(date_str: str, start: str, end: str, title: str,
              instructor: str, agency: str, location: str) -> str:
    """
    캘린더에 강의 일정 추가
    반환: 이벤트 링크
    """
    try:
        service = get_calendar_service()

        start_dt = f"{date_str}T{start}:00+09:00"
        end_dt   = f"{date_str}T{end}:00+09:00"

        event = {
            "summary": f"[{agency}] {title} - {instructor or '강사미정'}",
            "location": location,
            "description": f"의뢰기관: {agency}\n과정명: {title}\n강사: {instructor}",
            "start": {"dateTime": start_dt, "timeZone": "Asia/Seoul"},
            "end":   {"dateTime": end_dt,   "timeZone": "Asia/Seoul"},
        }

        result = service.events().insert(
            calendarId=CALENDAR_ID,
            body=event
        ).execute()

        return result.get("htmlLink", "")
    except Exception as e:
        st.error(f"캘린더 등록 오류: {e}")
        return ""


def get_events(start_date: str, end_date: str, calendar_id: str = CALENDAR_ID) -> list:
    """
    기간 내 캘린더 일정 조회
    start_date, end_date: 'YYYY-MM-DD'
    """
    try:
        service = get_calendar_service()

        result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=f"{start_date}T00:00:00+09:00",
            timeMax=f"{end_date}T23:59:59+09:00",
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        return result.get("items", [])
    except Exception as e:
        st.error(f"캘린더 조회 오류: {e}")
        return []


def delete_event(event_id: str) -> bool:
    """캘린더 일정 삭제"""
    try:
        service = get_calendar_service()
        service.events().delete(
            calendarId=CALENDAR_ID,
            eventId=event_id
        ).execute()
        return True
    except Exception as e:
        st.error(f"캘린더 삭제 오류: {e}")
        return False
