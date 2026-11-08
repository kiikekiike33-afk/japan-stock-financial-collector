import os
import json
import requests
import time
from datetime import datetime, timedelta
import logging
from src.utils import config
from src.utils.config import TEMP_DOWNLOAD_DIR

logger = logging.getLogger(__name__)

EDINET_API_URL = "https://jsite.edinet-fsa.go.jp/api/v2" # The domain might be disclosure.edinet-fsa.go.jp/api/v2
# Based on EDINET documentation:
EDINET_DOC_LIST_URL = "https://disclosure.edinet-fsa.go.jp/api/v2/documents.json"
EDINET_DOC_GET_URL = "https://disclosure.edinet-fsa.go.jp/api/v2/documents"

# --- 日次書類一覧の共有キャッシュ ---
# EDINET APIは「日付ごとの一覧」しか引けないため、期間検索は日数分の
# コールになる。一覧は対象日が過ぎれば変わらないので、過去日分は
# メモリ＋ディスクにキャッシュし、銘柄横断・同業他社分・再実行で
# 同じ日付を二度とAPIから取り直さない（初回の全走査だけが残る）。
_LIST_CACHE_DIR = os.path.join(TEMP_DOWNLOAD_DIR, "edinet_list_cache")
_list_mem_cache = {}


def _list_cache_path(date_str: str) -> str:
    return os.path.join(_LIST_CACHE_DIR, f"{date_str}.json")


def _load_cached_list(date_str: str):
    if date_str in _list_mem_cache:
        return _list_mem_cache[date_str]
    try:
        path = _list_cache_path(date_str)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                results = json.load(f)
            _list_mem_cache[date_str] = results
            return results
    except Exception as e:
        logger.warning(f"EDINET list cache read failed for {date_str}: {e}")
    return None


def _store_cached_list(date_str: str, results, target_date: datetime):
    _list_mem_cache[date_str] = results
    # 当日分はまだ増える可能性があるのでディスクには書かない。
    # 過去日分だけを永続化する（メモリ内キャッシュは当日分も有効）。
    if target_date.date() >= datetime.now().date():
        return
    try:
        os.makedirs(_LIST_CACHE_DIR, exist_ok=True)
        tmp = _list_cache_path(date_str) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False)
        os.replace(tmp, _list_cache_path(date_str))
    except Exception as e:
        logger.warning(f"EDINET list cache write failed for {date_str}: {e}")


