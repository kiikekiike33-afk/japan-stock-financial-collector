import os
import unittest
import tempfile
import json
from datetime import datetime, timedelta
import src.api.edinet as edinet


class TestEdinetCache(unittest.TestCase):
    def setUp(self):
        self.orig_cache_dir = edinet._LIST_CACHE_DIR
        self.orig_mem_cache = dict(edinet._list_mem_cache)
        self.temp_dir = tempfile.TemporaryDirectory()
        edinet._LIST_CACHE_DIR = self.temp_dir.name
        edinet._list_mem_cache.clear()

    def tearDown(self):
        edinet._LIST_CACHE_DIR = self.orig_cache_dir
        edinet._list_mem_cache = self.orig_mem_cache
        self.temp_dir.cleanup()

    def test_past_date_caching_writes_to_disk(self):
        """過去日のデータはディスクに永続化されることを検証"""
        past_date = datetime.now() - timedelta(days=10)
        date_str = past_date.strftime("%Y-%m-%d")
        dummy_results = [{"docID": "S100PAST", "title": "Test Report"}]

        edinet._store_cached_list(date_str, dummy_results, past_date)

        # ディスク上にファイルが存在すること
        expected_path = edinet._list_cache_path(date_str)
        self.assertTrue(os.path.exists(expected_path))

        # メモリをクリアしてもディスクから再ロードできること
        edinet._list_mem_cache.clear()
        loaded = edinet._load_cached_list(date_str)
        self.assertEqual(loaded, dummy_results)

    def test_today_caching_does_not_write_to_disk(self):
        """当日分のデータは更新可能性のためディスクには書き込まないことを検証"""
        today = edinet.get_current_tokyo_date()
        date_str = today.strftime("%Y-%m-%d")
        dummy_results = [{"docID": "S100TODAY", "title": "Today Report"}]

        edinet._store_cached_list(date_str, dummy_results, today)

        # ディスク上にファイルが存在しないこと
        expected_path = edinet._list_cache_path(date_str)
        self.assertFalse(os.path.exists(expected_path))

        # メモリキャッシュからは取得可能であること
        self.assertEqual(edinet._load_cached_list(date_str), dummy_results)


if __name__ == "__main__":
    unittest.main()
