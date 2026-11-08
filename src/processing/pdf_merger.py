import os
import fitz  # PyMuPDF
import logging
from src.utils.config import TEMP_DOWNLOAD_DIR

logger = logging.getLogger(__name__)

def merge_pdfs(pdf_filepaths: list, output_filename: str):
    """
    複数のPDFファイルを1つのPDFファイルに結合します。
    """
    if not pdf_filepaths:
        logger.warning("結合対象のPDFが指定されていません。")
        return None
        
    merged_pdf = fitz.open()
    output_path = os.path.join(TEMP_DOWNLOAD_DIR, output_filename)
        
    try:
        for filepath in pdf_filepaths:
            if not os.path.exists(filepath):
                logger.warning(f"結合対象ファイルが存在しません: {filepath}")
                continue
            with fitz.open(filepath) as doc:
                merged_pdf.insert_pdf(doc)
                
        if merged_pdf.page_count > 0:
            merged_pdf.save(output_path)
            logger.info(f"{len(pdf_filepaths)} 件のファイルを結合完了: {output_path}")
            return output_path
        else:
            logger.warning("結合後PDFのページ数が0です。")
            return None
    except Exception as e:
        logger.error(f"PDF結合中にエラーが発生しました: {e}")
        return None
    finally:
        merged_pdf.close()

def group_and_merge_by_year(pdf_filepaths: list, ticker: str, company_name: str = ""):
    """
    年度とドキュメント種別ごとにPDFをグループ化し、結合します。
    出力ファイル名: {ticker}_{company_name}_{year}_{doc_type}.pdf
    
    【改修点（指示07）】
    - 四半期報告書を有価証券報告書と分離し、独立した種別として結合・出力。
    - 年度抽出失敗ファイルを無言で落とさず、警告ログを出力。
    """
    if not pdf_filepaths:
        return []
        
    # 重複パスを削除
    pdf_filepaths = list(dict.fromkeys(pdf_filepaths))
    
    doc_types = ["決算短信", "有価証券報告書", "四半期報告書", "業績予想修正", "統合報告書", "長期経営計画", "ESGデータ"]
        
    # 年度と種別ごとにグループ化
    grouped = {}
    for filepath in pdf_filepaths:
        basename = os.path.basename(filepath)
        
        # 年を抽出（先頭8文字が数字なら先頭4文字を年度とする）
        if len(basename) >= 8 and basename[:8].isdigit():
            year = basename[:4]
        else:
            year = "その他"
            logger.warning(f"年度を抽出できなかったため『その他』に分類しました: {basename}")
            
        # 種別を抽出
        doc_type = "その他"
        for t in doc_types:
            if t in basename:
                # 四半期報告書を有価証券報告書へ寄せず、種別を分けたまま保持する（指示07）
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
