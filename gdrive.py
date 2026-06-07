"""
Google Drive 연동 모듈
- CareerLog/연도/기관/강의폴더 자동 생성 및 4대 하위 폴더 보장
- 공통 의뢰 증빙(엑셀 파일, 카톡 통짜 텍스트) 일괄 배포 저장
- 변경이력 발생 시 이미지 캡처 및 개별 텍스트 증빙 자동 기록
- 폴더 URL 반환
"""

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
        try:
            # st.secrets에 등록된 구글 인증 정보를 가져옵니다.
            creds_info = dict(st.secrets["google_gsheets"])
            creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
            _drive_service = build("drive", "v3", credentials=creds)
        except Exception as e:
            st.error(f"❌ 구글 드라이브 API 인증 오류: st.secrets['google_gsheets']를 확인하세요. ({e})")
            raise e
    return _drive_service


# ─────────────────────────────────────────────
# 내부 폴더 관리 유틸리티 함수
# ─────────────────────────────────────────────

def _find_folder(service, name, parent_id):
    """지정한 상위 폴더 내부에서 특정 이름의 폴더가 존재하는지 검색"""
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
    """새로운 폴더를 생성"""
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
    """폴더가 있으면 기존 ID를 반환하고, 없으면 새로 만들어 반환 (중복 방지)"""
    fid = _find_folder(service, name, parent_id)
    if not fid:
        fid = _create_folder(service, name, parent_id)
    return fid


def get_lecture_folder_id(year: int, agency: str, lecture_date: str, subject: str) -> str:
    """연도 -> 기관 -> 강의일시_과정명 구조의 폴더 계층을 탐색 및 생성"""
    service = get_drive_service()
    year_id     = _get_or_create_folder(service, str(year), DRIVE_ROOT_FOLDER_ID)
    agency_id   = _get_or_create_folder(service, agency, year_id)
    folder_name = f"{lecture_date}_{subject}"
    lecture_id  = _get_or_create_folder(service, folder_name, agency_id)
    return lecture_id


def get_folder_url(folder_id: str) -> str:
    """구글 드라이브 폴더의 웹 브라우저 링크 반환"""
    return f"https://drive.google.com/drive/folders/{folder_id}"


# ─────────────────────────────────────────────
# 기본 파일 업로드 코어 함수
# ─────────────────────────────────────────────

def _upload_text(service, filename: str, content: str, parent_id: str) -> str:
    """일반 텍스트 문자열을 구글 Docs(문서) 포맷으로 변환하여 업로드 (용량 차감 없음)"""
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
    """바이너리 파일(이미지, PDF, 엑셀 등)을 지정한 폴더에 업로드"""
    meta = {
        "name": filename,
        "parents": [parent_id]
    }

    # 만약 개별 DOCX 파일을 업로드하는 경우 구글 문서 포맷으로 자동 변환해 용량 절약
    if mimetype and "wordprocessingml" in mimetype:
        meta["mimeType"] = "application/vnd.google-apps.document"

    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mimetype)
    f = service.files().create(
        body=meta,
        media_body=media,
        fields="id",
        supportsAllDrives=True
    ).execute()
    return f["id"]


# ─────────────────────────────────────────────
# 업무 로직 연동 함수 (비즈니스 레이어)
# ─────────────────────────────────────────────

def create_careerlog_structure(year, agency, lecture_date, subject):
    """
    [최초 입력 단계용 - 1단계]
    메인 강의 폴더를 생성하고 하위에 필요한 필수 4대 하위 표준 폴더 구조를 보장하여 생성합니다.
    """
    lecture_folder_id = get_lecture_folder_id(year, agency, lecture_date, subject)
    service = get_drive_service()

    sub_folders = ["01_원본의뢰", "02_의뢰서", "03_변경이력", "04_정산"]
    for folder_name in sub_folders:
        _get_or_create_folder(service, folder_name, lecture_folder_id)

    return lecture_folder_id


