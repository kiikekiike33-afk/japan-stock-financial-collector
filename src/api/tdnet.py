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
    Scrapes TDnet disclosure PDFs directly from IR Bank.
    Targeting specific document types: 決算短信, 決算説明資料, 決算補足資料, 業績予想の修正
    """
    logger.info(f"Checking IR Bank for {ticker} past {years} years...")
    
    downloaded_files = []
    seen_pdf_urls = set()
    
    # User requested explicit target keywords in the link text
    # 決算短信 (Earnings summary)
    # 決算説明 (Earnings presentation)
    # 決算補足 (Earnings supplementary)
    # 業績予想 or 差異 (Earnings forecast revisions or differences from actuals)
    target_keywords = ["決算短信", "決算説明", "決算補足", "業績予想", "差異"]
    
    # Calculate target cutoff date
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * years)
    
    try:
        # Sleep to avoid hammering IR Bank
        time.sleep(1.5)
        
        # Base url for the company's IR page on IR bank
        url = f"https://irbank.net/{ticker}/ir"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        target_links = []
        # IR Bank lists links in <a> tags, the date info is often inside the url or text
        # Specifically, the URLs look like /6999/140120200422497505
        # We need to find the link, then visit that specific document page to extract the actual PDF link
        
        links = soup.find_all('a')
        for a in links:
            href = a.get('href', '')
            title = a.get_text(strip=True)
            
            if not href.startswith(f"/{ticker}/"):
                continue
                
            if any(kw in title for kw in target_keywords):
                # We found a target disclosure page
                target_links.append((title, urllib.parse.urljoin("https://irbank.net", href)))

        logger.info(f"Found {len(target_links)} raw matched TDnet announcements on IR Bank.")
        
        # Download each targeted PDF
        for i, (title, doc_page_url) in enumerate(target_links):
            
            # Request the specific document page to find the real PDF URL
            try:
                # We parse the YYYYMMDD out of the ending digits (roughly the middle of the ID)
                # Example: /6999/140120200422497505 -> 20200422
                page_id = doc_page_url.split('/')[-1]
                if len(page_id) >= 12:
                    date_part = page_id[4:12] # e.g. "20200422"
                    if not date_part.isdigit() or not (1900 <= int(date_part[:4]) <= 2100):
                         date_part = "YYYYMMDD"
                else:
                    date_part = "YYYYMMDD"
                    
                # Skip if older than requested years
                if date_part != "YYYYMMDD":
                    doc_date = datetime.strptime(date_part, "%Y%m%d")
                    if doc_date < start_date:
                        continue
                
                doc_resp = requests.get(doc_page_url, headers=headers, timeout=15)
                doc_resp.raise_for_status()
                
                # IR bank provides the direct PDF link in the HTML
                pdf_match = re.search(r'https?://f\.irbank\.net/pdf/[a-zA-Z0-9./_-]+\.pdf', doc_resp.text)
                
                if not pdf_match:
                    logger.warning(f"Could not find PDF link on {doc_page_url}")
                    continue
                    
                pdf_url = pdf_match.group(0)
                
                # 重複ダウンロードを防止（同じPDF URLは1回だけ）
                if pdf_url in seen_pdf_urls:
                    logger.info(f"Skipping duplicate PDF URL: {pdf_url}")
                    continue
                seen_pdf_urls.add(pdf_url)
                
                # Standardize Title to match pattern: 決算短信, 決算説明資料, etc.
                clean_title = title.replace("/", "／").replace("\\", "＼").replace(" ", "_")
                if "四半期" in title:
                    clean_title = "四半期" + clean_title
                    
                filename = f"{date_part}_{clean_title}_{ticker}.pdf"
                filepath = os.path.join(TEMP_DOWNLOAD_DIR, filename)
                
                logger.info(f"Downloading TDnet PDF: {filename} from {pdf_url}")
                pdf_dl_resp = requests.get(pdf_url, headers=headers, stream=True, timeout=30)
                pdf_dl_resp.raise_for_status()
                with open(filepath, 'wb') as f:
                    for chunk in pdf_dl_resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                downloaded_files.append(filepath)
                
            except Exception as dl_e:
                logger.warning(f"Failed to process/download TDnet doc {title}: {dl_e}")
                
            time.sleep(1) # Courtesy delay to avoid being banned by IR Bank
            
            if progress_callback:
                progress_callback((i + 1) / max(1, len(target_links)))

    except Exception as e:
        logger.error(f"Error fetching TDnet docs for {ticker}: {e}")
        
    # 重複パスを削除（同一ファイルが複数回リストに追加されるのを防ぐ）
    return list(dict.fromkeys(downloaded_files))
