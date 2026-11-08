import os
from dotenv import load_dotenv

load_dotenv()

# EDINET API Key
EDINET_API_KEY = os.getenv("EDINET_API_KEY", "")

# Directory to save downloaded PDFs temporarily
TEMP_DOWNLOAD_DIR = os.getenv("TEMP_DOWNLOAD_DIR", "./temp_downloads")

if not os.path.exists(TEMP_DOWNLOAD_DIR):
    os.makedirs(TEMP_DOWNLOAD_DIR)
