import os
import logging
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def get_gdrive_service():
    """Shows basic usage of the Drive v3 API.
    Prints the names and ids of the first 10 files the user has access to.
    """
    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                logger.error("credentials.json not found. Please follow README instructions to create one.")
                raise FileNotFoundError("Google Drive API OAuth credentials (credentials.json) missing.")
            
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('drive', 'v3', credentials=creds)

def get_or_create_folder(service, folder_name: str, parent_id: str = None):
    """
    Checks if a folder with `folder_name` exists (under `parent_id` if specified).
    Returns the ID of the folder. If not found, creates it.
    """
    query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
        
    results = service.files().list(q=query, spaces='drive', fields='nextPageToken, files(id, name)').execute()
    items = results.get('files', [])
    
    if items:
        # Folder exists
        return items[0]['id']
    else:
        # Create folder
        folder_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if parent_id:
            folder_metadata['parents'] = [parent_id]
            
        file = service.files().create(body=folder_metadata, fields='id').execute()
        logger.info(f"Created Google Drive folder '{folder_name}' (ID: {file.get('id')})")
        return file.get('id')

def upload_to_drive(ticker: str, filepaths: list, progress_callback=None, group_folder_name: str = None):
    """
    Google Driveへファイルをアップロードする。
    group_folder_name指定時: [root] / [group_folder_name] に直接アップロード
    未指定時: [root] / [ticker]_NotebookLMソース にアップロード
    """
    if not filepaths:
        logger.warning("No files provided for Google Drive upload.")
        return None
        
    try:
        service = get_gdrive_service()
        
        # ユーザー指定のルートフォルダ
        root_parent_id = "1te4F2oDZECvcQV9sY-5MHKcypr0MxYcf"
        
        if group_folder_name:
            # グループフォルダに直接アップロード（個別サブフォルダは作らない）
            folder_name = group_folder_name
            folder_id = get_or_create_folder(service, folder_name, parent_id=root_parent_id)
        else:
            # 単一銘柄の場合は従来通り個別フォルダを作成
            folder_name = f"{ticker}_NotebookLMソース"
            folder_id = get_or_create_folder(service, folder_name, parent_id=root_parent_id)
        # To return the link:
        folder_metadata = service.files().get(fileId=folder_id, fields='webViewLink').execute()
        folder_link = folder_metadata.get('webViewLink')

        total_files = len(filepaths)
        
        # 2. Upload files
        file_links = []
        for i, filepath in enumerate(filepaths):
            if not os.path.exists(filepath):
                logger.warning(f"File not found, skipping upload: {filepath}")
                continue
                
            filename = os.path.basename(filepath)
            
            file_metadata = {
                'name': filename,
                'parents': [folder_id]
            }
            
            media = MediaFileUpload(filepath, resumable=True)
            logger.info(f"Uploading {filename} to {folder_name}...")
            file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            file_id = file.get('id')
            logger.info(f"Uploaded {filename} (ID: {file_id})")
            
            file_links.append(f"https://drive.google.com/file/d/{file_id}/view")
            
            if progress_callback:
                progress_callback((i + 1) / total_files)
                
        return folder_link, file_links
        
    except Exception as e:
        logger.error(f"Failed to upload to Google Drive: {e}")
        raise

import re

def get_file_links_from_folder_url(folder_url: str):
    """
    指定されたGoogle DriveフォルダURL内のすべてのファイルのURLリストを取得する。
    """
    try:
        # URLからフォルダIDを抽出
        match = re.search(r'folders/([a-zA-Z0-9_-]+)', folder_url)
        if not match:
            match = re.search(r'id=([a-zA-Z0-9_-]+)', folder_url)
            
        if not match:
            raise ValueError("無効なGoogle DriveフォルダURLです。")
            
        folder_id = match.group(1)
        
        service = get_gdrive_service()
        try:
            folder_metadata = service.files().get(fileId=folder_id, fields='name').execute()
            folder_name = folder_metadata.get('name', folder_id)
        except Exception:
            folder_name = folder_id
        query = f"'{folder_id}' in parents and trashed=false"
        
        # フォルダ内のファイルを取得
        results = service.files().list(q=query, spaces='drive', fields='nextPageToken, files(id, name)').execute()
        items = results.get('files', [])
        
        file_links = []
        for item in items:
            file_id = item.get('id')
            file_links.append(f"https://drive.google.com/file/d/{file_id}/view")
            
        return file_links, folder_name
        
    except Exception as e:
        logger.error(f"Failed to fetch files from folder: {e}")
        raise e