def save_common_request_evidence(lecture_folder_ids: list, uploaded_excel, raw_text: str, requester: str, request_date: str):
    """
    [최초 입력 단계용 - 2단계] ★★★
    일괄 업로드된 파일(엑셀)이나 공통 카톡 원문이 들어왔을 때, 
    이번 의뢰 묶음으로 생성된 모든 개별 강의 폴더의 '01_원본의뢰' 폴더에 공통 증빙 파일들을 일괄 자동 분배 저장합니다.
    """
    if not lecture_folder_ids:
        return
        
    service = get_drive_service()
    
    # 1. 업로드된 공통 엑셀 파일이 존재하면 바이너리 데이터를 미리 선행 로드
    excel_data = None
    if uploaded_excel:
        uploaded_excel.seek(0)
        excel_data = uploaded_excel.read()
        
    # 2. 생성된 모든 개별 강의 일들의 하위 '01_원본의뢰' 폴더를 순회하며 증빙 복사본 주입
    for folder_id in lecture_folder_ids:
        sub_id = _get_or_create_folder(service, "01_원본의뢰", folder_id)
        
        # 공통 엑셀 파일 저장
        if excel_data:
            _upload_bytes(
                service=service, 
                filename=uploaded_excel.name, 
                data=excel_data, 
                mimetype=uploaded_excel.type or "application/octet-stream", 
                parent_id=sub_id
            )
            
        # 공통 카톡/이메일 통짜 본문이 존재할 경우 구글 Docs 문서로 저장
        if raw_text and raw_text.strip():
            safe_date = str(request_date).replace("-", "")
            filename = f"공통원본의뢰_{safe_date}_{requester}"
            header = f"[공통 원본 의뢰 내용]\n의뢰일: {request_date}\n의뢰인: {requester}\n{'='*40}\n\n"
            _upload_text(service, filename, header + raw_text, sub_id)


def append_change_log_with_evidence(folder_id: str, change_summary: str, modifier: str, evidence_image=None, evidence_text: str = None):
    """
    [최종 스케줄 수정 단계용] ★★★
    운영 도중 특정 일정이 변경되었을 때, 해당 강의 일의 '03_변경이력' 폴더에 접근하여
    어떤 셀이 바뀌었는지 요약문(change_summary)과 함께 현장에서 캡처한 변동 이미지, 추가 카톡 지시 내용 텍스트를 정밀 기록합니다.
    """
    service = get_drive_service()
    sub_id = _get_or_create_folder(service, "03_변경이력", folder_id)
    
    today_file_str = datetime.now().strftime("%Y%m%d_%H%M")
    base_filename = f"변경이력_{today_file_str}_{modifier}"
    
    # 1. 텍스트 변경 로그 컨텐츠 생성 및 업로드
    log_content = (
        f"[스케줄 변동 안내 로그]\n"
        f"변경일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"변경담당자: {modifier}\n"
        f"변동요약: {change_summary}\n"
        f"{'='*40}\n\n"
    )
    if evidence_text:
        log_content += f"[제공된 변동 텍스트/카톡 내용]:\n{evidence_text}"
        
    _upload_text(service, base_filename, log_content, sub_id)
    
    # 2. 실시간 변동 증빙 스크린샷 이미지 파일이 제출되었을 경우 이미지 추가 업로드
    if evidence_image:
        evidence_image.seek(0)
        img_data = evidence_image.read()
        img_name = f"변동증빙이미지_{today_file_str}_{evidence_image.name}"
        _upload_bytes(service, img_name, img_data, evidence_image.type or "image/png", sub_id)


# ─────────────────────────────────────────────
# 기존 레거시 함수 유지보수용 인터페이스 (하위 호환성 보장)
# ─────────────────────────────────────────────

def save_original_text(folder_id: str, text: str, requester: str, request_date: str):
    """[기존 함수 호환용] 단일 폴더 개별 텍스트 저장용"""
    if not text.strip(): return
    service = get_drive_service()
    sub_id = _get_or_create_folder(service, "01_원본의뢰", folder_id)
    safe_date = str(request_date).replace("-", "")
    filename = f"원본의뢰_{safe_date}_{requester}"
    header = f"[원본 의뢰 내용]\n의뢰일: {request_date}\n의뢰인: {requester}\n{'='*40}\n\n"
    _upload_text(service, filename, header + text, sub_id)


def save_evidence_files(folder_id: str, uploaded_files):
    """[기존 함수 호환용] 단일 폴더 대량 파일 업로드용"""
    if not uploaded_files: return
    service = get_drive_service()
    sub_id = _get_or_create_folder(service, "01_원본의뢰", folder_id)
    for uf in uploaded_files:
        uf.seek(0)
        data = uf.read()
        _upload_bytes(service, uf.name, data, uf.type or "application/octet-stream", sub_id)


def save_docx_to_drive(folder_id: str, docx_bytes: bytes, filename: str):
    """[기존 함수 호환용] 단일 의뢰서 파일 구글문서화 저장용"""
    service = get_drive_service()
    sub_id = _get_or_create_folder(service, "02_의뢰서", folder_id)
    mimetype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    _upload_bytes(service, filename, docx_bytes, mimetype, sub_id)
