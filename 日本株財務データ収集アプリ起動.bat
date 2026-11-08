@echo off
chcp 65001 > nul

:: このbat自身のフォルダをアプリの場所とする（個人パスを埋め込まない）
cd /d "%~dp0"

:: 既存の全Streamlitプロセスは終了しない。
:: ポート8501が使用中なら二重起動せず、ブラウザだけ開く
netstat -ano | findstr ":8501" | findstr "LISTENING" >nul 2>nul
if %errorlevel%==0 (
  start "" "http://127.0.0.1:8501"
  exit
)

:: PATH上のPythonでStreamlitを起動する
start /min "" python -m streamlit run app.py --server.port=8501 --server.headless=true

:: Wait 7 seconds
ping 127.0.0.1 -n 8 > nul

:: Open browser
start "" "http://127.0.0.1:8501"
exit
