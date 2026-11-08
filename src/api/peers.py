import requests
from bs4 import BeautifulSoup
import re
import logging

logger = logging.getLogger(__name__)

def get_competitors(ticker: str) -> list:
    """
    株探（Kabutan）から正確な競合他社（同業他社）を取得します。
    2段階で抽出:
      1. 株探の「比較される銘柄」セクション（直接競合）
      2. 同一業種の上場銘柄一覧から上位を補完（yfinanceのAPI負荷軽減対応済み）
    Returns: 4桁の証券コードのリスト（例: ['7267', '7201', '7211']）
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
            logger.warning(f"株探アクセス失敗 (Status {r.status_code}): {ticker}")
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
                            
        logger.info(f"株探直接競合 ({ticker}): {peers}")
        
        # === Step 2: 5件未満の場合、同一業種の銘柄一覧から上位を補完 ===
        sector_link = None
        for a in soup.find_all('a'):
            href = a.get('href', '')
            if '/themes/?industry=' in href and 'market=' in href:
                sector_link = href
                break
                
        if sector_link and len(peers) < 5:
            if not sector_link.startswith('http'):
                sector_link = 'https://kabutan.jp' + sector_link
            
            logger.info(f"業種別銘柄一覧を取得中: {sector_link}")
            all_sector_stocks = []
            
            # 負荷軽減のため1ページ目（最大上位30件）のみを取得
            page_url = sector_link + "&capitalization=-1&dispmode=normal&stc=&stm=0&page=1"
            r2 = requests.get(page_url, headers=headers, timeout=10)
            if r2.status_code == 200:
                soup2 = BeautifulSoup(r2.text, 'html.parser')
                for table in soup2.find_all('table'):
                    ths = table.find_all('th')
                    th_texts = [th.get_text(strip=True) for th in ths]
                    if 'コード' not in th_texts:
                        continue
                    
                    for tr in table.find_all('tr'):
                        code_link = tr.find('a', href=re.compile(r'code=\d{4}'))
                        if not code_link:
                            continue
                        m = re.search(r'code=(\d{4})', code_link.get('href', ''))
                        if not m:
                            continue
                        code = m.group(1)
                        if int(code) < 1000 or code in seen:
                            continue
                        all_sector_stocks.append(code)
            
            # 【改修点（指示11）】全銘柄に.infoを叩くのをやめ、必要件数＋α（最大8件）のみに絞って軽量取得
            remaining = 5 - len(peers)
            candidates = all_sector_stocks[:max(8, remaining * 2)]
            
            if candidates:
                try:
                    import yfinance as yf
                    stocks_with_mcap = []
                    for code in candidates:
                        try:
                            t = yf.Ticker(f"{code}.T")
                            # fast_info を使用して高速に時価総額を取得（.info より大幅に軽量）
                            mcap = getattr(t.fast_info, 'market_cap', None)
                            if mcap is None:
                                mcap = t.info.get('marketCap', 0) or 0
                            stocks_with_mcap.append((code, mcap))
                        except Exception:
                            stocks_with_mcap.append((code, 0))
                    
                    stocks_with_mcap.sort(key=lambda x: x[1], reverse=True)
                    for code, mcap in stocks_with_mcap[:remaining]:
                        if code not in seen:
                            peers.append(code)
                            seen.add(code)
                            
                except Exception as e:
                    logger.warning(f"時価総額ソート失敗、順位順で補完: {e}")
                    for code in candidates[:remaining]:
                        if code not in seen:
                            peers.append(code)
                            seen.add(code)
                
    except Exception as e:
        logger.warning(f"競合他社取得エラー ({ticker}): {e}")
    
    return peers[:5]
