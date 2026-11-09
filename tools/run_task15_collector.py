import os
import sys
import time
import json
import logging
from datetime import datetime
from src.utils.logger import setup_collector_logger

# プロジェクトルートをパスに追加
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(project_root)
sys.path.insert(0, project_root)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

from src.utils.mapper import ticker_to_edinet, get_company_name
from src.api.edinet import fetch_and_save_edinet_reports
from src.api.tdnet import search_and_download_tdnet_docs
from src.api.esg_reports import fetch_integrated_esg_reports
from src.processing.pdf_merger import group_and_merge_by_year
from src.processing.pdf_text_extractor import extract_texts_for_pdfs
from src.cloud.gdrive import upload_to_drive
from src.api.stock_data import fetch_3y_stock_data
import src.utils.config as config

def main():
    ticker = "446A"
    setup_collector_logger(ticker)
    target_years = 5  # 標準設定: 過去5年
    merge_options = True
    fetch_esg = True
    fetch_stock = True
    
    start_time = time.time()
    logger.info(f"=== 指示15 データ収集タスク開始 (Ticker: {ticker}) ===")
    
    company_name = get_company_name(ticker) or "ノースサンド"
    display_name = f"{ticker}_{company_name}"
    logger.info(f"対象企業名: {company_name} (表示名: {display_name})")
    
    downloaded_files = []
    summary = {
        "ticker": ticker,
        "company_name": company_name,
        "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "edinet": {"found": [], "downloaded": [], "not_found": []},
        "tdnet": {"found": [], "downloaded": [], "rejected": 0, "not_found": []},
        "esg": {"downloaded": [], "not_found": []},
        "stock_data": None,
        "merged_files": [],
        "upload_targets": [],
        "gdrive_folder_link": "",
        "gdrive_file_links": [],
        "errors": []
    }
    
    # 1. EDINET
    logger.info("--- 1. EDINET 書類検索 & ダウンロード ---")
    try:
        edinet_code = ticker_to_edinet(ticker)
        logger.info(f"EDINET コード: {edinet_code}")
        summary["edinet"]["code"] = edinet_code
        
        edinet_files = fetch_and_save_edinet_reports(ticker, edinet_code, years=target_years)
        downloaded_files.extend(edinet_files)
        summary["edinet"]["downloaded"] = edinet_files
        logger.info(f"EDINET 取得件数: {len(edinet_files)}")
    except Exception as e:
        logger.error(f"EDINET 処理エラー: {e}", exc_info=True)
        summary["errors"].append(f"EDINET: {str(e)}")

    # 2. TDnet (IR Bank)
    logger.info("--- 2. TDnet (IR Bank) 開示検索 & ダウンロード ---")
    try:
        tdnet_files = search_and_download_tdnet_docs(ticker, years=target_years)
        downloaded_files.extend(tdnet_files)
        summary["tdnet"]["downloaded"] = tdnet_files
        logger.info(f"TDnet 取得件数: {len(tdnet_files)}")
    except Exception as e:
        logger.error(f"TDnet 処理エラー: {e}", exc_info=True)
        summary["errors"].append(f"TDnet: {str(e)}")

    # 3. ESG・統合報告書 (Web)
    if fetch_esg:
        logger.info("--- 3. ESG・統合報告書 検索 & ダウンロード ---")
        try:
            esg_files = fetch_integrated_esg_reports(ticker, company_name)
            downloaded_files.extend(esg_files)
            summary["esg"]["downloaded"] = esg_files
            logger.info(f"ESG 取得件数: {len(esg_files)}")
        except Exception as e:
            logger.error(f"ESG 処理エラー: {e}", exc_info=True)
            summary["errors"].append(f"ESG: {str(e)}")

    # 4. 株価データ (過去3年分)
    if fetch_stock:
        logger.info("--- 4. 過去3年分株価データ取得 ---")
        try:
            stock_csv = fetch_3y_stock_data(ticker, company_name)
            if stock_csv:
                downloaded_files.append(stock_csv)
                summary["stock_data"] = stock_csv
                logger.info(f"株価データ生成: {stock_csv}")
            else:
                logger.warning("株価データ取得不可（上場期間等の理由）")
                summary["stock_data"] = None
        except Exception as e:
            logger.error(f"株価データ取得エラー: {e}", exc_info=True)
            summary["errors"].append(f"株価データ: {str(e)}")

    # 5. PDF結合
    logger.info("--- 5. PDF結合処理 ---")
    upload_targets = []
    csv_files = [f for f in downloaded_files if f.endswith('.csv')]
    pdf_files = [f for f in downloaded_files if f.endswith('.pdf')]
    
    if merge_options and pdf_files:
        try:
            merged_files = group_and_merge_by_year(pdf_files, ticker, company_name)
            upload_targets.extend(merged_files)
            summary["merged_files"] = merged_files
            logger.info(f"結合後PDF件数: {len(merged_files)}")
        except Exception as e:
            logger.error(f"PDF結合エラー: {e}", exc_info=True)
            summary["errors"].append(f"PDF結合: {str(e)}")
            upload_targets.extend(pdf_files)
    else:
        upload_targets.extend(pdf_files)
        
    upload_targets.extend(csv_files)
    summary["upload_targets"] = upload_targets

    # 5.5 テキスト抽出処理 (PyMuPDF)
    logger.info("--- 5.5 テキスト抽出処理 (PyMuPDF) ---")
    all_target_pdfs = list(dict.fromkeys(pdf_files + (merged_files if merge_options else [])))
    txt_files, low_text_reports = extract_texts_for_pdfs(all_target_pdfs)
    upload_targets.extend(txt_files)
    summary["extracted_txt_files"] = txt_files
    summary["low_text_reports"] = low_text_reports
    logger.info(f"生成テキストファイル件数: {len(txt_files)}, 低文字数PDF: {len(low_text_reports)}件")

    # 6. Google Driveへアップロード
    logger.info("--- 6. Google Drive アップロード ---")
    try:
        folder_link, file_links = upload_to_drive(display_name, upload_targets, group_folder_name=None)
        summary["gdrive_folder_link"] = folder_link
        summary["gdrive_file_links"] = file_links
        logger.info(f"Google Drive アップロード完了: {folder_link}")
        logger.info(f"アップロードファイル件数: {len(file_links)}")
    except Exception as e:
        logger.error(f"Google Drive アップロードエラー: {e}", exc_info=True)
        summary["errors"].append(f"Google Drive: {str(e)}")

    elapsed = time.time() - start_time
    summary["elapsed_seconds"] = round(elapsed, 2)
    summary["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"=== 全処理完了 (所要時間: {summary['elapsed_seconds']} 秒) ===")

    # 結果をJSONとして保存
    result_path = os.path.join(project_root, "output", "task15_result.json")
    os.makedirs(os.path.dirname(result_path), exist_ok=True)
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    logger.info(f"結果サマリー保存: {result_path}")

if __name__ == "__main__":
    main()
