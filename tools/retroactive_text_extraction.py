import os
import sys
import json
import logging
from datetime import datetime

# プロジェクトルートをパスに追加
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(project_root)
sys.path.insert(0, project_root)

from src.utils.logger import setup_collector_logger
from src.processing.pdf_text_extractor import extract_texts_for_pdfs
from src.cloud.gdrive import upload_to_drive

def process_target(ticker: str, company_name: str, result_json_path: str):
    logger = logging.getLogger(__name__)
    display_name = f"{ticker}_{company_name}"
    logger.info(f"=== {display_name} 遡及テキスト抽出開始 ===")
    
    with open(result_json_path, "r", encoding="utf-8") as f:
        res_data = json.load(f)
        
    # 個別収集PDFと結合PDFの両方を網羅
    edinet_files = res_data.get("edinet", {}).get("downloaded", [])
    tdnet_files = res_data.get("tdnet", {}).get("downloaded", [])
    esg_files = res_data.get("esg", {}).get("downloaded", [])
    merged_files = res_data.get("merged_files", [])
    
    all_pdfs = list(dict.fromkeys(edinet_files + tdnet_files + esg_files + merged_files))
    all_pdfs = [f for f in all_pdfs if f.lower().endswith(".pdf") and os.path.exists(f)]
    logger.info(f"対象PDF件数: {len(all_pdfs)}件")
    
    # テキスト抽出
    txt_files, low_text_reports = extract_texts_for_pdfs(all_pdfs)
    logger.info(f"生成 .txt 件数: {len(txt_files)}件, 低文字数PDF: {len(low_text_reports)}件")
    
    for r in low_text_reports:
        logger.warning(
            f"低文字数PDF: {os.path.basename(r['pdf_path'])} - {r['total_chars']}文字 / {r['page_count']}頁 "
            f"(平均 {r['chars_per_page']}文字/頁)"
        )
        
    # Google Drive へ .txt ファイルをアップロード
    logger.info(f"Google Drive へテキストファイル {len(txt_files)}件 をアップロード中...")
    folder_link, file_links = upload_to_drive(display_name, txt_files, group_folder_name=None)
    logger.info(f"アップロード完了: {folder_link} ({len(file_links)}件)")
    
    return {
        "ticker": ticker,
        "company_name": company_name,
        "total_pdfs": len(all_pdfs),
        "generated_txts": len(txt_files),
        "low_text_reports": low_text_reports,
        "gdrive_folder_link": folder_link,
        "uploaded_count": len(file_links)
    }

def main():
    setup_collector_logger("RETROACTIVE")
    logger = logging.getLogger(__name__)
    logger.info("=== 収集PDFテキスト抽出（既存分遡及適用）タスク開始 ===")
    
    results = {}
    
    # 1. 446A ノースサンド
    results["446A"] = process_target(
        ticker="446A",
        company_name="ノースサンド",
        result_json_path=os.path.join(project_root, "output", "task15_result.json")
    )
    
    # 2. 1965 テクノ菱和
    results["1965"] = process_target(
        ticker="1965",
        company_name="テクノ菱和",
        result_json_path=os.path.join(project_root, "output", "task16_result.json")
    )
    
    # 結果サマリーを保存
    out_path = os.path.join(project_root, "output", "retroactive_text_extraction_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        
    logger.info(f"=== 全遡及処理完了: 結果を {out_path} に保存しました ===")

if __name__ == "__main__":
    main()
