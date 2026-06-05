from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import streamlit as st

SCOPES = ["https://www.googleapis.com/auth/drive"]

ROOT_FOLDER_ID = "1AtxUFhHDixQzKss5mWs6yIfiTZ78Z7M-"


def get_drive_service():
    credentials = Credentials.from_service_account_info(
        dict(st.secrets["google_gsheets"]),
        scopes=SCOPES
    )

    return build("drive", "v3", credentials=credentials)
