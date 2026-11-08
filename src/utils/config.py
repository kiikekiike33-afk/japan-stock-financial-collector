import os
from dotenv import load_dotenv

load_dotenv()

# Streamlit secrets フォールバック
def _get_secret_or_env(key: str, default: str = "") -> str:
    val = os.getenv(key)
    if not val:
        try:
            import streamlit as st
            val = st.secrets.get(key, default)
        except Exception:
            val = default
    return val or default

# EDINET API Key
EDINET_API_KEY = _get_secret_or_env("EDINET_API_KEY", "")

# Google Drive Root Folder ID (未設定の場合はマイドライブ直下に保存)
GDRIVE_ROOT_FOLDER_ID = _get_secret_or_env("GDRIVE_ROOT_FOLDER_ID", "")

# Google Drive 認証トークン（token.json の中身）。Streamlit Cloud 等の
# ブラウザ認可ができない環境では、Secrets / 環境変数でこれを渡す。
# 値は文字列（JSON）でも辞書（Secrets のテーブル形式）でもよい。
GDRIVE_TOKEN_JSON = _get_secret_or_env("GDRIVE_TOKEN_JSON", "")

# Directory to save downloaded PDFs temporarily
TEMP_DOWNLOAD_DIR = _get_secret_or_env("TEMP_DOWNLOAD_DIR", "./temp_downloads")

if not os.path.exists(TEMP_DOWNLOAD_DIR):
    os.makedirs(TEMP_DOWNLOAD_DIR)
