import os
import sys
import time
import json
import logging
from datetime import datetime

# プロジェクトルートをパスに追加
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(project_root)
sys.path.insert(0, project_root)

from src.utils.logger import setup_collector_logger
from src.utils.mapper import ticker_to_edinet, get_company_name
from src.api.edinet import fetch_and_save_edinet_reports
from src.api.tdnet import search_and_download_tdnet_docs
from src.api.esg_reports import fetch_integrated_esg_reports
from src.processing.pdf_merger import group_and_merge_by_year
from src.processing.pdf_text_extractor import extract_texts_for_pdfs
from src.cloud.gdrive import upload_to_drive
from src.api.stock_data import fetch_3y_stock_data

def process_single_ticker(ticker: str, company_name: str, target_years: int = 5):
    logger = logging.getLogger(__name__)
    display_name = f"{ticker}_{company_name}"
    logger.info(f"==================================================")
    logger.info(f"=== 銘柄収集開始: {display_name} (過去{target_years}年) ===")
    logger.info(f"==================================================")
    
    start_time = time.time()
    downloaded_files = []
    summary = {
        "ticker": ticker,
        "company_name": company_name,
        "display_name": display_name,
        "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "edinet": {"downloaded": []},
        "tdnet": {"downloaded": []},
        "esg": {"downloaded": []},
        "stock_data": None,
        "merged_files": [],
        "extracted_txt_files": [],
        "low_text_reports": [],
        "upload_targets": [],
        "gdrive_folder_link": "",
        "gdrive_file_links": [],
        "errors": []
    }
    
    # 1. EDINET
    logger.info(f"[{ticker}] --- 1. EDINET 書類検索 & ダウンロード ---")
    try:
        edinet_code = ticker_to_edinet(ticker)
        logger.info(f"[{ticker}] EDINET コード: {edinet_code}")
        summary["edinet"]["code"] = edinet_code
        if edinet_code:
            edinet_files = fetch_and_save_edinet_reports(ticker, edinet_code, years=target_years)
            downloaded_files.extend(edinet_files)
            summary["edinet"]["downloaded"] = edinet_files
            logger.info(f"[{ticker}] EDINET 取得件数: {len(edinet_files)}")
        else:
            logger.warning(f"[{ticker}] EDINET コードが見つかりませんでした")
            summary["errors"].append("EDINET コード未解決")
    except Exception as e:
        logger.error(f"[{ticker}] EDINET 処理エラー: {e}", exc_info=True)
        summary["errors"].append(f"EDINET: {str(e)}")

    # 2. TDnet (IR Bank)
    logger.info(f"[{ticker}] --- 2. TDnet (IR Bank) 開示検索 & ダウンロード ---")
    try:
        tdnet_files = search_and_download_tdnet_docs(ticker, years=target_years)
        downloaded_files.extend(tdnet_files)
        summary["tdnet"]["downloaded"] = tdnet_files
        logger.info(f"[{ticker}] TDnet 取得件数: {len(tdnet_files)}")
    except Exception as e:
        logger.error(f"[{ticker}] TDnet 処理エラー: {e}", exc_info=True)
        summary["errors"].append(f"TDnet: {str(e)}")

    # 3. ESG・統合報告書 (Web)
    logger.info(f"[{ticker}] --- 3. ESG・統合報告書 検索 & ダウンロード ---")
    try:
        esg_files = fetch_integrated_esg_reports(ticker, company_name)
        downloaded_files.extend(esg_files)
        summary["esg"]["downloaded"] = esg_files
        logger.info(f"[{ticker}] ESG 取得件数: {len(esg_files)}")
    except Exception as e:
        logger.error(f"[{ticker}] ESG 処理エラー: {e}", exc_info=True)
        summary["errors"].append(f"ESG: {str(e)}")

    # 4. 株価データ (過去3年分)
    logger.info(f"[{ticker}] --- 4. 過去3年分株価データ取得 ---")
    try:
        stock_csv = fetch_3y_stock_data(ticker, company_name)
        if stock_csv:
            downloaded_files.append(stock_csv)
            summary["stock_data"] = stock_csv
            logger.info(f"[{ticker}] 株価データ生成: {stock_csv}")
        else:
            logger.warning(f"[{ticker}] 株価データ取得不可")
    except Exception as e:
        logger.error(f"[{ticker}] 株価データ取得エラー: {e}", exc_info=True)
        summary["errors"].append(f"株価データ: {str(e)}")

    # 5. PDF結合
    logger.info(f"[{ticker}] --- 5. PDF結合処理 ---")
    upload_targets = []
    csv_files = [f for f in downloaded_files if f.endswith('.csv')]
    pdf_files = [f for f in downloaded_files if f.endswith('.pdf')]
    
    merged_files = []
    if pdf_files:
        try:
            merged_files = group_and_merge_by_year(pdf_files, ticker, company_name)
            upload_targets.extend(merged_files)
            summary["merged_files"] = merged_files
            logger.info(f"[{ticker}] 結合後PDF件数: {len(merged_files)}")
        except Exception as e:
            logger.error(f"[{ticker}] PDF結合エラー: {e}", exc_info=True)
            summary["errors"].append(f"PDF結合: {str(e)}")
            upload_targets.extend(pdf_files)
    upload_targets.extend(csv_files)

    # 5.5 テキスト抽出 (PyMuPDF)
    logger.info(f"[{ticker}] --- 5.5 テキスト抽出 (PyMuPDF) ---")
    all_target_pdfs = list(dict.fromkeys(pdf_files + merged_files))
    try:
        txt_files, low_text_reports = extract_texts_for_pdfs(all_target_pdfs)
        upload_targets.extend(txt_files)
        summary["extracted_txt_files"] = txt_files
        summary["low_text_reports"] = low_text_reports
        logger.info(f"[{ticker}] テキスト生成件数: {len(txt_files)}, 低文字数PDF: {len(low_text_reports)}件")
    except Exception as e:
        logger.error(f"[{ticker}] テキスト抽出エラー: {e}", exc_info=True)
        summary["errors"].append(f"テキスト抽出: {str(e)}")

    summary["upload_targets"] = upload_targets

    # 6. Google Driveへアップロード
    logger.info(f"[{ticker}] --- 6. Google Drive アップロード ---")
    try:
        folder_link, file_links = upload_to_drive(display_name, upload_targets, group_folder_name=None)
        summary["gdrive_folder_link"] = folder_link
        summary["gdrive_file_links"] = file_links
        logger.info(f"[{ticker}] Google Drive アップロード完了: {folder_link}")
        logger.info(f"[{ticker}] アップロードファイル件数: {len(file_links)}")
    except Exception as e:
        logger.error(f"[{ticker}] Google Drive アップロードエラー: {e}", exc_info=True)
        summary["errors"].append(f"Google Drive: {str(e)}")

    elapsed = time.time() - start_time
    summary["elapsed_seconds"] = round(elapsed, 2)
    summary["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[{ticker}] 完了 (所要時間: {summary['elapsed_seconds']} 秒)")
    return summary

