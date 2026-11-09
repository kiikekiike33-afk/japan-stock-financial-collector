import os
import unittest
import fitz
from src.processing.pdf_text_extractor import extract_text_from_pdf, extract_texts_for_pdfs

class TestPdfTextExtractor(unittest.TestCase):
    def setUp(self):
        self.test_dir = os.path.join(os.path.dirname(__file__), "temp_test_pdf")
        os.makedirs(self.test_dir, exist_ok=True)
        
        # 1. 通常テキストPDFの作成
        self.normal_pdf = os.path.join(self.test_dir, "normal.pdf")
        doc = fitz.open()
        page = doc.new_page()
        text = "This is a test financial document for unit testing. " * 5
        page.insert_text((50, 50), text)
        doc.save(self.normal_pdf)
        doc.close()
        
        # 2. 低文字数PDFの作成 (100文字未満)
        self.low_text_pdf = os.path.join(self.test_dir, "low_text.pdf")
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Short text.")
        doc.save(self.low_text_pdf)
        doc.close()
        
    def tearDown(self):
        import shutil
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)
            
    def test_extract_normal_pdf(self):
        res = extract_text_from_pdf(self.normal_pdf)
        self.assertTrue(os.path.exists(res["txt_path"]))
        self.assertEqual(res["page_count"], 1)
        self.assertGreater(res["total_chars"], 100)
        self.assertFalse(res["is_low_text"])
        
        with open(res["txt_path"], "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("financial document", content)
            self.assertIn("--- ページ 1 ---", content)
            
    def test_extract_low_text_pdf(self):
        res = extract_text_from_pdf(self.low_text_pdf)
        self.assertTrue(os.path.exists(res["txt_path"]))
        self.assertEqual(res["page_count"], 1)
        self.assertLess(res["total_chars"], 100)
        self.assertTrue(res["is_low_text"])
        
    def test_extract_texts_for_pdfs(self):
        txt_paths, low_reports = extract_texts_for_pdfs([self.normal_pdf, self.low_text_pdf])
        self.assertEqual(len(txt_paths), 2)
        self.assertEqual(len(low_reports), 1)
        self.assertEqual(low_reports[0]["pdf_path"], self.low_text_pdf)

if __name__ == "__main__":
    unittest.main()
