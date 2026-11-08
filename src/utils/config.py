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

# Directory to save downloaded PDFs temporarily
TEMP_DOWNLOAD_DIR = _get_secret_or_env("TEMP_DOWNLOAD_DIR", "./temp_downloads")

if not os.path.exists(TEMP_DOWNLOAD_DIR):
    os.makedirs(TEMP_DOWNLOAD_DIR)
