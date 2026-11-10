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

def collect_single_stock(ticker: str, company_name: str, target_years: int = 5):
    """単一銘柄の収集パイプライン（標準条件）"""
    start_time = time.time()
    display_name = f"{ticker}_{company_name}"
    logger.info(f"==================================================")
    logger.info(f"[{ticker}] 収集開始: {display_name}")
    logger.info(f"==================================================")

    downloaded_files = []
    summary = {
        "ticker": ticker,
        "company_name": company_name,
        "display_name": display_name,
        "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "edinet": {"downloaded": [], "code": ""},
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
        summary["edinet"]["code"] = edinet_code
        logger.info(f"[{ticker}] EDINET コード: {edinet_code}")
        if edinet_code:
            edinet_files = fetch_and_save_edinet_reports(ticker, edinet_code, years=target_years)
            downloaded_files.extend(edinet_files)
            summary["edinet"]["downloaded"] = edinet_files
            logger.info(f"[{ticker}] EDINET 取得件数: {len(edinet_files)}")
        else:
            logger.warning(f"[{ticker}] EDINET コードが見つかりませんでした。スキップします。")
    except Exception as e:
        logger.error(f"[{ticker}] EDINET エラー: {e}", exc_info=True)
        summary["errors"].append(f"EDINET: {str(e)}")

    # 2. TDnet (IR Bank)
    logger.info(f"[{ticker}] --- 2. TDnet (IR Bank) 開示検索 & ダウンロード ---")
    try:
        tdnet_files = search_and_download_tdnet_docs(ticker, years=target_years)
        downloaded_files.extend(tdnet_files)
        summary["tdnet"]["downloaded"] = tdnet_files
        logger.info(f"[{ticker}] TDnet 取得件数: {len(tdnet_files)}")
    except Exception as e:
        logger.error(f"[{ticker}] TDnet エラー: {e}", exc_info=True)
        summary["errors"].append(f"TDnet: {str(e)}")

    # 3. ESG / 統合報告書
    logger.info(f"[{ticker}] --- 3. ESG / 統合報告書 検索 & ダウンロード ---")
    try:
        esg_files = fetch_integrated_esg_reports(ticker, company_name)
        downloaded_files.extend(esg_files)
        summary["esg"]["downloaded"] = esg_files
        logger.info(f"[{ticker}] ESG 取得件数: {len(esg_files)}")
    except Exception as e:
        logger.error(f"[{ticker}] ESG エラー: {e}", exc_info=True)
        summary["errors"].append(f"ESG: {str(e)}")

    # 4. 株価データ
    logger.info(f"[{ticker}] --- 4. 株価データ取得 (過去3年) ---")
    try:
        stock_csv = fetch_3y_stock_data(ticker, company_name)
        if stock_csv and os.path.exists(stock_csv):
            downloaded_files.append(stock_csv)
            summary["stock_data"] = stock_csv
            logger.info(f"[{ticker}] 株価データ取得完了: {stock_csv}")
        else:
            logger.warning(f"[{ticker}] 株価データ取得なし")
    except Exception as e:
        logger.error(f"[{ticker}] 株価データ取得エラー: {e}", exc_info=True)
        summary["errors"].append(f"株価: {str(e)}")

    # 5. PDF 結合処理
    upload_targets = []
    logger.info(f"[{ticker}] --- 5. PDF 結合処理 ---")
    try:
        pdf_files = [f for f in downloaded_files if f.lower().endswith(".pdf")]
        merged_files = group_and_merge_by_year(pdf_files, ticker, company_name)
        summary["merged_files"] = merged_files
        non_pdf_files = [f for f in downloaded_files if not f.lower().endswith(".pdf")]
        upload_targets = merged_files + non_pdf_files
        logger.info(f"[{ticker}] 結合PDF件数: {len(merged_files)}")
    except Exception as e:
        logger.error(f"[{ticker}] PDF結合エラー: {e}", exc_info=True)
        summary["errors"].append(f"PDF結合: {str(e)}")
        upload_targets = downloaded_files

    # 6. PDF テキスト抽出処理 (PyMuPDF)
    logger.info(f"[{ticker}] --- 6. PDF テキスト抽出処理 ---")
    try:
        all_pdfs = [f for f in downloaded_files if f.lower().endswith(".pdf")]
        all_pdfs.extend(summary.get("merged_files", []))
        seen_pdf = set()
        unique_pdfs = []
        for p in all_pdfs:
            if p not in seen_pdf:
                seen_pdf.add(p)
                unique_pdfs.append(p)
                
        txt_files, low_text_reports = extract_texts_for_pdfs(unique_pdfs)
        summary["extracted_txt_files"] = txt_files
        summary["low_text_reports"] = low_text_reports
        upload_targets.extend(txt_files)
        logger.info(f"[{ticker}] テキスト生成件数: {len(txt_files)}, 低文字数PDF: {len(low_text_reports)}件")
    except Exception as e:
        logger.error(f"[{ticker}] テキスト抽出エラー: {e}", exc_info=True)
        summary["errors"].append(f"テキスト抽出: {str(e)}")

    summary["upload_targets"] = upload_targets

    # 7. Google Driveへアップロード
    logger.info(f"[{ticker}] --- 7. Google Drive アップロード ---")
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
    setup_collector_logger("SCREENING")
    logger.info("=== スクリーニング候補8銘柄の一括データ収集タスク開始 ===")
    
    candidates = [
        ("6417", "SANKYO"),
        ("7994", "オカムラ"),
        ("2181", "パーソルホールディングス"),
        ("6750", "エレコム"),
        ("4012", "アクシス"),
        ("3150", "グリムス"),
        ("2415", "ヒューマンホールディングス"),
        ("6915", "千代田インテグレ")
    ]
    
    total_start = time.time()
    results = {}
    
    for idx, (ticker, company_name) in enumerate(candidates, 1):
        logger.info(f"\n=======================================================")
        logger.info(f"【進捗 {idx}/{len(candidates)}】銘柄: {ticker} {company_name}")
        logger.info(f"=======================================================")
        try:
            res = collect_single_stock(ticker, company_name, target_years=5)
            results[ticker] = res
        except Exception as e:
            logger.error(f"銘柄 {ticker} ({company_name}) で致命的エラーが発生しましたが、後続を継続します: {e}", exc_info=True)
            results[ticker] = {
                "ticker": ticker,
                "company_name": company_name,
                "errors": [str(e)]
            }
        # 各銘柄終了時に途中経過を保存
        os.makedirs("output", exist_ok=True)
        with open("output/screening_candidates_result.json", "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

    total_elapsed = time.time() - total_start
    logger.info(f"\n=======================================================")
    logger.info(f"=== スクリーニング候補8銘柄の全収集完了 (総所要時間: {total_elapsed:.2f} 秒) ===")
    logger.info(f"=======================================================")

    # ログ共有
    sync_all_logs_to_muse_share()

if __name__ == "__main__":
    main()
