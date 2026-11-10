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

from src.utils.logger import setup_collector_logger, sync_all_logs_to_muse_share

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
    ticker = "3093"
    setup_collector_logger(ticker)
    target_years = 5  # 標準設定: 過去5年
    merge_options = True
    fetch_esg = True
    fetch_stock = True
    # 同業他社（peers）は OFF
    
    start_time = time.time()
    logger.info(f"=== 3093 トレジャー・ファクトリー 再収集タスク開始 (Ticker: {ticker}) ===")
    
    company_name = get_company_name(ticker) or "トレジャー・ファクトリー"
    display_name = f"{ticker}_{company_name}"
    logger.info(f"対象企業名: {company_name} (表示名: {display_name})")
    
    downloaded_files = []
    summary = {
        "ticker": ticker,
        "company_name": company_name,
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
    
    # 1. EDINET 書類検索 & ダウンロード
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

    # 3. ESG / 統合報告書
    if fetch_esg:
        logger.info("--- 3. ESG / 統合報告書 検索 & ダウンロード ---")
        try:
            esg_files = fetch_integrated_esg_reports(ticker, company_name)
            downloaded_files.extend(esg_files)
            summary["esg"]["downloaded"] = esg_files
            logger.info(f"ESG 取得件数: {len(esg_files)}")
        except Exception as e:
            logger.error(f"ESG 処理エラー: {e}", exc_info=True)
            summary["errors"].append(f"ESG: {str(e)}")

    # 4. 株価データ
    if fetch_stock:
        logger.info("--- 4. 株価データ (過去3年) 取得 ---")
        try:
            stock_csv = fetch_3y_stock_data(ticker, company_name)
            if stock_csv and os.path.exists(stock_csv):
                downloaded_files.append(stock_csv)
                summary["stock_data"] = stock_csv
                logger.info(f"株価データ取得完了: {stock_csv}")
            else:
                logger.warning(f"株価データ取得スキップまたは失敗 (Ticker: {ticker})")
        except Exception as e:
            logger.error(f"株価データ取得エラー: {e}", exc_info=True)
            summary["errors"].append(f"Stock: {str(e)}")

    # 5. PDF 結合処理
    upload_targets = []
    if merge_options:
        logger.info("--- 5. PDF 結合処理 ---")
        try:
            pdf_files_to_merge = [f for f in downloaded_files if f.lower().endswith(".pdf")]
            logger.info(f"結合対象 PDF 件数: {len(pdf_files_to_merge)}")
            merged_results = group_and_merge_by_year(pdf_files_to_merge, ticker, company_name)
            summary["merged_files"] = merged_results
            logger.info(f"結合完了 PDF 件数: {len(merged_results)}")
            
            # アップロード対象: 結合PDF + 非PDF(CSV等)
            non_pdf_files = [f for f in downloaded_files if not f.lower().endswith(".pdf")]
            upload_targets = merged_results + non_pdf_files
        except Exception as e:
            logger.error(f"PDF 結合処理エラー: {e}", exc_info=True)
            summary["errors"].append(f"Merge: {str(e)}")
            upload_targets = downloaded_files
    else:
        upload_targets = downloaded_files

    # 6. PDF テキスト抽出処理 (PyMuPDF)
    logger.info("--- 6. PDF テキスト抽出処理 (PyMuPDF) ---")
    try:
        pdf_targets_for_text = [f for f in downloaded_files if f.lower().endswith(".pdf")]
        if merge_options:
            pdf_targets_for_text.extend(summary.get("merged_files", []))
        # 重複排除
        seen_pdf = set()
        unique_pdf_targets = []
        for p in pdf_targets_for_text:
            if p not in seen_pdf:
                seen_pdf.add(p)
                unique_pdf_targets.append(p)
                
        logger.info(f"テキスト抽出対象 PDF 件数: {len(unique_pdf_targets)}")
        extracted_txts, low_text_reports = extract_texts_for_pdfs(unique_pdf_targets)
        summary["extracted_txt_files"] = extracted_txts
        summary["low_text_reports"] = low_text_reports
        logger.info(f"テキスト抽出完了件数: {len(extracted_txts)}, 低文字数PDF: {len(low_text_reports)}")
        
        # テキストファイルもDriveアップロード対象に追加
        upload_targets.extend(extracted_txts)
    except Exception as e:
        logger.error(f"テキスト抽出エラー: {e}", exc_info=True)
        summary["errors"].append(f"TextExtraction: {str(e)}")

    summary["upload_targets"] = upload_targets

    # 7. Google Drive アップロード
    logger.info(f"--- 7. Google Drive アップロード (対象ファイル数: {len(upload_targets)}) ---")
    try:
        folder_link, file_links = upload_to_drive(display_name, upload_targets, group_folder_name=None)
        summary["gdrive_folder_link"] = folder_link
        summary["gdrive_file_links"] = file_links
        logger.info(f"Google Drive フォルダリンク: {folder_link}")
        logger.info(f"アップロード成功ファイルリンク数: {len(file_links)}")
    except Exception as e:
        logger.error(f"Google Drive アップロードエラー: {e}", exc_info=True)
        summary["errors"].append(f"GDrive: {str(e)}")

    elapsed = time.time() - start_time
    summary["elapsed_seconds"] = elapsed
    logger.info(f"=== 3093 タスク完了 (所要時間: {elapsed:.2f} 秒) ===")

    # 結果をJSONとして保存
    os.makedirs("output", exist_ok=True)
    result_path = "output/3093_collector_result.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    logger.info(f"結果サマリー保存: {result_path}")

    # 共有先へ全ログを同期
    sync_all_logs_to_muse_share()

if __name__ == "__main__":
    main()
