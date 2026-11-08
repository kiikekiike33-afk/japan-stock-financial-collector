import os
import json
import requests
import time
from datetime import datetime, timedelta
import logging
from zoneinfo import ZoneInfo
from src.utils import config
from src.utils.config import TEMP_DOWNLOAD_DIR

logger = logging.getLogger(__name__)

EDINET_API_URL = "https://disclosure.edinet-fsa.go.jp/api/v2"
EDINET_DOC_LIST_URL = "https://disclosure.edinet-fsa.go.jp/api/v2/documents.json"
EDINET_DOC_GET_URL = "https://disclosure.edinet-fsa.go.jp/api/v2/documents"

# 最大ダウンロード・ZIP展開サイズ上限（100MB）
MAX_DOWNLOAD_SIZE = 100 * 1024 * 1024

# --- 日次書類一覧の共有キャッシュ ---
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
    now_tokyo = get_current_tokyo_date()
    if target_date.date() >= now_tokyo.date():
        return
    try:
        os.makedirs(_LIST_CACHE_DIR, exist_ok=True)
        tmp = _list_cache_path(date_str) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False)
        os.replace(tmp, _list_cache_path(date_str))
    except Exception as e:
        logger.warning(f"EDINET list cache write failed for {date_str}: {e}")


def get_current_tokyo_date() -> datetime:
    """
    東京タイムゾーン（Asia/Tokyo）の現在日時を安全に取得します（WorldTimeAPI廃止）。
    """
    try:
        return datetime.now(ZoneInfo("Asia/Tokyo")).replace(tzinfo=None)
    except Exception:
        return datetime.now()


def get_submission_list_by_date(target_date: datetime):
    """
    指定された日付のEDINET提出書類一覧を取得します。
    過去日分は共有キャッシュから即座に返却されます。
    """
    date_str = target_date.strftime("%Y-%m-%d")

    cached = _load_cached_list(date_str)
    if cached is not None:
        return cached

    params = {
        "date": date_str,
        "type": 2,
        "Subscription-Key": config.EDINET_API_KEY
    }

    if not config.EDINET_API_KEY:
        params.pop("Subscription-Key", None)

    try:
        response = requests.get(EDINET_DOC_LIST_URL, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        if "message" in data and "Access denied" in data["message"]:
            logger.error("EDINET API Key is invalid or missing: " + data["message"])
            raise ValueError("EDINET APIキーが無効、または設定されていません。正しいキーを入力してください。")
        results = data.get("results", []) or []
        _store_cached_list(date_str, results, target_date)
        time.sleep(0.1)  # 礼儀的なウェイト
        return results
    except Exception as e:
        if isinstance(e, ValueError):
            raise e
        logger.warning(f"Failed to fetch document list for {date_str}: {e}")
        return []


def search_documents(ticker: str, edinet_code: str = None, years: int = 1, progress_callback=None):
    """
    指定銘柄（証券コードまたはEDINETコード）の報告書（有報:120, 四半期報:140）を過去指定年数分検索します。
    """
    end_date = get_current_tokyo_date()
    start_date = end_date - timedelta(days=365 * years)
    
    current_date = end_date
    found_documents = []
    
    total_days = max(1, (end_date - start_date).days)
    days_processed = 0
    
    target_doc_types = ["120", "140"]
    logger.info(f"EDINET書類検索: ticker={ticker}, edinet={edinet_code} ({start_date.date()} 〜 {end_date.date()})")
    
    while current_date >= start_date:
        docs = get_submission_list_by_date(current_date)
        for doc in docs:
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
                        "title": (doc.get("filerName") or "") + "_" + (doc.get("docDescription") or ""),
                        "submitDate": current_date.strftime("%Y%m%d"),
                        "docTypeCode": doc_type
                    }
                    found_documents.append(doc_info)
                    logger.info(f"対象書類を検出: {doc_info['docID']} {doc_info['title']}")

        days_processed += 1
        current_date -= timedelta(days=1)
        
        if progress_callback:
            progress_callback(days_processed / total_days)

    return found_documents


