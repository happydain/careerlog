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
        sheet = get_or_create_sheet(client, "보건스케쥴")
        ensure_header(sheet)

        # 중복 체크
        existing_data = sheet.get_all_records()
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

        try:
            df["_dt"] = pd.to_datetime(df["강의일시"], errors="coerce")
            df = df.sort_values("_dt", ascending=False).drop(columns=["_dt"])
        except Exception:
            pass

        df_clean = df.fillna("").astype(str)
        sheet.append_rows(df_clean.values.tolist())
        return True
    except Exception as e:
        st.exception(e)
        return False


def append_evidence_to_sheet(folder_name: str, files):
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
        sheet = get_or_create_sheet(client, "최종")
        data = sheet.get_all_records()
        if not data:
            return pd.DataFrame(columns=COLUMNS)
        df = pd.DataFrame(data)
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = ""
        df["_dt"] = pd.to_datetime(df["강의일시"], errors="coerce")
        df = df.sort_values("_dt", ascending=False).drop(columns=["_dt"]).reset_index(drop=True)
        return df[COLUMNS]
    except Exception as e:
        st.error(f"구글시트 불러오기 오류: {e}")
        return pd.DataFrame(columns=COLUMNS)


def save_gsheet_final(df):
    try:
        client = get_gsheet_client()
        sheet = get_or_create_sheet(client, "최종")
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


def init_status_column():
    """기존 데이터에 상태 컬럼 일괄 추가"""
    try:
        client = get_gsheet_client()
        for sheet_name in ["의뢰일별", "최종"]:
            sheet = get_or_create_sheet(client, sheet_name)
            df = pd.DataFrame(sheet.get_all_records())
            if "상태" not in df.columns:
                df["상태"] = "정상"
                sheet.clear()
                sheet.append_row(df.columns.tolist())
                sheet.append_rows(df.fillna("").astype(str).values.tolist())
        return True
    except Exception as e:
        return False

def replace_gsheet_final(df):
    """최종 시트 전체 교체 (기존 데이터 삭제 후 새 데이터 입력)"""
    try:
        client = get_gsheet_client()
        sheet = get_or_create_sheet(client, "최종")
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = ""
        df = df[COLUMNS]
        # 강의일시 내림차순 정렬
        try:
            df["_dt"] = pd.to_datetime(df["강의일시"], errors="coerce")
            df = df.sort_values("_dt", ascending=False).drop(columns=["_dt"])
        except Exception:
            pass
        sheet.clear()
        sheet.append_row(COLUMNS)
        df_clean = df.fillna("").astype(str)
        sheet.append_rows(df_clean.values.tolist())
        return True
    except Exception as e:
        st.exception(e)
        return False
