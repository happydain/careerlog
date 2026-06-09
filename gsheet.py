import streamlit as st
import pandas as pd
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from config import SPREADSHEET_ID, COLUMNS


def get_gsheet_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        dict(st.secrets["google_gsheets"]), scope
    )
    return gspread.authorize(creds)


def get_or_create_sheet(client, title):
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    try:
        return spreadsheet.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=1000, cols=30)


def ensure_header(sheet):
    existing = sheet.get_all_values()
    if not existing or existing[0] != COLUMNS:
        sheet.clear()
        sheet.append_row(COLUMNS)


def append_to_gsheet(df):
    try:
        client = get_gsheet_client()
        sheet1 = get_or_create_sheet(client, "의뢰일별")
        ensure_header(sheet1)
        sheet2 = get_or_create_sheet(client, "강의날짜별")
        ensure_header(sheet2)

        # 중복 체크
        existing_data = sheet2.get_all_records()
        if existing_data:
            existing_df = pd.DataFrame(existing_data)
            duplicates = []
            for _, row in df.iterrows():
                mask = (
                    (existing_df["강의일시"].astype(str) == str(row.get("강의일시", ""))) &
                    (existing_df["의뢰기관"].astype(str) == str(row.get("의뢰기관", ""))) &
                    (existing_df["과정명"].astype(str) == str(row.get("과정명", ""))) &
                    (existing_df["시작"].astype(str) == str(row.get("시작", "")))
                )
                if mask.any():
                    duplicates.append(f"{row.get('강의일시','')} / {row.get('의뢰기관','')} / {row.get('과정명','')} / {row.get('강사님','')}")
            if duplicates:
                st.warning(f"⚠️ 중복 데이터 {len(duplicates)}건 - 저장하지 않습니다:\n" + "\n".join(duplicates))
                return False

        for col in COLUMNS:
            if col not in df.columns:
                df[col] = ""
        df = df[COLUMNS]
        df_clean = df.fillna("").astype(str)
        values = df_clean.values.tolist()
        sheet1.append_rows(values)
        sheet2.append_rows(values)
        return True
    except Exception as e:
        st.exception(e)
        return False


def append_evidence_to_sheet(folder_name: str, files):
    """증빙 파일 내용을 구글 시트 '증빙' 탭에 기록"""
    try:
        client = get_gsheet_client()
        sheet = get_or_create_sheet(client, "증빙")

        evidence_columns = ["폴더명", "파일명", "업로드일시", "내용"]
        existing = sheet.get_all_values()
        if not existing or existing[0] != evidence_columns:
            sheet.clear()
            sheet.append_row(evidence_columns)

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        rows = []

        for f in files:
            f.seek(0)
            if f.name.endswith(".xlsx"):
                df = pd.read_excel(f, sheet_name=0)
                content = df.to_csv(index=False)
            elif f.type and "text" in f.type:
                content = f.read().decode("utf-8", errors="ignore")
            else:
                content = f"[{f.type}] 파일"
            rows.append([folder_name, f.name, now, content[:5000]])

        if rows:
            sheet.append_rows(rows)
        return True
    except Exception as e:
        st.error(f"증빙 저장 오류: {e}")
        return False


def load_gsheet_raw():
    try:
        client = get_gsheet_client()
        sheet = get_or_create_sheet(client, "의뢰일별")
        data = sheet.get_all_records()
        if not data:
            return pd.DataFrame(columns=COLUMNS)
        df = pd.DataFrame(data)
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = ""
        return df[COLUMNS]
    except Exception as e:
        st.error(f"구글시트 불러오기 오류: {e}")
        return pd.DataFrame(columns=COLUMNS)


def load_gsheet_final():
    try:
        client = get_gsheet_client()
        sheet = get_or_create_sheet(client, "강의날짜별")
        data = sheet.get_all_records()
        if not data:
            return pd.DataFrame(columns=COLUMNS)
        df = pd.DataFrame(data)
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = ""
        df["_dt"] = pd.to_datetime(df["강의일시"], errors="coerce")
        df = df.sort_values("_dt").drop(columns=["_dt"]).reset_index(drop=True)
        return df[COLUMNS]
    except Exception as e:
        st.error(f"구글시트 불러오기 오류: {e}")
        return pd.DataFrame(columns=COLUMNS)


def save_gsheet_final(df):
    try:
        client = get_gsheet_client()
        sheet = get_or_create_sheet(client, "강의날짜별")
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = ""
        df = df[COLUMNS]
        sheet.clear()
        sheet.append_row(COLUMNS)
        df_clean = df.fillna("").astype(str)
        sheet.append_rows(df_clean.values.tolist())
        return True
    except Exception as e:
        st.exception(e)


def create_evidence_spreadsheet(folder_id: str, folder_name: str, raw_text: str, requester: str, request_date: str):
    """드라이브 폴더 안에 새 구글시트 생성 후 카톡 내용 저장"""
    try:
        from googleapiclient.discovery import build
        from google.oauth2.service_account import Credentials

        client = get_gsheet_client()
        spreadsheet = client.create(f"{folder_name}_원본의뢰")

        # 드라이브 폴더로 이동
        creds = Credentials.from_service_account_info(
            dict(st.secrets["google_gsheets"]),
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        drive_service = build("drive", "v3", credentials=creds)

        file = drive_service.files().get(
            fileId=spreadsheet.id, fields="parents"
        ).execute()
        drive_service.files().update(
            fileId=spreadsheet.id,
            addParents=folder_id,
            removeParents=",".join(file.get("parents", [])),
            fields="id, parents",
            supportsAllDrives=True
        ).execute()

        # 내용 입력
        sheet = spreadsheet.sheet1
        sheet.update_title("원본의뢰")
        sheet.append_row(["의뢰일", "의뢰인", "원본내용"])
        sheet.append_row([request_date, requester, raw_text])

        return True
    except Exception as e:
        st.error(f"증빙 시트 생성 오류: {e}")

def save_gsheet_raw(df):
    try:
        client = get_gsheet_client()
        sheet = get_or_create_sheet(client, "의뢰일별")
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = ""
        df = df[COLUMNS]
        sheet.clear()
        sheet.append_row(COLUMNS)
        df_clean = df.fillna("").astype(str)
        sheet.append_rows(df_clean.values.tolist())
        return True
    except Exception as e:
        st.exception(e)
        return False
        return False
        return False