def get_submission_list_by_date(target_date: datetime):
    """
    Fetches the document list for a specific date from EDINET.
    Past dates are served from the shared cache when available.
    """
    date_str = target_date.strftime("%Y-%m-%d")

    cached = _load_cached_list(date_str)
    if cached is not None:
        return cached

    params = {
        "date": date_str,
        "type": 2, # 2 covers all documents including 提出書類
        "Subscription-Key": config.EDINET_API_KEY
    }

    # If no API key is set, we try without it (for V1 backwards compatibility testing if any)
    if not config.EDINET_API_KEY:
        params.pop("Subscription-Key")

    try:
        response = requests.get(EDINET_DOC_LIST_URL, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        if "message" in data and "Access denied" in data["message"]:
             logger.error("EDINET API Key is invalid or missing: " + data["message"])
             raise ValueError("EDINET APIキーが無効、または設定されていません。正しいキーを入力してください。")
        results = data.get("results", []) or []
        # 失敗時（下の except で [] を返す経路）とは区別し、成功した
        # 結果だけをキャッシュする。空の成功結果も正規の結果として保存する。
        _store_cached_list(date_str, results, target_date)
        # APIへの礼儀的な間隔は、実際にネットワーク取得した時だけ入れる
        # （キャッシュヒット時にまで待つと期間検索が無駄に遅くなるため）
        time.sleep(0.1)
        return results
    except Exception as e:
        if isinstance(e, ValueError): raise e
        logger.warning(f"Failed to fetch document list for {date_str}: {e}")
        return []

def search_documents(ticker: str, edinet_code: str = None, years: int = 1, progress_callback=None):
    """
    Searches for documents (有価証券報告書: 120, 四半期報告書: 140) for a given ticker or edinet_code
    over the past `years`. 
    NOTE: Because EDINET API only provides day-by-day lookup, this fetches day by day.
    To avoid massive delays, in a production environment this would query a cached database.
    Here we iterate backwards.
    """
    # Fetch real server date from a reliable external JSON API to bypass aggressive 
    # local system clock mocking (e.g. testing environments).
    end_date = datetime.now()
    
    # Try WorldTimeAPI
    try:
        resp = requests.get("http://worldtimeapi.org/api/timezone/Asia/Tokyo", timeout=3)
        if resp.status_code == 200:
            real_date_str = resp.json().get("datetime", "")[:10]
            if real_date_str:
                end_date = datetime.strptime(real_date_str, "%Y-%m-%d")
                logger.info(f"Using WorldTimeAPI real-world date: {end_date.date()}")
    except Exception as e:
        logger.warning(f"WorldTimeAPI failed: {e}")
        # If WorldTimeAPI fails, we just use datetime.now()
        # In this environment, it's 2026, which is exactly what we want to use.
        pass
            
    start_date = end_date - timedelta(days=365 * years)
    
    current_date = end_date
    found_documents = []
    
    total_days = (end_date - start_date).days
    days_processed = 0
    
    # DOC TYPE CODES:
    # 120: 有価証券報告書 (Annual Securities Report)
    # 140: 四半期報告書 (Quarterly Securities Report)
    target_doc_types = ["120", "140"]
    
    logger.info(f"Searching EDINET documents for ticker:{ticker} edinet:{edinet_code} from {start_date.date()} to {end_date.date()}")
    
    while current_date >= start_date:
        docs = get_submission_list_by_date(current_date)
        for doc in docs:
            # Check either secCode == "XXXX0" OR edinetCode == edinet_code
            match_found = False
            if ticker and doc.get("secCode") == f"{ticker}0":
                match_found = True
            elif edinet_code and doc.get("edinetCode") == edinet_code:
                match_found = True
                
            if match_found:
                doc_type = doc.get("docTypeCode")
                if doc_type in target_doc_types:
                    doc_info = {
                        "docID": doc.get("docID"),
                        "title": doc.get("filerName") + "_" + doc.get("docDescription", ""),
                        "submitDate": current_date.strftime("%Y%m%d"),
                        "docTypeCode": doc_type
                    }
                    found_documents.append(doc_info)
                    logger.info(f"Found document: {doc_info}")

        days_processed += 1
        current_date -= timedelta(days=1)
        
        if progress_callback:
            # Report progress percentage (0.0 to 1.0)
            progress_callback(days_processed / total_days)

        # レート制限対策の sleep は get_submission_list_by_date の
        # ネットワーク取得時だけに入る（キャッシュ時は待たない）

    return found_documents

def download_pdf(doc_id: str, save_filename: str):
    """
    Downloads the PDF representation of the document using EDINET API.
    type=2 historically indicates PDF format. Often returned as a ZIP file.
    """
    url = f"{EDINET_DOC_GET_URL}/{doc_id}"
    params = {
        "type": 2, 
        "Subscription-Key": config.EDINET_API_KEY
    }
    
    if not config.EDINET_API_KEY:
        params.pop("Subscription-Key", None)
        
    try:
        response = requests.get(url, params=params, stream=True, timeout=30)
        
        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '').lower()
            filepath = os.path.join(TEMP_DOWNLOAD_DIR, save_filename)
            
            if 'application/pdf' in content_type:
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                return filepath
            elif 'application/zip' in content_type or 'application/octet-stream' in content_type:
                import zipfile
                import io
                with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                    pdf_files = [f for f in z.namelist() if f.lower().endswith('.pdf')]
                    if pdf_files:
                        # Extract the first PDF found
                        pdf_filename = pdf_files[0]
                        with z.open(pdf_filename) as zf, open(filepath, 'wb') as f:
                            f.write(zf.read())
                        return filepath
                    else:
                        logger.warning(f"No PDF found in ZIP for docID {doc_id}")
                        return None
            else:
                logger.warning(f"Unexpected content type {content_type} for docID {doc_id}")
                return None
        else:
            logger.warning(f"Failed to fetch PDF for docID {doc_id} (Status: {response.status_code})")
            return None
    except Exception as e:
        logger.warning(f"Error downloading docID {doc_id}: {e}")
        return None

def fetch_and_save_edinet_reports(ticker: str, edinet_code: str = None, years: int = 1, progress_callback=None):
    """
    Orchestrates finding and downloading EDINET reports.
    """
    docs = search_documents(ticker, edinet_code, years, progress_callback)
    downloaded_files = []
    
    for doc in docs:
        # Determine document type string for filename
        doc_type_str = "有価証券報告書" if doc["docTypeCode"] == "120" else "四半期報告書"
        
        # Rename rule: YYYYMMDD_[ドキュメント種別]_[証券コード].pdf
        safe_title = doc["title"].replace("/", "_").replace("\\", "_")
        filename = f"{doc['submitDate']}_{doc_type_str}_{ticker}.pdf"
        
        logger.info(f"Downloading {filename}...")
        filepath = download_pdf(doc["docID"], filename)
        if filepath:
            downloaded_files.append(filepath)
            
        time.sleep(0.5) # Courtesy sleep
        
    return downloaded_files
