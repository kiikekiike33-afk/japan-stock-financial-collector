import os
import logging
import fitz

logger = logging.getLogger(__name__)

def extract_text_from_pdf(pdf_path: str, output_txt_path: str = None) -> dict:
    """
    PyMuPDF (fitz) を使用してPDFファイルからテキストを抽出し、同名の .txt ファイルを生成します。
    
    引数:
        pdf_path: 対象PDFファイルのパス
        output_txt_path: 出力先テキストファイルのパス (省略時は同名 .txt)
        
    戻り値:
        dict: {
            "pdf_path": str,
            "txt_path": str,
            "page_count": int,
            "total_chars": int,
            "chars_per_page": float,
            "is_low_text": bool
        }
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDFファイルが見つかりません: {pdf_path}")
        
    if not output_txt_path:
        output_txt_path = os.path.splitext(pdf_path)[0] + ".txt"
        
    total_chars = 0
    pages_text = []
    
    with fitz.open(pdf_path) as doc:
        page_count = len(doc)
        for page_idx in range(page_count):
            page = doc[page_idx]
            text = page.get_text() or ""
            total_chars += len(text.strip())
            pages_text.append(f"--- ページ {page_idx + 1} ---\n{text}")
            
    full_text = "\n\n".join(pages_text)
    
    # UTF-8 でテキストファイルを保存
    os.makedirs(os.path.dirname(os.path.abspath(output_txt_path)), exist_ok=True)
    with open(output_txt_path, "w", encoding="utf-8") as f:
        f.write(full_text)
        
    chars_per_page = round(total_chars / max(1, page_count), 1)
    is_low_text = total_chars < (page_count * 100)
    
    if is_low_text:
        logger.warning(
            f"テキスト抽出量が極端に少ないPDFを検出: {os.path.basename(pdf_path)} "
            f"({total_chars}文字 / {page_count}ページ, 平均 {chars_per_page}文字/頁)"
        )
    else:
        logger.info(
            f"テキスト抽出完了: {os.path.basename(output_txt_path)} "
            f"({total_chars}文字 / {page_count}ページ)"
        )
        
    return {
        "pdf_path": pdf_path,
        "txt_path": output_txt_path,
        "page_count": page_count,
        "total_chars": total_chars,
        "chars_per_page": chars_per_page,
        "is_low_text": is_low_text
    }

def extract_texts_for_pdfs(pdf_paths: list[str]) -> tuple[list[str], list[dict]]:
    """
    複数のPDFファイルから一括でテキストを抽出します。
    
    戻り値:
        (生成された .txt ファイルのパスリスト, 低文字数PDFのレポートリスト)
    """
    txt_paths = []
    low_text_reports = []
    
    for pdf_path in pdf_paths:
        if not pdf_path.lower().endswith(".pdf"):
            continue
        try:
            res = extract_text_from_pdf(pdf_path)
            txt_paths.append(res["txt_path"])
            if res["is_low_text"]:
                low_text_reports.append(res)
        except Exception as e:
            logger.error(f"テキスト抽出失敗: {pdf_path} ({e})", exc_info=True)
            
    return txt_paths, low_text_reports