def main():
    setup_collector_logger("PORTFOLIO")
    logger = logging.getLogger(__name__)
    logger.info("=== 保有5銘柄の決算資料収集（リンチ式深掘り用）一括タスク開始 ===")
    
    target_list = [
        ("2928", "RIZAPグループ"),
        ("3093", "トレジャー・ファクトリー"),
        ("4755", "楽天グループ"),
        ("9551", "メタウォーター"),
        ("9934", "因幡電機産業")
    ]
    
    all_results = {}
    for idx, (ticker, company_name) in enumerate(target_list):
        logger.info(f"\n>>>>>>>>>> 進行状況: [{idx+1}/{len(target_list)}] {ticker} {company_name} <<<<<<<<<<")
        try:
            res = process_single_ticker(ticker, company_name, target_years=5)
            all_results[ticker] = res
        except Exception as e:
            logger.error(f"[{ticker}] 予期せぬ致命的例外（後続を継続）: {e}", exc_info=True)
            all_results[ticker] = {
                "ticker": ticker,
                "company_name": company_name,
                "errors": [f"Fatal: {str(e)}"],
                "gdrive_folder_link": ""
            }
            
    # 結果保存
    out_path = os.path.join(project_root, "output", "portfolio_collector_result.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
        
    logger.info(f"=== 保有5銘柄の全収集処理が完了しました: 結果サマリー -> {out_path} ===")

if __name__ == "__main__":
    main()