def download_pdf(doc_id: str, save_filename: str):
    """
    EDINET APIからPDF形式で書類をダウンロードします。
    ZIP形式で返却された場合は安全に展開してPDFを抽出します（サイズ上限あり）。
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
            
            # コンテンツサイズの事前確認
            content_length = response.headers.get('Content-Length')
            if content_length and int(content_length) > MAX_DOWNLOAD_SIZE:
                logger.warning(f"書類 {doc_id} のサイズ ({content_length} bytes) が上限 (100MB) を超過したためスキップします。")
                return None
            
            if 'application/pdf' in content_type:
                total_bytes = 0
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        total_bytes += len(chunk)
                        if total_bytes > MAX_DOWNLOAD_SIZE:
                            logger.warning(f"書類 {doc_id} のDLサイズが100MBを超過したため中断します。")
                            f.close()
                            if os.path.exists(filepath):
                                os.remove(filepath)
                            return None
                        f.write(chunk)
                return filepath
                
            elif 'application/zip' in content_type or 'application/octet-stream' in content_type:
                import zipfile
                import io
                
                zip_bytes = io.BytesIO()
                total_bytes = 0
                for chunk in response.iter_content(chunk_size=8192):
                    total_bytes += len(chunk)
                    if total_bytes > MAX_DOWNLOAD_SIZE:
                        logger.warning(f"書類 {doc_id} のZIPサイズが100MBを超過したため中断します。")
                        return None
                    zip_bytes.write(chunk)
                    
                zip_bytes.seek(0)
                with zipfile.ZipFile(zip_bytes) as z:
                    pdf_files = [f for f in z.namelist() if f.lower().endswith('.pdf')]
                    if pdf_files:
                        pdf_filename = pdf_files[0]
                        # 展開後のサイズも上限チェック
                        info = z.getinfo(pdf_filename)
                        if info.file_size > MAX_DOWNLOAD_SIZE:
                            logger.warning(f"書類 {doc_id} 内のPDF解凍サイズ ({info.file_size} bytes) が100MBを超過したため中断します。")
                            return None
                        with z.open(pdf_filename) as zf, open(filepath, 'wb') as f:
                            f.write(zf.read())
                        return filepath
                    else:
                        logger.warning(f"docID {doc_id} のZIP内にPDFが見つかりませんでした。")
                        return None
            else:
                logger.warning(f"予期しないContent-Type ({content_type}): docID {doc_id}")
                return None
        else:
            logger.warning(f"PDF取得失敗: docID {doc_id} (Status: {response.status_code})")
            return None
    except Exception as e:
        logger.warning(f"docID {doc_id} のダウンロード処理中にエラー: {e}")
        return None


def fetch_and_save_edinet_reports(ticker: str, edinet_code: str = None, years: int = 1, progress_callback=None):
    """
    EDINET報告書を検索・ダウンロードし、重複上書きを防ぐdocID付きファイル名で保存します。
    命名規則: {submitDate}_{doc_type_str}_{docID}_{ticker}.pdf
    """
    docs = search_documents(ticker, edinet_code, years, progress_callback)
    downloaded_files = []
    
    for doc in docs:
        doc_type_str = "有価証券報告書" if doc["docTypeCode"] == "120" else "四半期報告書"
        
        # 命名規則: YYYYMMDD_[ドキュメント種別]_[docID]_[証券コード].pdf
        # docIDを含めることで同日・同種別でもファイル名の衝突・上書きを防止
        filename = f"{doc['submitDate']}_{doc_type_str}_{doc['docID']}_{ticker}.pdf"
        
        logger.info(f"EDINET書類ダウンロード中: {filename}...")
        filepath = download_pdf(doc["docID"], filename)
        if filepath:
            downloaded_files.append(filepath)
            
        time.sleep(0.5)
        
    return downloaded_files
