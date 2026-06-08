"""
Google Drive 연동 모듈
- CareerLog/연도/기관/강의폴더 자동 생성
- 원본 카톡 텍스트 → 구글 Docs로 저장 (용량 무료)
- 증빙 이미지/파일 업로드
- 변경이력 자동 기록
- 폴더 URL 반환
"""

import io
import streamlit as st
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from config import DRIVE_ROOT_FOLDER_ID
from datetime import datetime


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


def get_lecture_folder_id(year: int, agency: str, lecture_date: str, subject: str) -> str:
    service = get_drive_service()
    year_id     = _get_or_create_folder(service, str(year), DRIVE_ROOT_FOLDER_ID)
    agency_id   = _get_or_create_folder(service, agency, year_id)
    folder_name = f"{lecture_date}_{subject}"
    lecture_id  = _get_or_create_folder(service, folder_name, agency_id)
    return lecture_id


def get_folder_url(folder_id: str) -> str:
    return f"https://drive.google.com/drive/folders/{folder_id}"


# ─────────────────────────────────────────────
# 파일 업로드
# ─────────────────────────────────────────────

def _upload_text(service, filename: str, content: str, parent_id: str) -> str:
    """텍스트를 구글 Docs로 저장 (용량 무료)"""
    meta = {
        "name": filename,
        "mimeType": "application/vnd.google-apps.document",
        "parents": [parent_id]
    }
    media = MediaIoBaseUpload(
        io.BytesIO(content.encode("utf-8")),
        mimetype="text/plain"
    )
    f = service.files().create(
        body=meta,
        media_body=media,
        fields="id",
        supportsAllDrives=True
    ).execute()
    return f["id"]


def _upload_bytes(service, filename: str, data: bytes, mimetype: str, parent_id: str) -> str:
    """
    파일 업로드
    - DOCX → 구글 Docs로 변환 저장 (용량 무료)
    - 이미지/PDF → 그대로 저장
    """
    meta = {
        "name": filename,
        "parents": [parent_id]
    }

    # DOCX는 구글 Docs로 변환 (용량 안 씀)
    if "wordprocessingml" in mimetype:
        meta["mimeType"] = "application/vnd.google-apps.document"

    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mimetype)
    f = service.files().create(
        body=meta,
        media_body=media,
        fields="id",
        supportsAllDrives=True
    ).execute()
    return f["id"]


def save_original_text(folder_id: str, text: str, requester: str, request_date: str):
    """01_원본의뢰/ 에 카톡 원문을 구글 Docs로 저장"""
    service = get_drive_service()
    sub_id = _get_or_create_folder(service, "01_원본의뢰", folder_id)
    safe_date = str(request_date).replace("-", "")
    filename = f"원본의뢰_{safe_date}_{requester}"
    header = f"[원본 의뢰 내용]\n의뢰일: {request_date}\n의뢰인: {requester}\n{'='*40}\n\n"
    _upload_text(service, filename, header + text, sub_id)


def save_evidence_files(folder_id: str, uploaded_files):
    """01_원본의뢰/ 에 증빙 파일들 업로드"""
    if not uploaded_files:
        return
    service = get_drive_service()
    sub_id = _get_or_create_folder(service, "01_원본의뢰", folder_id)
    for uf in uploaded_files:
        uf.seek(0)
        data = uf.read()
        _upload_bytes(service, uf.name, data, uf.type or "application/octet-stream", sub_id)


def save_docx_to_drive(folder_id: str, docx_bytes: bytes, filename: str):
    """02_의뢰서/ 에 DOCX를 구글 Docs로 변환 저장"""
    service = get_drive_service()
    sub_id = _get_or_create_folder(service, "02_의뢰서", folder_id)
    mimetype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    _upload_bytes(service, filename, docx_bytes, mimetype, sub_id)


def append_change_log(folder_id: str, change_summary: str, modifier: str):
    """03_변경이력/ 에 변경내역을 구글 Docs로 저장"""
    service = get_drive_service()
    sub_id = _get_or_create_folder(service, "03_변경이력", folder_id)
    today = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"변경이력_{today}_{modifier}"
    content = (
        f"[변경 내역]\n"
        f"변경일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"변경의뢰인: {modifier}\n"
        f"{'='*40}\n\n"
        f"{change_summary}"
    )
    _upload_text(service, filename, content, sub_id)

def create_careerlog_structure(
    year,
    agency,
    lecture_date,
    subject
):

    lecture_folder_id = get_lecture_folder_id(
        year,
        agency,
        lecture_date,
        subject
    )

    service = get_drive_service()

    for folder_name in [
        "01_원본의뢰",
        "02_의뢰서",
        "03_변경이력",
        "04_정산"
    ]:
        _get_or_create_folder(
            service,
            folder_name,
            lecture_folder_id
        )

    return lecture_folder_id

def append_evidence_to_sheet(folder_name: str, files):
    """증빙 파일 내용을 구글 시트 '증빙' 탭에 기록"""
    try:
        client = get_gsheet_client()
        sheet = get_or_create_sheet(client, "증빙")
        
        # 헤더 확인
        evidence_columns = ["폴더명", "파일명", "업로드일시", "내용"]
        existing = sheet.get_all_values()
        if not existing or existing[0] != evidence_columns:
            sheet.clear()
            sheet.append_row(evidence_columns)
        
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        rows = []
        
        for f in files:
            f.seek(0)
            # 엑셀이면 내용 읽기
            if f.name.endswith(".xlsx"):
                df = pd.read_excel(f, sheet_name=0)
                content = df.to_csv(index=False)
            # 텍스트 계열이면 내용 읽기
            elif f.type and "text" in f.type:
                content = f.read().decode("utf-8", errors="ignore")
            # 이미지/PDF는 파일명만
            else:
                content = f"[{f.type}] 파일"
            
            rows.append([folder_name, f.name, now, content[:5000]])
        
        if rows:
            sheet.append_rows(rows)
        return True
    except Exception as e:
        st.error(f"증빙 저장 오류: {e}")
        return False
