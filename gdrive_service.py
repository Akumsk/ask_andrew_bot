# gdrive_service.py

import os
import io
import pickle
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']


def get_flow(state):
    """Creates a Flow object for OAuth 2.0 authentication."""
    flow = Flow.from_client_secrets_file(
        'path/to/client_secrets.json',  # Replace with your client secrets JSON file
        scopes=SCOPES,
        redirect_uri='https://yourdomain.com/oauth2callback'  # Replace with your redirect URI
    )
    flow.state = state
    return flow


def get_credentials(user_id):
    """Retrieves credentials for a user from storage."""
    creds_file = f'credentials/{user_id}.pickle'
    if os.path.exists(creds_file):
        with open(creds_file, 'rb') as token:
            creds = pickle.load(token)
        return creds
    else:
        return None


def save_credentials(user_id, creds):
    """Saves credentials for a user to storage."""
    creds_file = f'credentials/{user_id}.pickle'
    os.makedirs('credentials', exist_ok=True)
    with open(creds_file, 'wb') as token:
        pickle.dump(creds, token)


def build_service(user_id):
    """Builds a Google Drive service for a user."""
    creds = get_credentials(user_id)
    if not creds:
        return None
    service = build('drive', 'v3', credentials=creds)
    return service


def list_files_in_folder(service, folder_id):
    """Lists all files in a specified Google Drive folder."""
    query = f"'{folder_id}' in parents and trashed=false"
    results = service.files().list(
        q=query,
        pageSize=1000,
        fields="nextPageToken, files(id, name, mimeType)").execute()
    items = results.get('files', [])
    return items


def download_file(service, file_id, destination):
    """Downloads a file from Google Drive to the specified destination."""
    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(destination, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
        print(f"Download {int(status.progress() * 100)}%.")
    fh.close()


def download_all_files_in_folder(service, folder_id, local_folder):
    """Downloads all files from a Google Drive folder to a local folder."""
    if not os.path.exists(local_folder):
        os.makedirs(local_folder)

    files = list_files_in_folder(service, folder_id)
    for file in files:
        file_id = file['id']
        file_name = file['name']
        destination = os.path.join(local_folder, file_name)
        download_file(service, file_id, destination)
        print(f"Downloaded {file_name} to {destination}")
