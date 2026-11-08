import os
import re
import logging
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from src.utils.config import GDRIVE_ROOT_FOLDER_ID

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive.file']

def get_gdrive_service():
    """
    Google Drive API v3 のサービスクライアントを取得します。
    """
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                logger.error("credentials.json が見つかりません。")
                raise FileNotFoundError("Google Drive API OAuth 認証ファイル (credentials.json) が存在しません。")
            
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('drive', 'v3', credentials=creds)

def get_or_create_folder(service, folder_name: str, parent_id: str = None):
    """
    指定されたフォルダ名が存在するか確認し、存在しなければ作成してそのIDを返します。
    クエリ内の特殊文字エスケープおよび nextPageToken ページングに対応しています。
    """
    safe_folder_name = folder_name.replace("'", "\\'")
    query = f"mimeType='application/vnd.google-apps.folder' and name='{safe_folder_name}' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
        
    page_token = None
    existing_folder_id = None
    
    while True:
        results = service.files().list(
            q=query,
            spaces='drive',
            fields='nextPageToken, files(id, name)',
            pageToken=page_token
        ).execute()
        
        files = results.get('files', [])
        if files:
            existing_folder_id = files[0]['id']
            break
            
        page_token = results.get('nextPageToken')
        if not page_token:
            break
            
    if existing_folder_id:
        return existing_folder_id
        
    # 存在しない場合は新規作成
    folder_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    if parent_id:
        folder_metadata['parents'] = [parent_id]
        
    file = service.files().create(body=folder_metadata, fields='id').execute()
    new_id = file.get('id')
    logger.info(f"Google Driveに新規フォルダを作成しました: '{folder_name}' (ID: {new_id})")
    return new_id

def get_existing_files_in_folder(service, folder_id: str) -> dict:
    """
    指定フォルダ内の既存ファイル一覧を {filename: file_id} の辞書形式で取得します（ページング対応）。
    """
    existing_files = {}
    query = f"'{folder_id}' in parents and trashed=false"
    page_token = None
    
    while True:
        results = service.files().list(
            q=query,
            spaces='drive',
            fields='nextPageToken, files(id, name)',
            pageToken=page_token
        ).execute()
        
        for f in results.get('files', []):
            existing_files[f['name']] = f['id']
            
        page_token = results.get('nextPageToken')
        if not page_token:
            break
            
    return existing_files

def upload_to_drive(ticker: str, filepaths: list, progress_callback=None, group_folder_name: str = None):
    """
    Google Driveへファイルをアップロードします。
    戻り値: (folder_link, file_links) のタプル（空時は ("", [])）
    
    【改修点（指示06）】
    - ハードコードIDを廃止し環境変数 GDRIVE_ROOT_FOLDER_ID を使用（未設定時はマイドライブ直下）
    - 既存ファイルがある場合は重複アップロードをスキップ
    - 戻り値を常に (str, list) に統一
    """
    if not filepaths:
        logger.warning("Google Driveへのアップロード対象ファイルがありません。")
        return "", []
        
    try:
        service = get_gdrive_service()
        
        # 環境変数から親フォルダIDを取得（未設定時はマイドライブ直下 = None）
        root_parent_id = GDRIVE_ROOT_FOLDER_ID if GDRIVE_ROOT_FOLDER_ID else None
        
        if group_folder_name:
            folder_name = group_folder_name
        else:
            folder_name = f"{ticker}_NotebookLMソース"
            
        folder_id = get_or_create_folder(service, folder_name, parent_id=root_parent_id)
        
        folder_metadata = service.files().get(fileId=folder_id, fields='webViewLink').execute()
        folder_link = folder_metadata.get('webViewLink', '')

        # 既存ファイルの確認（重複アップロード防止）
        existing_files = get_existing_files_in_folder(service, folder_id)
        skipped_count = 0

        file_links = []
        total_files = len(filepaths)
        
        for i, filepath in enumerate(filepaths):
            if not os.path.exists(filepath):
                logger.warning(f"ファイルが存在しないためスキップ: {filepath}")
                continue
                
            filename = os.path.basename(filepath)
            
            # 同名ファイルが既にアップロード先にある場合はスキップ
            if filename in existing_files:
                file_id = existing_files[filename]
                file_links.append(f"https://drive.google.com/file/d/{file_id}/view")
                logger.info(f"同名ファイルが既に存在するためアップロードをスキップ: {filename}")
                skipped_count += 1
                if progress_callback:
                    progress_callback((i + 1) / total_files)
                continue
                
            file_metadata = {
                'name': filename,
                'parents': [folder_id]
            }
            
            media = MediaFileUpload(filepath, resumable=True)
            logger.info(f"{filename} を Google Drive にアップロード中...")
            file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            file_id = file.get('id')
            logger.info(f"アップロード完了: {filename} (ID: {file_id})")
            
            file_links.append(f"https://drive.google.com/file/d/{file_id}/view")
            
            if progress_callback:
                progress_callback((i + 1) / total_files)
                
        if skipped_count > 0:
            logger.info(f"重複スキップ件数: {skipped_count} / {total_files} 件")
            
        return folder_link, file_links
        
    except Exception as e:
        logger.error(f"Google Driveアップロード失敗: {e}")
        raise

def get_file_links_from_folder_url(folder_url: str):
    """
    指定されたGoogle DriveフォルダURL内のすべてのファイルのURLリストを取得します（ページング対応）。
    """
    try:
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
        except Exception as e:
            logger.warning(f"フォルダ情報取得エラー (ID: {folder_id}): {e}")
            raise PermissionError(
                "指定されたフォルダにアクセスできませんでした。\n"
                "※本アプリの認証スコープ（drive.file）では、本アプリ自身が作成したファイル・フォルダのみ操作可能です。"
                "外部で手動作成されたフォルダや権限のないフォルダは読み込めない場合があります。"
            )
            
        query = f"'{folder_id}' in parents and trashed=false"
        file_links = []
        page_token = None
        
        while True:
            results = service.files().list(
                q=query,
                spaces='drive',
                fields='nextPageToken, files(id, name)',
                pageToken=page_token
            ).execute()
            
            for item in results.get('files', []):
                file_id = item.get('id')
                file_links.append(f"https://drive.google.com/file/d/{file_id}/view")
                
            page_token = results.get('nextPageToken')
            if not page_token:
                break
                
        if not file_links:
            logger.info(f"フォルダ内にファイルが見つかりませんでした (ID: {folder_id})")
            
        return file_links, folder_name
        
    except Exception as e:
        logger.error(f"フォルダからのファイル取得に失敗しました: {e}")
        raise e
