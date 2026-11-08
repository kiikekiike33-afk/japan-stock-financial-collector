import requests
from bs4 import BeautifulSoup
import re
import logging

logger = logging.getLogger(__name__)

def get_competitors(ticker: str) -> list:
    """
    株探（Kabutan）から正確な競合他社（同業他社）を取得する。
    2段階で抽出:
      1. 株探の「比較される銘柄」セクション（最も正確な直接競合）
      2. 同一業種の上場銘柄一覧（複数ページ）から時価総額上位を補完
    Returns a list of 4-digit ticker strings, e.g. ['7267', '7201', '7211'].
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept-Language': 'ja-JP,ja;q=0.9',
    }
    
    peers = []
    seen = {str(ticker)}  # 自分自身は除外
    
    try:
        # === Step 1: 株探メインページから「比較される銘柄」を取得 ===
        url = f"https://kabutan.jp/stock/?code={ticker}"
        r = requests.get(url, headers=headers, timeout=10)
        
        if r.status_code != 200:
            logger.warning(f"Kabutan returned {r.status_code} for {ticker}")
            return peers
            
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # 「比較される銘柄」のdt/ddペアから直接競合を抽出
        dt_tag = soup.find('dt', string=re.compile(r'比較される銘柄'))
        if dt_tag:
            dd_tag = dt_tag.find_next_sibling('dd')
            if dd_tag:
                for a in dd_tag.find_all('a'):
                    href = a.get('href', '')
                    m = re.search(r'code=(\d{4})', href)
                    if m:
                        code = m.group(1)
                        if code not in seen:
                            peers.append(code)
                            seen.add(code)
                            
        logger.info(f"Kabutan direct peers for {ticker}: {peers}")
        
        # === Step 2: 同一業種の銘柄一覧から時価総額上位を補完 ===
        # 業種リンクを取得（例: /themes/?industry=17&market=1）
        sector_link = None
        for a in soup.find_all('a'):
            href = a.get('href', '')
            if '/themes/?industry=' in href and 'market=' in href:
                sector_link = href
                break
                
        if sector_link and len(peers) < 5:
            if not sector_link.startswith('http'):
                sector_link = 'https://kabutan.jp' + sector_link
            
            # ページネーション対応: 全ページのデータを収集    
            logger.info(f"Fetching sector peers from: {sector_link}")
            all_sector_stocks = []
            
            for page in range(1, 4):  # 最大3ページ
                page_url = sector_link + f"&capitalization=-1&dispmode=normal&stc=&stm=0&page={page}"
                r2 = requests.get(page_url, headers=headers, timeout=10)
                if r2.status_code != 200:
                    break
                    
                soup2 = BeautifulSoup(r2.text, 'html.parser')
                page_found = False
                
                for table in soup2.find_all('table'):
                    ths = table.find_all('th')
                    th_texts = [th.get_text(strip=True) for th in ths]
                    if 'コード' not in th_texts:
                        continue
                    
                    for tr in table.find_all('tr'):
                        tds = tr.find_all('td')
                        if len(tds) < 6:
                            continue
                        code_link = tr.find('a', href=re.compile(r'code=\d{4}'))
                        if not code_link:
                            continue
                        m = re.search(r'code=(\d{4})', code_link.get('href', ''))
                        if not m:
                            continue
                        code = m.group(1)
                        # 市場指数（0000〜0999）と自分自身を除外
                        if int(code) < 1000 or code in seen:
                            continue
                        name = tds[1].get_text(strip=True) if len(tds) > 1 else ''
                        all_sector_stocks.append(code)
                        page_found = True
                
                if not page_found:
                    break  # これ以上ページがない
            
            # 時価総額順にソートするため、yfinanceで市場価値を取得
            if all_sector_stocks:
                try:
                    import yfinance as yf
                    stocks_with_mcap = []
                    for code in all_sector_stocks:
                        try:
                            t = yf.Ticker(f"{code}.T")
                            mcap = t.info.get('marketCap', 0) or 0
                            stocks_with_mcap.append((code, mcap))
                        except Exception:
                            stocks_with_mcap.append((code, 0))
                    
                    # 時価総額の降順でソート
                    stocks_with_mcap.sort(key=lambda x: x[1], reverse=True)
                    
                    remaining = 5 - len(peers)
                    for code, mcap in stocks_with_mcap[:remaining]:
                        if code not in seen:
                            peers.append(code)
                            seen.add(code)
                            
                    logger.info(f"Added sector peers sorted by market cap: {[s[0] for s in stocks_with_mcap[:remaining]]}")
                    
                except ImportError:
                    # yfinanceが無い場合はそのまま追加
                    remaining = 5 - len(peers)
                    for code in all_sector_stocks[:remaining]:
                        if code not in seen:
                            peers.append(code)
                            seen.add(code)
                
    except Exception as e:
        logger.warning(f"Error fetching competitors for {ticker}: {e}")
    
    return peers[:5]

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = get_competitors("7203")
    print("Competitors for 7203 (Toyota):", result)
