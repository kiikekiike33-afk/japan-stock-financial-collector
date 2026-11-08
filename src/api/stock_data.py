import os
import logging
from datetime import datetime
import pandas as pd

logger = logging.getLogger(__name__)

def fetch_3y_stock_data(ticker: str, company_name: str = "") -> str:
    """
    yfinanceを利用して過去3年分の日次株価・出来高データを取得し、PDFとして保存する。
    戻り値: 保存したPDFファイルのパス。取得できなかった場合は None。
    """
    try:
        import yfinance as yf
        import matplotlib.pyplot as plt
        import japanize_matplotlib
        from matplotlib.backends.backend_pdf import PdfPages
    except ImportError:
        logger.error("yfinance or matplotlib is not installed.")
        return None
        
    try:
        # 日本株のティッカーシンボル（例: 7203.T）
        yf_ticker = f"{ticker}.T"
        stock = yf.Ticker(yf_ticker)
        
        # 過去3年分の履歴データを取得
        df = stock.history(period="3y")
        
        if df.empty:
            logger.warning(f"No stock data found for {ticker}.")
            return None
            
        df.index = df.index.tz_localize(None)
        
        cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        df = df[[c for c in cols if c in df.columns]]
        
        # 保存先ディレクトリの作成
        output_dir = "output"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        if company_name:
            filename = f"{ticker}_{company_name}_3年分株価データ.pdf"
            title_name = f"{ticker} {company_name} - 過去3年間の株価推移"
        else:
            filename = f"{ticker}_3年分株価データ.pdf"
            title_name = f"{ticker} - 過去3年間の株価推移"
            
        filepath = os.path.join(output_dir, filename)
        
        # サマリー情報の計算
        max_price = df['High'].max()
        min_price = df['Low'].min()
        avg_vol = df['Volume'].mean()
        start_date = df.index[0].strftime('%Y/%m/%d')
        end_date = df.index[-1].strftime('%Y/%m/%d')
        start_price = df['Close'].iloc[0]
        end_price = df['Close'].iloc[-1]
        perf = ((end_price - start_price) / start_price) * 100
        
        # プロットの作成 (3つの領域: 株価、出来高、サマリーテキスト)
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 12), gridspec_kw={'height_ratios': [3, 1, 1]})
        fig.suptitle(title_name, fontsize=16, fontweight='bold')
        
        # 1. 株価チャート (Close)
        ax1.plot(df.index, df['Close'], color='blue', linewidth=1.5, label='終値')
        ax1.set_title("株価 (終値)", fontsize=12)
        ax1.set_ylabel("価格 (円)")
        ax1.grid(True, linestyle='--', alpha=0.6)
        ax1.legend(loc="upper left")
        
        # 2. 出来高チャート (Volume)
        ax2.bar(df.index, df['Volume'], color='gray', alpha=0.7, width=1.5, label='出来高')
        ax2.set_title("出来高", fontsize=12)
        ax2.set_ylabel("株数")
        ax2.grid(True, linestyle='--', alpha=0.6)
        ax2.legend(loc="upper left")
        
        # 信用残高の取得（Yahoo Financeから直近の週次データ）
        margin_buy, margin_sell, margin_mag = "取得不可", "取得不可", "取得不可"
        try:
            import requests
            import re
            url = f"https://finance.yahoo.co.jp/quote/{yf_ticker}"
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            buy_m = re.search(r'marginTransactionBuy.*?value[^\d]+([\d,\.]+)', res.text)
            sell_m = re.search(r'marginTransactionSell.*?value[^\d]+([\d,\.]+)', res.text)
            mag_m = re.search(r'marginCreditMagnification.*?value[^\d]+([\d,\.]+)', res.text)
            
            if buy_m: margin_buy = buy_m.group(1) + " 株"
            if sell_m: margin_sell = sell_m.group(1) + " 株"
            if mag_m: margin_mag = mag_m.group(1) + " 倍"
        except Exception as e:
            logger.warning(f"Failed to fetch margin balance for {ticker}: {e}")
            
        # 3. サマリー情報 (Text)
        ax3.axis('off')
        summary_text = (
            f"【データ期間】 {start_date} 〜 {end_date}\n\n"
            f"● 期間最高値: {max_price:,.1f} 円\n"
            f"● 期間最安値: {min_price:,.1f} 円\n"
            f"● 期間首尾パフォーマンス: {perf:+.2f} %\n"
            f"● 1日平均出来高: {avg_vol:,.0f} 株\n\n"
            f"【直近の信用取引残高 (週次)】\n"
            f"● 信用買残: {margin_buy}  /  信用売残: {margin_sell}  /  信用倍率: {margin_mag}\n"
        )
        ax3.text(0.1, 0.5, summary_text, fontsize=12, va='center', ha='left',
                 bbox=dict(boxstyle='round,pad=1', facecolor='whitesmoke', edgecolor='gray'))
        
        plt.tight_layout()
        plt.subplots_adjust(top=0.92)
        
        # PDFとして保存 (複数ページ)
        with PdfPages(filepath) as pdf:
            # 1ページ目: グラフとサマリー
            pdf.savefig(fig)
            plt.close(fig)
            
            # 2ページ目以降: 日別データの表
            # 最新の日付から降順にする
            df_desc = df.sort_index(ascending=False)
            chunk_size = 45 # 1ページあたりの行数
            total_rows = len(df_desc)
            
            for i in range(0, total_rows, chunk_size):
                chunk = df_desc.iloc[i:i+chunk_size]
                
                fig_table, ax_table = plt.subplots(figsize=(10, 12))
                ax_table.axis('off')
                
                page_title = f"日別データ ({i+1} 〜 {min(i+chunk_size, total_rows)} 件目 / 全{total_rows}件)"
                ax_table.set_title(page_title, fontsize=14, fontweight='bold')
                
                # データのフォーマット
                formatted_chunk = chunk.copy()
                formatted_chunk.index = formatted_chunk.index.strftime('%Y/%m/%d')
                for col in ['Open', 'High', 'Low', 'Close']:
                    formatted_chunk[col] = formatted_chunk[col].map(lambda x: f"{x:,.1f}" if pd.notna(x) else "-")
                formatted_chunk['Volume'] = formatted_chunk['Volume'].map(lambda x: f"{x:,.0f}" if pd.notna(x) else "-")
                
                # 表の描画
                table = ax_table.table(
                    cellText=formatted_chunk.values,
                    rowLabels=formatted_chunk.index,
                    colLabels=formatted_chunk.columns,
                    loc='center',
                    cellLoc='right'
                )
                
                # 表のレイアウト調整
                table.auto_set_font_size(False)
                table.set_fontsize(10)
                table.scale(1, 1.8) # 行の高さを広げる
                
                # ヘッダーと行ラベルのスタイル調整
                for (row, col), cell in table.get_celld().items():
                    if row == 0 or col == -1:
                        cell.set_text_props(weight='bold')
                        cell.set_facecolor('#f0f0f0')
                
                plt.tight_layout()
                pdf.savefig(fig_table)
                plt.close(fig_table)
        
        logger.info(f"Successfully saved 3-year stock data PDF for {ticker} at {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"Error fetching stock data for {ticker}: {e}")
        return None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    path = fetch_3y_stock_data("7203", "トヨタ自動車")
    print(f"Saved to: {path}")
