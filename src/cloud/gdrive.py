import json
import os
import re
import logging
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from src.utils.config import GDRIVE_ROOT_FOLDER_ID, GDRIVE_TOKEN_JSON

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive.file']

def credentials_from_token_value(value):
    """
    token.json 相当の値（JSON文字列 または 辞書）から Credentials を生成します。
    Streamlit Secrets のテーブル形式（辞書）と、環境変数の JSON 文字列の両方に対応します。
    """
    if isinstance(value, str):
        try:
            info = json.loads(value)
        except json.JSONDecodeError as e:
            raise ValueError("GDRIVE_TOKEN_JSON が JSON として読み取れません。token.json の中身をそのまま設定してください。") from e
    elif isinstance(value, dict):
        info = dict(value)
    else:
        raise ValueError("GDRIVE_TOKEN_JSON の形式が不正です（文字列またはテーブルで設定してください）。")
    if not isinstance(info, dict) or not info.get("refresh_token"):
        raise ValueError("GDRIVE_TOKEN_JSON に refresh_token が含まれていません。PCで認可し直して token.json を作り直してください。")
    return Credentials.from_authorized_user_info(info, SCOPES)


def get_gdrive_service():
    """
    Google Drive API v3 のサービスクライアントを取得します。

    認証情報の優先順位:
    1. Secrets / 環境変数 GDRIVE_TOKEN_JSON（Streamlit Cloud 等、ブラウザ認可ができない環境用）
    2. ローカルファイル token.json（PC実行用）
    3. credentials.json による初回対話認可（PC実行専用。token.json を生成して保存）
    """
    creds = None
    from_secrets = False
    if GDRIVE_TOKEN_JSON:
        creds = credentials_from_token_value(GDRIVE_TOKEN_JSON)
        from_secrets = True
    elif os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            if not from_secrets and os.path.exists('token.json'):
                with open('token.json', 'w') as token:
                    token.write(creds.to_json())
        else:
            if not os.path.exists('credentials.json'):
                logger.error("Google Drive の認証情報が見つかりません。")
                raise RuntimeError(
                    "Google Drive の認証情報がありません。ローカルPCでは credentials.json を置いて初回認可してください。"
                    "Streamlit Cloud では Secrets に GDRIVE_TOKEN_JSON（PCで生成した token.json の中身）を設定してください。"
                )
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
