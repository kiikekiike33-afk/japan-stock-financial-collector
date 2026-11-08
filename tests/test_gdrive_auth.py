"""Drive認証（Secrets / 環境変数のトークン読み込み）の単体テスト。

ネットワークには接続しない。ダミーのトークン情報で Credentials が
生成できることと、不正な値が分かりやすいエラーになることを確認する。
"""
import json
import unittest

from src.cloud.gdrive import credentials_from_token_value

DUMMY_INFO = {
    "token": "dummy-access-token",
    "refresh_token": "dummy-refresh-token",
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_id": "dummy-client-id",
    "client_secret": "dummy-client-secret",
    "scopes": ["https://www.googleapis.com/auth/drive.file"],
}


class TestCredentialsFromTokenValue(unittest.TestCase):
    def test_from_json_string(self):
        creds = credentials_from_token_value(json.dumps(DUMMY_INFO))
        self.assertEqual(creds.refresh_token, "dummy-refresh-token")
        self.assertEqual(creds.client_id, "dummy-client-id")

    def test_from_dict(self):
        creds = credentials_from_token_value(dict(DUMMY_INFO))
        self.assertEqual(creds.refresh_token, "dummy-refresh-token")

    def test_invalid_json_raises(self):
        with self.assertRaises(ValueError):
            credentials_from_token_value("{not json")

    def test_missing_refresh_token_raises(self):
        info = dict(DUMMY_INFO)
        del info["refresh_token"]
        with self.assertRaises(ValueError):
            credentials_from_token_value(info)


if __name__ == "__main__":
    unittest.main()
