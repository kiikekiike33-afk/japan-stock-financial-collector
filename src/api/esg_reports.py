import os
import requests
import logging
from duckduckgo_search import DDGS
import datetime
from urllib.parse import urlparse
import yfinance as yf
from src.utils.config import TEMP_DOWNLOAD_DIR

logger = logging.getLogger(__name__)

def fetch_integrated_esg_reports(ticker: str, company_name: str = None) -> list:
    """
    Searches DuckDuckGo for the company's Integrated Report or ESG Report PDF.
    Downloads the top match if found. Returns list of downloaded file paths.
    """
    downloaded_files = []
    
    # Try to resolve company name using yfinance if not provided
    if not company_name:
        try:
            yf_ticker = yf.Ticker(f"{ticker}.T")
            company_name = yf_ticker.info.get("longName", "")
            if not company_name:
                 company_name = str(ticker) # Fallback to ticker
        except Exception as e:
            logger.warning(f"Could not resolve company name for {ticker}: {e}")
            company_name = str(ticker)
            
    # Remove Inc, Ltd, etc for cleaner search
    clean_name = company_name.replace("株式会社", "").replace("Inc.", "").replace("Ltd.", "").strip()
    
    queries = [
        f"{clean_name} 統合報告書 filetype:pdf",
        f"{clean_name} ESGデータブック filetype:pdf"
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    pdf_urls = []
    
    try:
        with DDGS() as ddgs:
            for query in queries:
                logger.info(f"Searching: {query}")
                results = list(ddgs.text(query, max_results=2))
                for r in results:
                    href = r.get("href", "")
                    if href.lower().endswith('.pdf'):
                        pdf_urls.append(href)
                        break # Just take the top PDF block for this query
                        
    except Exception as e:
        logger.error(f"DuckDuckGo search failed for {ticker}: {e}")
        
    for idx, url in enumerate(pdf_urls):
        try:
            domain = urlparse(url).netloc
            logger.info(f"Downloading ESG/Integrated Report from {domain}...")
            # We don't want to get stuck on a huge file, timeout 30s
            response = requests.get(url, headers=headers, stream=True, timeout=30)
            
            if response.status_code == 200 and 'application/pdf' in response.headers.get('Content-Type', ''):
                doc_type = "統合報告書" if idx == 0 else "ESGデータ"
                date_str = datetime.datetime.now().strftime("%Y%m%d")
                filename = f"{date_str}_{doc_type}_{ticker}_Web.pdf"
                filepath = os.path.join(TEMP_DOWNLOAD_DIR, filename)
                
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
                            
                downloaded_files.append(filepath)
                logger.info(f"Successfully saved {filename}")
            else:
                logger.warning(f"URL did not return a valid PDF: {url}")
                
        except Exception as e:
             logger.error(f"Failed to download ESG PDF from {url}: {e}")
             
    return downloaded_files

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    docs = fetch_integrated_esg_reports("7203", "トヨタ自動車")
    print(docs)
