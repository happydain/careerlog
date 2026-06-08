import io
import streamlit as st
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from config import DRIVE_ROOT_FOLDER_ID

SCOPES = ["https://www.googleapis.com/auth/drive"]
_drive_service = None


def get_drive_service():
    global _drive_service
    if _drive_service is None:
        creds = Credentials.from_service_account_info(
            dict(st.secrets["google_gsheets"]),
            scopes=SCOPES
        )
        _drive_service = build("drive", "v3", credentials=creds)
    return _drive_service


# ─────────────────────────────────────────────
# 폴더 관리
# ─────────────────────────────────────────────

def _find_folder(service, name, parent_id):
    q = (
        f"name='{name}' "
        f"and '{parent_id}' in parents "
        f"and mimeType='application/vnd.google-apps.folder' "
        f"and trashed=false"
    )
    result = service.files().list(
        q=q,
        fields="files(id,name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()
    files = result.get("files", [])
    return files[0]["id"] if files else None


def _create_folder(service, name, parent_id):
    meta = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id]
    }
    folder = service.files().create(
        body=meta,
        fields="id",
        supportsAllDrives=True
    ).execute()
    return folder["id"]


def _get_or_create_folder(service, name, parent_id):
    fid = _find_folder(service, name, parent_id)
    if not fid:
        fid = _create_folder(service, name, parent_id)
    return fid


def create_request_folder(year: int, agency: str, request_date: str, requester: str) -> str:
    """의뢰 1건 = 폴더 1개: CareerLog/연도/기관/날짜_의뢰인"""
    service = get_drive_service()
    year_id     = _get_or_create_folder(service, str(year), DRIVE_ROOT_FOLDER_ID)
    agency_id   = _get_or_create_folder(service, agency, year_id)
    folder_name = f"{request_date.replace('-', '')}_{requester}"
    folder_id   = _get_or_create_folder(service, folder_name, agency_id)
    return folder_id


def get_folder_url(folder_id: str) -> str:
    return f"https://drive.google.com/drive/folders/{folder_id}"


def append_change_log(folder_id: str, change_summary: str, modifier: str):
    """변경이력 텍스트를 구글 Docs로 저장"""
    service = get_drive_service()
    today = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"변경이력_{today}_{modifier}"
    content = (
        f"[변경 내역]\n"
        f"변경일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"변경의뢰인: {modifier}\n"
        f"{'='*40}\n\n"
        f"{change_summary}"
    )
    meta = {
        "name": filename,
        "mimeType": "application/vnd.google-apps.document",
        "parents": [folder_id]
    }
    media = MediaIoBaseUpload(
        io.BytesIO(content.encode("utf-8")),
        mimetype="text/plain"
    )
    service.files().create(
        body=meta,
        media_body=media,
        fields="id",
        supportsAllDrives=True
    ).execute()
