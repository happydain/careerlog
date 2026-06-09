"""
Google Calendar 연동 모듈
"""
import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from config import CALENDAR_ID
from datetime import datetime, timedelta


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
              instructor: str, agency: str, location: str,
              calendar_id: str = CALENDAR_ID) -> str:
    try:
        service  = get_calendar_service()
        
        event = {
            "summary":     title,
            "location":    location,
            "description": f"의뢰기관: {agency}\n과정명: {title}\n강사: {instructor}",
            "start": {"date": date_str},
            "end":   {"date": (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")},
        }
        result = service.events().insert(
            calendarId=calendar_id,
            body=event
        ).execute()
        return result.get("htmlLink", "")
    except Exception as e:
        st.error(f"캘린더 등록 오류: {e}")
        return ""


def get_events(start_date: str, end_date: str, calendar_id: str = CALENDAR_ID) -> list:
    try:
        service = get_calendar_service()
        result  = service.events().list(
            calendarId=calendar_id,
            timeMin=f"{start_date}T00:00:00+09:00",
            timeMax=f"{end_date}T23:59:59+09:00",
            singleEvents=True,
            orderBy="startTime"
        ).execute()
        return result.get("items", [])
    except Exception as e:
        st.error(f"캘린더 조회 오류: {e}")
        return []


def delete_event(event_id: str, calendar_id: str = CALENDAR_ID) -> bool:
    try:
        service = get_calendar_service()
        service.events().delete(
            calendarId=calendar_id,
            eventId=event_id
        ).execute()
        return True
    except Exception as e:
        st.error(f"캘린더 삭제 오류: {e}")
        return False
