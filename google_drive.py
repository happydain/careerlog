from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import streamlit as st


SCOPES = [
    "https://www.googleapis.com/auth/drive"
]

ROOT_FOLDER_ID = "여기에_CareerLog_폴더ID"


def get_drive_service():

    credentials = Credentials.from_service_account_info(
        dict(st.secrets["google_gsheets"]),
        scopes=SCOPES
    )

    return build(
        "drive",
        "v3",
        credentials=credentials
    )


def find_folder(
    service,
    folder_name,
    parent_id
):

    query = (
        f"name='{folder_name}' "
        f"and '{parent_id}' in parents "
        f"and mimeType='application/vnd.google-apps.folder' "
        f"and trashed=false"
    )

    result = service.files().list(
        q=query,
        fields="files(id,name)"
    ).execute()

    files = result.get("files", [])

    if files:
        return files[0]["id"]

    return None


def create_folder(
    service,
    folder_name,
    parent_id
):

    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id]
    }

    folder = service.files().create(
        body=metadata,
        fields="id"
    ).execute()

    return folder["id"]


def create_agency_folder(
    year,
    agency
):

    service = get_drive_service()

    year_folder_id = find_folder(
        service,
        str(year),
        ROOT_FOLDER_ID
    )

    if not year_folder_id:
        year_folder_id = create_folder(
            service,
            str(year),
            ROOT_FOLDER_ID
        )

    agency_folder_id = find_folder(
        service,
        agency,
        year_folder_id
    )

    if not agency_folder_id:
        agency_folder_id = create_folder(
            service,
            agency,
            year_folder_id
        )

    return agency_folder_id


def create_lecture_folder(
    agency_folder_id,
    lecture_date,
    subject
):

    service = get_drive_service()

    folder_name = (
        f"{lecture_date}_{subject}"
    )

    lecture_folder_id = find_folder(
        service,
        folder_name,
        agency_folder_id
    )

    if not lecture_folder_id:
        lecture_folder_id = create_folder(
            service,
            folder_name,
            agency_folder_id
        )

    return lecture_folder_id


def get_folder_url(folder_id):

    return (
        f"https://drive.google.com/drive/folders/{folder_id}"
    )
