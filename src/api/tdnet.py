import os
import time
import logging
import requests
from bs4 import BeautifulSoup
import re
import urllib.parse
from datetime import datetime, timedelta
from src.utils.config import TEMP_DOWNLOAD_DIR

logger = logging.getLogger(__name__)

def search_and_download_tdnet_docs(ticker: str, years: int = 1, progress_callback=None):
    """
    IR BankからTDnet適時開示PDFを直接検索・ダウンロードします。
    対象ドキュメント種別: 決算短信, 決算説明資料, 決算補足資料, 業績予想の修正, 差異
    
    【取得範囲に関する仕様（実地調査済み）】
    IR Bankの各企業IRページ (https://irbank.net/{ticker}/ir) にはページ送りの仕組みはなく、
    過去約10年分（2013年以降）の開示リンクが単一ページに全件掲載されています。
    そのため、取得範囲はIR Bankの当該ページに掲載されている全件となります。
    """
    logger.info(f"IR Bankから銘柄コード {ticker} の過去 {years} 年分のTDnet開示を検索中...")
    
    downloaded_files = []
    seen_pdf_urls = set()
    rejected_count = 0  # PDF検証で弾かれた件数
    
    # 対象キーワード
    target_keywords = ["決算短信", "決算説明", "決算補足", "業績予想", "差異"]
    
    # 取得期間の足切り日時
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * years)
    
    try:
        time.sleep(1.5)  # 負荷軽減のための待機
        
        url = f"https://irbank.net/{ticker}/ir"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        target_links = []
        
        links = soup.find_all('a')
        for a in links:
            href = a.get('href', '')
            title = a.get_text(strip=True)
            
            if not href.startswith(f"/{ticker}/"):
                continue
                
            if any(kw in title for kw in target_keywords):
                target_links.append((title, urllib.parse.urljoin("https://irbank.net", href)))

        logger.info(f"IR Bank上で合致する適時開示リンクを {len(target_links)} 件検出しました。")
        
        # 各PDFのダウンロード処理
        for i, (title, doc_page_url) in enumerate(target_links):
            try:
                # URL末尾のIDから日付（YYYYMMDD）を抽出
                page_id = doc_page_url.split('/')[-1]
                if len(page_id) >= 12:
                    date_part = page_id[4:12]
                    if not date_part.isdigit() or not (1900 <= int(date_part[:4]) <= 2100):
                        date_part = "YYYYMMDD"
                else:
                    date_part = "YYYYMMDD"
                    
                # 指定年数より古い開示はスキップ
                if date_part != "YYYYMMDD":
                    doc_date = datetime.strptime(date_part, "%Y%m%d")
                    if doc_date < start_date:
                        continue
                
                doc_resp = requests.get(doc_page_url, headers=headers, timeout=15)
                doc_resp.raise_for_status()
                
                pdf_match = re.search(r'https?://f\.irbank\.net/pdf/[a-zA-Z0-9./_-]+\.pdf', doc_resp.text)
                if not pdf_match:
                    logger.warning(f"PDFリンクが見つかりませんでした: {doc_page_url}")
                    continue
                    
                pdf_url = pdf_match.group(0)
                
                # 重複ダウンロードを防止
                if pdf_url in seen_pdf_urls:
                    logger.info(f"重複PDF URLをスキップ: {pdf_url}")
                    continue
                seen_pdf_urls.add(pdf_url)
                
                # タイトルの正規化
                clean_title = title.replace("/", "／").replace("\\", "＼").replace(" ", "_")
                if "四半期" in title:
                    clean_title = "四半期" + clean_title
                    
                filename = f"{date_part}_{clean_title}_{ticker}.pdf"
                filepath = os.path.join(TEMP_DOWNLOAD_DIR, filename)
                
                logger.info(f"TDnet PDFダウンロード開始: {filename} ({pdf_url})")
                pdf_dl_resp = requests.get(pdf_url, headers=headers, stream=True, timeout=30)
                pdf_dl_resp.raise_for_status()
                
                content_type = pdf_dl_resp.headers.get('Content-Type', '').lower()
                
                # 先頭チャンクを取得してマジックナンバー (%PDF) を検証
                first_chunk = next(pdf_dl_resp.iter_content(chunk_size=8192), None)
                if not first_chunk or not first_chunk.startswith(b'%PDF'):
                    logger.warning(f"PDFヘッダ検証失敗（%PDFマジックナンバーなし、Content-Type: {content_type}）。保存を中止します: {pdf_url}")
                    rejected_count += 1
                    continue
                
                with open(filepath, 'wb') as f:
                    f.write(first_chunk)
                    for chunk in pdf_dl_resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            
                downloaded_files.append(filepath)
                
            except Exception as dl_e:
                logger.warning(f"TDnet開示資料の処理失敗 ({title}): {dl_e}")
                
            time.sleep(1) # IR Bankへのアクセス負荷軽減
            
            if progress_callback:
                progress_callback((i + 1) / max(1, len(target_links)))

    except Exception as e:
        logger.error(f"TDnet開示資料の取得エラー ({ticker}): {e}")
        
    if rejected_count > 0:
        logger.warning(f"【検証集計】PDF検証で弾かれた不正ファイル数: {rejected_count} 件")
        
    # 重複パスを削除して返却
    return list(dict.fromkeys(downloaded_files))
