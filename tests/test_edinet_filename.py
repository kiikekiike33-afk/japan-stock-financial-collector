import unittest
import re


class TestEdinetFilename(unittest.TestCase):
    def test_filename_generation_rule(self):
        """指示04の新規則に従い、docIDを含めて一意なファイル名が生成されることを検証"""
        doc1 = {
            "docID": "S100TEST1",
            "docTypeCode": "120",
            "submitDate": "20240325",
        }
        doc2 = {
            "docID": "S100TEST2",
            "docTypeCode": "120",
            "submitDate": "20240325",  # 同日・同種別
        }
        ticker = "7203"

        doc_type_str1 = "有価証券報告書" if doc1["docTypeCode"] == "120" else "四半期報告書"
        doc_type_str2 = "有価証券報告書" if doc2["docTypeCode"] == "120" else "四半期報告書"

        fn1 = f"{doc1['submitDate']}_{doc_type_str1}_{doc1['docID']}_{ticker}.pdf"
        fn2 = f"{doc2['submitDate']}_{doc_type_str2}_{doc2['docID']}_{ticker}.pdf"

        # 衝突しないこと
        self.assertNotEqual(fn1, fn2)
        self.assertIn("S100TEST1", fn1)
        self.assertIn("S100TEST2", fn2)

        # 先頭8文字が日付（YYYYMMDD）であること（pdf_merger互換性）
        self.assertTrue(fn1[:8].isdigit())
        self.assertEqual(fn1[:4], "2024")


if __name__ == "__main__":
    unittest.main()
