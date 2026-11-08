import os
import fitz  # PyMuPDF
import logging
from src.utils.config import TEMP_DOWNLOAD_DIR

logger = logging.getLogger(__name__)

def merge_pdfs(pdf_filepaths: list, output_filename: str):
    """
    Merges multiple PDF files into a single PDF file (e.g., for NotebookLM limit).
    """
    if not pdf_filepaths:
        logger.warning("No PDFs provided for merging.")
        return None
        
    if len(pdf_filepaths) == 1:
        # If there's only one, you can just return it, but renaming it might be requested
        # Let's just return the original or rename it.
        pass
        
    merged_pdf = fitz.open()
    
    output_path = os.path.join(TEMP_DOWNLOAD_DIR, output_filename)
        
    try:
        for filepath in pdf_filepaths:
            if not os.path.exists(filepath):
                continue
            with fitz.open(filepath) as doc:
                merged_pdf.insert_pdf(doc)
                
        if merged_pdf.page_count > 0:
            merged_pdf.save(output_path)
            logger.info(f"Successfully merged {len(pdf_filepaths)} files into {output_path}")
            return output_path
        else:
            logger.warning("Merged PDF has no pages.")
            return None
    except Exception as e:
        logger.error(f"Error during PDF merge: {e}")
        return None
    finally:
        merged_pdf.close()

def group_and_merge_by_year(pdf_filepaths: list, ticker: str, company_name: str = ""):
    """
    年度とドキュメント種別ごとにPDFをグループ化し、結合する。
    出力ファイル名: {ticker}_{company_name}_{year}_{doc_type}.pdf
    """
    if not pdf_filepaths:
        return []
        
    # 重複パスを削除（同じファイルが複数回結合されるのを防ぐ）
    pdf_filepaths = list(dict.fromkeys(pdf_filepaths))
    
    doc_types = ["決算短信", "有価証券報告書", "四半期報告書", "業績予想修正", "統合報告書", "長期経営計画"]
        
    # 年度と種別ごとにグループ化
    grouped = {}
    for filepath in pdf_filepaths:
        basename = os.path.basename(filepath)
        
        # 年を抽出
        if len(basename) >= 8 and basename[:8].isdigit():
            year = basename[:4]
        else:
            year = "その他"
            
        # 種別を抽出
        doc_type = "その他"
        for t in doc_types:
            if t in basename:
                # 四半期報告書と有価証券報告書は一旦分けるか、有価証券報告書にまとめるか
                # ユーザーは「有価証券報告書」として指定していたので、四半期報告書も分ける
                if t == "四半期報告書":
                    doc_type = "有価証券報告書" # 四半期報告書は有価証券報告書としてまとめる
                else:
                    doc_type = t
                break
                
        key = f"{year}_{doc_type}"
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(filepath)
            
    merged_paths = []
    for key, paths in grouped.items():
        if len(paths) >= 1:
            paths.sort()
            year_str, type_str = key.split('_', 1)
            
            if company_name:
                output_filename = f"{ticker}_{company_name}_{year_str}_{type_str}.pdf"
            else:
                output_filename = f"{ticker}_{year_str}_{type_str}.pdf"
                
            merged_path = merge_pdfs(paths, output_filename)
            if merged_path:
                merged_paths.append(merged_path)
                
    return merged_paths

