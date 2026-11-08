import os
import unittest
import tempfile
import fitz
from src.processing.pdf_merger import group_and_merge_by_year, merge_pdfs


class TestPdfMerger(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        
    def tearDown(self):
        self.test_dir.cleanup()

    def _create_dummy_pdf(self, filename: str):
        filepath = os.path.join(self.test_dir.name, filename)
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((50, 50), f"Dummy text for {filename}")
        doc.save(filepath)
        doc.close()
        return filepath

    def test_grouping_classification(self):
        """四半期報告書と有価証券報告書が別個に分類され、年度が正しく抽出されることを検証"""
        p1 = self._create_dummy_pdf("20240331_有価証券報告書_S100TEST_7203.pdf")
        p2 = self._create_dummy_pdf("20240630_四半期報告書_S100TEST2_7203.pdf")
        p3 = self._create_dummy_pdf("20230331_有価証券報告書_S100TEST3_7203.pdf")
        p4 = self._create_dummy_pdf("その他_統合報告書_7203_Web.pdf")

        merged = group_and_merge_by_year([p1, p2, p3, p4], "7203", "トヨタ")
        merged_basenames = [os.path.basename(p) for p in merged]

        # 4つの独立したファイル（2024有報、2024四半期、2023有報、その他統合報告書）が生成されること
        self.assertTrue(any("2024_有価証券報告書" in name for name in merged_basenames))
        self.assertTrue(any("2024_四半期報告書" in name for name in merged_basenames))
        self.assertTrue(any("2023_有価証券報告書" in name for name in merged_basenames))
        self.assertTrue(any("その他_統合報告書" in name for name in merged_basenames))


if __name__ == "__main__":
    unittest.main()
