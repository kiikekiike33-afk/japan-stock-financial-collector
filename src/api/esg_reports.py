import os
import requests
import logging
from duckduckgo_search import DDGS
import re
from urllib.parse import urlparse
import yfinance as yf
from src.utils.config import TEMP_DOWNLOAD_DIR

logger = logging.getLogger(__name__)

# 最大ダウンロードサイズ（100MB）
MAX_DOWNLOAD_SIZE = 100 * 1024 * 1024


def extract_year_from_text_or_url(text: str) -> str:
    """
    タイトルやURL文字列から西暦4桁（2000〜2099）を抽出します。
    見つからない場合は空文字列を返します。
    """
    matches = re.findall(r'(20[0-9]{2})', text)
    if matches:
        # 最新の年（末尾に近いもの）を採用
        return matches[-1]
    return ""


def fetch_integrated_esg_reports(ticker: str, company_name: str = None) -> list:
    """
    DuckDuckGoで企業の統合報告書・ESGレポートPDFを検索し、検証の上ダウンロードします。
    
    【検証基準（指示05）】
    1. 検索結果のタイトル、URL、スニペットに企業名が含まれているか、または公式サイト等の正規ドメインであること。
    2. 年度をダウンロード日ではなく資料自体の記載年度から抽出し、抽出不能時は「その他」として分類。
    3. ダウンロードサイズ上限（100MB）を設けて過大なファイル取得を中断。
    """
    downloaded_files = []
    
    # 企業名が未指定の場合はyfinance等から解決
    if not company_name:
        try:
            yf_ticker = yf.Ticker(f"{ticker}.T")
            company_name = yf_ticker.info.get("longName", "")
            if not company_name:
                company_name = str(ticker)
        except Exception as e:
            logger.warning(f"銘柄コード {ticker} の企業名解決失敗: {e}")
            company_name = str(ticker)
            
    # 検索用クリーン企業名
    clean_name = company_name.replace("株式会社", "").replace("Inc.", "").replace("Ltd.", "").strip()
    
    queries = [
        f"{clean_name} 統合報告書 filetype:pdf",
        f"{clean_name} ESGデータブック filetype:pdf"
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    candidate_items = []
    
    try:
        with DDGS() as ddgs:
            for q_idx, query in enumerate(queries):
                logger.info(f"ESG資料検索中: {query}")
                results = list(ddgs.text(query, max_results=5))
                for r in results:
                    href = r.get("href", "")
                    title = r.get("title", "")
                    body = r.get("body", "")
                    
                    if not href.lower().endswith('.pdf'):
                        continue
                    
                    # 1. 企業名の検証（タイトル、URL、本文のいずれかに企業名が含まれるか）
                    combined_text = f"{title} {body} {href}".lower()
                    if clean_name.lower() not in combined_text and str(ticker) not in combined_text:
                        logger.warning(f"企業名 '{clean_name}' が見出し・URLに含まれないため除外: {href}")
                        continue
                        
                    doc_type = "統合報告書" if q_idx == 0 else "ESGデータ"
                    candidate_items.append({
                        "url": href,
                        "title": title,
                        "doc_type": doc_type
                    })
                    break  # 各クエリにつき最上位の適合PDFを採用
                    
    except Exception as e:
        logger.error(f"DuckDuckGo検索エラー ({ticker}): {e}")
        
    for item in candidate_items:
        url = item["url"]
        doc_type = item["doc_type"]
        title = item["title"]
        
        try:
            domain = urlparse(url).netloc
            logger.info(f"{clean_name} の {doc_type} をダウンロード中 ({domain})...")
            
            response = requests.get(url, headers=headers, stream=True, timeout=30)
            if response.status_code != 200:
                logger.warning(f"URLアクセス失敗 (Status {response.status_code}): {url}")
                continue
                
            content_type = response.headers.get('Content-Type', '').lower()
            if 'application/pdf' not in content_type and not url.lower().endswith('.pdf'):
                logger.warning(f"PDF形式ではありません (Content-Type: {content_type}): {url}")
                continue
                
            # Content-Lengthヘッダのチェック
            content_length = response.headers.get('Content-Length')
            if content_length and int(content_length) > MAX_DOWNLOAD_SIZE:
                logger.warning(f"ファイルサイズ ({content_length} bytes) が上限 (100MB) を超過したためスキップ: {url}")
                continue
                
            # 年度推定（タイトルおよびURLから）
            extracted_year = extract_year_from_text_or_url(f"{title} {url}")
            if extracted_year:
                date_prefix = f"{extracted_year}0000"
            else:
                date_prefix = "その他"
                logger.info(f"対象年度を特定できなかったため『その他』として保存: {title}")
                
            filename = f"{date_prefix}_{doc_type}_{ticker}_Web.pdf"
            filepath = os.path.join(TEMP_DOWNLOAD_DIR, filename)
            
            total_bytes = 0
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        total_bytes += len(chunk)
                        if total_bytes > MAX_DOWNLOAD_SIZE:
                            logger.warning(f"ダウンロードサイズが100MBを超過したため中断: {url}")
                            f.close()
                            if os.path.exists(filepath):
                                os.remove(filepath)
                            filepath = None
                            break
                        f.write(chunk)
                        
            if filepath and os.path.exists(filepath):
                downloaded_files.append(filepath)
                logger.info(f"保存完了: {filename} ({total_bytes} bytes)")
                
        except Exception as e:
            logger.error(f"ESG PDFのダウンロード失敗 ({url}): {e}")
            
    return downloaded_files
