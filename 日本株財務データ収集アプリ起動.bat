@echo off
chcp 65001 > nul

:: Stop existing Streamlit process
taskkill /F /IM streamlit.exe >nul 2>nul

:: Change directory
cd /d "C:\Users\kiike\.gemini\antigravity\playground\chrono-equinox"

:: Start Streamlit in background using conda
start /min "" "C:\Users\kiike\miniforge3\condabin\conda.bat" run -n chrono_env streamlit run app.py --server.port=8501 --server.headless=true

:: Wait 7 seconds
ping 127.0.0.1 -n 8 > nul

:: Open browser
start "" "http://127.0.0.1:8501"
exit
