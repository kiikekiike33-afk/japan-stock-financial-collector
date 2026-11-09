import os
import json
import requests
import zipfile
import io
import csv
import logging
import time
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# キャッシュファイルのパス（アプリ起動ディレクトリに保存）
_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'edinet_ticker_cache.json')
_CACHE_FILE = os.path.normpath(_CACHE_FILE)

# メモリ上のキャッシュ（プログラム実行中に使い回す）
_ticker_edinet_map = None

def _load_cache_from_file():
    """ローカルJSONキャッシュファイルからマッピングを読み込む"""
    try:
        if os.path.exists(_CACHE_FILE):
            with open(_CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # キャッシュが7日以内なら有効とする
            cached_date = data.get('updated', '')
            if cached_date:
                cache_dt = datetime.strptime(cached_date, '%Y-%m-%d')
                if (datetime.now() - cache_dt).days <= 7:
                    mapping = data.get('mapping', {})
                    if len(mapping) > 100:  # 十分なデータがある場合のみ
                        logger.info(f"ローカルキャッシュから {len(mapping)} 件のマッピングを読み込みました（{cached_date}更新）")
                        return mapping
                    else:
                        logger.info(f"キャッシュのデータが少ない（{len(mapping)}件）。再構築します。")
                else:
                    logger.info(f"キャッシュが古い（{cached_date}）。再構築します。")
    except Exception as e:
        logger.warning(f"キャッシュ読み込みエラー: {e}")
    return None

def _save_cache_to_file(mapping: dict):
    """マッピングをローカルJSONキャッシュファイルに保存する"""
    try:
        data = {
            'updated': datetime.now().strftime('%Y-%m-%d'),
            'count': len(mapping),
            'mapping': mapping
        }
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        with open(_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"マッピング {len(mapping)} 件をキャッシュファイルに保存しました: {_CACHE_FILE}")
    except Exception as e:
        logger.warning(f"キャッシュ保存エラー: {e}")

def _build_mapping_from_edinet_api(days: int = 60):
    """
    EDINET APIの日次ドキュメント一覧を過去N日分走査し、
    secCode（証券コード5桁）→ edinetCode のマッピングを構築する。
    公式APIデータなので最も信頼性が高い。
    """
    from src.utils.config import EDINET_API_KEY
    
    if not EDINET_API_KEY:
        logger.warning("EDINET APIキーが設定されていません。APIマッピング構築をスキップします。")
        return {}
    
    mapping = {}
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    current = end_date - timedelta(days=1)  # 前日から開始（当日はまだデータがない場合がある）
    
    logger.info(f"EDINET APIから証券コードマッピングを構築中...（過去{days}日分）")
    
    api_errors = 0
    while current >= start_date:
        try:
            date_str = current.strftime('%Y-%m-%d')
            r = requests.get(
                'https://api.edinet-fsa.go.jp/api/v2/documents.json',
                params={'date': date_str, 'type': 2, 'Subscription-Key': EDINET_API_KEY},
                timeout=15
            )
            if r.status_code == 200:
                docs = r.json().get('results', [])
                for doc in docs:
                    sec_code = doc.get('secCode')
                    edinet_code = doc.get('edinetCode')
                    if sec_code and edinet_code and len(sec_code) == 5:
                        ticker_4 = sec_code[:4]
                        if ticker_4 not in mapping:
                            mapping[ticker_4] = edinet_code
                api_errors = 0  # 成功したらリセット
            else:
                api_errors += 1
                if api_errors >= 5:
                    logger.warning(f"EDINET API連続エラー。マッピング構築を中断します（{len(mapping)}件取得済み）")
                    break
        except Exception as e:
            api_errors += 1
            logger.warning(f"EDINET API通信エラー ({current.strftime('%Y-%m-%d')}): {e}")
            if api_errors >= 5:
                break
        
        current -= timedelta(days=1)
        time.sleep(0.15)  # API負荷軽減
        
        # 十分なマッピングが集まったら早期終了
        if len(mapping) >= 3000:
            logger.info(f"十分なマッピング数（{len(mapping)}件）に達しました。構築を完了します。")
            break
    
    logger.info(f"EDINET APIからマッピング {len(mapping)} 件を構築しました。")
    return mapping

def _get_static_fallback():
    """最終フォールバック：よく使われる銘柄のハードコード辞書"""
    return {
        "7203": "E02144", "9984": "E04430", "6999": "E01902", "1961": "E00085",
        "6758": "E01176", "8306": "E03606", "7974": "E01111", "6861": "E01948",
        "9432": "E04436", "8035": "E02529", "4063": "E00776", "9983": "E03365",
        "8001": "E02505", "8031": "E02520", "6501": "E01739", "8058": "E02521",
        "8316": "E03608", "7267": "E02188", "6098": "E04907", "4502": "E00936",
        "6981": "E01904", "7741": "E01940", "6902": "E02150", "4568": "E00970",
        "8766": "E03756", "3382": "E03362",
    }

def get_ticker_to_edinet_map(refresh=False):
    """
    証券コード → EDINETコード のマッピングを返す。
    優先順位: 
      1. メモリキャッシュ
      2. ローカルファイルキャッシュ（7日以内）
      3. EDINET API から自動構築（過去60日分）
      4. 静的フォールバック辞書
    """
    global _ticker_edinet_map
    
    # 1. メモリキャッシュ
    if _ticker_edinet_map and not refresh:
        return _ticker_edinet_map
    
    # 2. ローカルファイルキャッシュ
    cached = _load_cache_from_file()
    if cached and not refresh:
        _ticker_edinet_map = cached
        return _ticker_edinet_map
    
    # 3. EDINET APIから構築
    logger.info("EDINET APIからマッピングを構築します（初回 or キャッシュ期限切れ）...")
    api_mapping = _build_mapping_from_edinet_api(days=60)
    
    if len(api_mapping) >= 100:
        # 静的フォールバックもマージしておく（API期間外の銘柄をカバー）
        fallback = _get_static_fallback()
        for k, v in fallback.items():
            if k not in api_mapping:
                api_mapping[k] = v
        _ticker_edinet_map = api_mapping
        _save_cache_to_file(_ticker_edinet_map)
        return _ticker_edinet_map
    
    # 4. 静的フォールバック
    logger.warning("EDINET APIからのマッピング構築に失敗。静的フォールバックを使用します。")
    _ticker_edinet_map = _get_static_fallback()
    return _ticker_edinet_map

_irbank_cache = {}

def _fetch_from_irbank(ticker: str):
    """
    Fetches both EDINET code and company name from IR Bank in a single request,
    with an in-memory cache and a delay to prevent rate-limiting.
    """
    import time
    
    ticker_str = str(ticker)
    if ticker_str in _irbank_cache:
        return _irbank_cache[ticker_str]
        
    result = {"name": "", "edinet_code": None}
    try:
        # Sleep to avoid hammering IR Bank
        time.sleep(1.5)
        
        url = f"https://irbank.net/{ticker_str}/ir"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract Name
            title_tag = soup.find('title')
            if title_tag:
                title = title_tag.text
                if '|' in title:
                    name = title.split('|')[0].replace(ticker_str, '').strip()
                    name = name.replace('()', '').replace('（）', '').strip()
                    name = name.replace('のIR情報・決算資料', '').strip()
                    result["name"] = name
                    
            # Extract EDINET Code
            for a in soup.find_all('a'):
                href = a.get('href', '')
                if href.startswith('/E') and '/edinet' in href:
                    parts = href.split('/')
                    if len(parts) >= 2 and len(parts[1]) == 6:
                        result["edinet_code"] = parts[1]
                        break
                        
        _irbank_cache[ticker_str] = result
        return result
    except Exception as e:
        logger.warning(f"Failed to fetch data from IR Bank for {ticker}: {e}")
        return result

def ticker_to_edinet(ticker):
    """
    Converts a 4-digit ticker code (e.g., '7203') to its EDINET code (e.g., 'E02144').
    First checks the local fallback map, then tries scraping IR Bank.
    """
    try:
        mapping = get_ticker_to_edinet_map()
        edinet_code = mapping.get(str(ticker))
        
        if not edinet_code:
            logger.info(f"Ticker {ticker} not in static map. Fetching from IR Bank...")
            info = _fetch_from_irbank(ticker)
            edinet_code = info.get("edinet_code")
            if edinet_code:
                 logger.info(f"Successfully retrieved EDINET code {edinet_code} for {ticker}")
                 
        return edinet_code
    except Exception as e:
        logger.error(f"Error getting ticker mapping: {e}")
        return None

def get_company_name(ticker: str) -> str:
    """
    Retrieves the Japanese company name from IR Bank.
    """
    info = _fetch_from_irbank(ticker)
    return info.get("name", "")

if __name__ == "__main__":
    t = "6544" 
    e_code = ticker_to_edinet(t)
    c_name = get_company_name(t)
    print(f"Ticker: {t} -> EDINET Code: {e_code}, Name: {c_name}")
