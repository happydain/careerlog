import streamlit as st
import pandas as pd
import gspread
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
        sheet2 = get_or_create_sheet(client, "최종")
        ensure_header(sheet2)

        # 중복 체크 (강의일시 + 의뢰기관 + 과정명 + 시작 기준)
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
                st.warning(f"⚠️ 중복 데이터 {len(duplicates)}건 발견:\n" + "\n".join(duplicates))
                if not st.checkbox("중복 포함하여 저장하시겠습니까?"):
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
        df = df.sort_values("_dt").drop(columns=["_dt"]).reset_index(drop=True)
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
