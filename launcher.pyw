"""
日本株財務データ収集アプリ サイレントランチャー
pythonw.exe で実行することで、黒い画面を一切表示しない
"""
import subprocess
import os
import time
import webbrowser

# アプリのディレクトリ
APP_DIR = r"C:\Users\kiike\.gemini\antigravity\playground\chrono-equinox"

# conda環境のパス
CONDA_ENV = r"C:\Users\kiike\miniforge3\envs\chrono_env"
STREAMLIT_EXE = os.path.join(CONDA_ENV, "Scripts", "streamlit.exe")

# 既存プロセスを停止（エラーは無視）
subprocess.run(
    ["taskkill", "/F", "/IM", "streamlit.exe"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    creationflags=subprocess.CREATE_NO_WINDOW
)

# Streamlitをバックグラウンドで起動
# CREATE_NO_WINDOW フラグでコンソールウィンドウを表示しない
env = os.environ.copy()
env["PATH"] = CONDA_ENV + ";" + os.path.join(CONDA_ENV, "Scripts") + ";" + os.path.join(CONDA_ENV, "Library", "bin") + ";" + env.get("PATH", "")

subprocess.Popen(
    [STREAMLIT_EXE, "run", "app.py", "--server.port=8501", "--server.headless=true"],
    cwd=APP_DIR,
    env=env,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    creationflags=subprocess.CREATE_NO_WINDOW
)

# サーバー起動を待つ
time.sleep(7)

# ブラウザを開く
webbrowser.open("http://127.0.0.1:8501")
