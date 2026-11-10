import unittest
from src.api.tdnet import TARGET_KEYWORDS

class TestTDnetKeywordFilter(unittest.TestCase):
    """TDnet適時開示のキーワードフィルタリング単体テスト"""

    def is_target_title(self, title: str) -> bool:
        """tdnet.py と同一のキーワードマッチング判定"""
        return any(kw in title for kw in TARGET_KEYWORDS)

    def test_leak_and_risk_titles_pass(self):
        """1. 漏えい・リスク関連のタイトルがフィルタを通過することを確認"""
        leak_titles = [
            "当社システムへの不正アクセスによる個人情報漏えいに関するお知らせ（15:30）",
            "当社連結子会社における不正アクセスによる個人情報漏えいに関する調査結果及び再発防止策について(第三報)（12:00）",
            "当社連結子会社における不正アクセスによる個人情報漏えいに関する専用お問い合わせ窓口開設のお知らせ（13:00）",
            "当社連結子会社における不正アクセスによる個人情報漏えいに関するお知らせ（11:30）",
            "第三者委員会による特別調査報告書の受領に関するお知らせ",
            "サイバー攻撃によるシステム障害および特別損失の計上について",
            "当社に対する行政処分および改善報告書の提出に関するお詫び"
        ]
        for title in leak_titles:
            with self.subTest(title=title):
                self.assertTrue(self.is_target_title(title), f"漏えい・リスク開示が通過していません: {title}")

    def test_conventional_financial_titles_pass(self):
        """2. 従来の決算・業績関連タイトルが引き続き通過することを確認"""
        conventional_titles = [
            "2026年3月期 決算短信〔日本基準〕(連結)",
            "2026年3月期 第2四半期決算説明資料",
            "決算補足説明資料",
            "通期連結業績予想の修正に関するお知らせ",
            "連結業績予想と実績値との差異に関するお知らせ"
        ]
        for title in conventional_titles:
            with self.subTest(title=title):
                self.assertTrue(self.is_target_title(title), f"決算・業績開示が通過していません: {title}")

    def test_unrelated_titles_rejected(self):
        """3. 無関係なタイトル（人事異動、招集通知等）が除外されることを確認"""
        unrelated_titles = [
            "代表取締役の異動に関するお知らせ",
            "組織変更および人事異動に関するお知らせ",
            "第30回定時株主総会招集ご通知",
            "監査役の選任に関するお知らせ",
            "独立役員の届出に関するお知らせ",
            "東京オフィス移転のお知らせ"
        ]
        for title in unrelated_titles:
            with self.subTest(title=title):
                self.assertFalse(self.is_target_title(title), f"無関係な開示が誤って通過しています: {title}")

    def test_capital_policy_titles_pass(self):
        """4. 資本政策系タイトル（自己株式、配当等）が通過することを確認"""
        capital_titles = [
            "自己株式取得に係る事項の決定に関するお知らせ",
            "剰余金の配当（増配）に関するお知らせ",
            "株式分割および定款の一部変更に関するお知らせ",
            "株式会社〇〇の株式取得（子会社化）に関するお知らせ"
        ]
        for title in capital_titles:
            with self.subTest(title=title):
                self.assertTrue(self.is_target_title(title), f"資本政策開示が通過していません: {title}")

if __name__ == "__main__":
    unittest.main()
