"""
日本株財務データ収集アプリ サイレントランチャー
pythonw.exe で実行することで、黒い画面を一切表示しない

- アプリの場所はこのファイル自身の場所から決める（個人パスを埋め込まない）
- streamlit.exe の全プロセス終了はしない。ポート8501で既に起動中なら
  ブラウザを開くだけで終わる
"""
import os
import shutil
import socket
import subprocess
import sys
import time
import webbrowser

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = 8501


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _streamlit_command():
    """streamlit の起動コマンドを環境から解決する。"""
    exe = shutil.which("streamlit")
    if exe:
        return [exe]
    sibling = os.path.join(os.path.dirname(sys.executable), "streamlit.exe")
    if os.path.exists(sibling):
        return [sibling]
    # 最終手段: 現在のPythonでモジュールとして起動
    return [sys.executable, "-m", "streamlit"]


if _port_in_use(PORT):
    webbrowser.open(f"http://127.0.0.1:{PORT}")
else:
    subprocess.Popen(
        _streamlit_command() + [
            "run", os.path.join(APP_DIR, "app.py"),
            f"--server.port={PORT}", "--server.headless=true",
        ],
        cwd=APP_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    # 起動完了（ポートが開く）まで最大30秒待つ。固定sleepで失敗しないため
    for _ in range(60):
        if _port_in_use(PORT):
            break
        time.sleep(0.5)
    webbrowser.open(f"http://127.0.0.1:{PORT}")
