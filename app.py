import streamlit as st
import time
import re
from src.utils.mapper import ticker_to_edinet
from src.api.peers import get_competitors

st.set_page_config(page_title="日本株財務データ収集", page_icon="📈", layout="wide")

st.title("日本株財務データ収集 & Google Drive連携ツール")
st.markdown("""
証券コードを入力するだけで、過去の有価証券報告書や適時開示情報、さらに**ESG・統合報告書**も自動検索・収集し、
指定のフォーマットに結合してGoogle Driveへアップロードします。
""")

with st.sidebar:
    st.header("設定")
    ticker_input = st.text_input("証券コード (メイン銘柄)", value="")
    years = st.selectbox("取得期間", ["過去1年", "過去3年", "過去5年", "過去10年"], index=2)
    merge_options = st.checkbox("年度・種別ごとにPDFを結合する", value=True)
    fetch_esg = st.checkbox("統合報告書・ESGレポートも検索(Web)", value=True)
    include_peers = st.checkbox("同業他社も含めて収集する", value=True)
    fetch_stock = st.checkbox("過去3年分の株価・出来高データも取得する", value=True)
    
    start_button = st.button("🚀 データ収集を開始", type="primary")

if start_button:
    st.session_state.start_processing = True
    import streamlit.components.v1 as components
    # 処理中の誤操作（タブ閉じ・リロード）防止スクリプト（指示11: 解除可能な同一ハンドラ登録）
    components.html("""
        <script>
            window.parent.__preventCloseHandler = function(e) {
                e.preventDefault();
                e.returnValue = '';
            };
            window.parent.addEventListener('beforeunload', window.parent.__preventCloseHandler);
        </script>
    """, height=0)

    import src.utils.config as config
    if not config.EDINET_API_KEY or config.EDINET_API_KEY == "your_edinet_api_key_here" or "ここに" in config.EDINET_API_KEY:
        st.error(".env ファイルに「EDINET APIキー」を設定してください。")
        st.session_state.start_processing = False
        st.stop()
    
    # 全角→半角変換 (英数字対応)
    zenkaku_chars = "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ，　"
    hankaku_chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz, "
    trans_map = str.maketrans(zenkaku_chars, hankaku_chars)
    normalized_input = ticker_input.translate(trans_map)
    raw_tickers = re.split(r'[,\s]+', normalized_input.strip())
    
    base_tickers = []
    invalid_tickers = []
    for t in raw_tickers:
        clean_t = t.strip().upper()
        if not clean_t:
            continue
        if clean_t.isalnum() and len(clean_t) == 4:
            base_tickers.append(clean_t)
        else:
            invalid_tickers.append(clean_t)
            
    # 【指示11改修】除外された無効コードを画面に明示
    if invalid_tickers:
        st.warning(f"以下の入力は4桁の銘柄コード形式に合致しないため除外しました: {', '.join(invalid_tickers)}")
    
    if not base_tickers:
        st.error("正しい4桁の証券コードを入力してください。")
        st.session_state.start_processing = False
        st.stop()
    
    from src.utils.mapper import ticker_to_edinet, get_company_name
    from src.api.edinet import fetch_and_save_edinet_reports
    from src.api.tdnet import search_and_download_tdnet_docs
    from src.api.esg_reports import fetch_integrated_esg_reports
    from src.processing.pdf_merger import group_and_merge_by_year
    from src.cloud.gdrive import upload_to_drive
    from src.api.stock_data import fetch_3y_stock_data
    
    year_map = {"過去1年": 1, "過去3年": 3, "過去5年": 5, "過去10年": 10}
    target_years = year_map.get(years, 1)
    
    if "all_folder_links" not in st.session_state:
        st.session_state.all_folder_links = []
    if "all_file_links_by_base" not in st.session_state:
        st.session_state.all_file_links_by_base = {}
        
    st.session_state.all_folder_links = []
    st.session_state.all_file_links_by_base = {}
    
    # === 入力銘柄ごとに独立して処理する ===
    for base_idx, base_ticker in enumerate(base_tickers):
        st.markdown("---")
        base_name = get_company_name(base_ticker)
        base_label = f"{base_ticker}_{base_name}" if base_name else base_ticker
        st.session_state.all_file_links_by_base[base_label] = []
        st.header(f"📊 [{base_idx+1}/{len(base_tickers)}] {base_label} グループ")
        
        # この銘柄の処理対象リスト作成
        group_tickers = [base_ticker]
        if include_peers:
            with st.spinner(f"{base_label} の同業他社を検索中（株探 + 時価総額ソート）..."):
                found_peers = get_competitors(base_ticker)
                group_tickers = list(dict.fromkeys([base_ticker] + found_peers))
        
        # グループ内全銘柄の企業名を取得
        name_map = {base_ticker: base_name}
        with st.spinner("企業名を取得中..."):
            for t in group_tickers:
                if t not in name_map:
                    name_map[t] = get_company_name(t)
        
        # 処理対象の表示
        labels = [f"{t} - {name_map.get(t, '')}" if name_map.get(t) else t for t in group_tickers]
        st.info(f"対象: {', '.join(labels)}")
        
        # アップロード先フォルダ名
        group_folder_name = f"{base_label}_同業分析セット" if len(group_tickers) > 1 else None
        
        for idx, ticker in enumerate(group_tickers):
            company_name = name_map.get(ticker, "")
            display_name = f"{ticker}_{company_name}" if company_name else ticker
            st.subheader(f"[{idx+1}/{len(group_tickers)}] {display_name}")
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            downloaded_files = []
            
            try:
                # 1. EDINET
                status_text.text("EDINETで有価証券報告書を検索中...")
                edinet_code = ticker_to_edinet(ticker)
                
                def edinet_progress(p):
                    progress_bar.progress(int(p * 20))
                    
                edinet_files = fetch_and_save_edinet_reports(ticker, edinet_code, years=target_years, progress_callback=edinet_progress)
                downloaded_files.extend(edinet_files)
                
                # 2. TDnet (IR Bank)
                status_text.text("IR Bankで決算短信等を検索中...")
                def tdnet_progress(p):
                    progress_bar.progress(20 + int(p * 20))
                    
                tdnet_files = search_and_download_tdnet_docs(ticker, years=target_years, progress_callback=tdnet_progress)
                downloaded_files.extend(tdnet_files)
                
                # 3. ESG・統合報告書 (Web)
                if fetch_esg:
                    status_text.text("WebからESG・統合報告書を検索中...")
                    progress_bar.progress(50)
                    esg_files = fetch_integrated_esg_reports(ticker, company_name)
                    downloaded_files.extend(esg_files)
                
                # 4. 株価データ (過去3年分)
                if fetch_stock:
                    status_text.text("過去3年分の株価データを取得中...")
                    progress_bar.progress(60)
                    stock_csv = fetch_3y_stock_data(ticker, company_name)
                    if stock_csv:
                        downloaded_files.append(stock_csv)
                
                progress_bar.progress(70)
                
                # 5. PDF結合
                upload_targets = []
                csv_files = [f for f in downloaded_files if f.endswith('.csv')]
                pdf_files = [f for f in downloaded_files if f.endswith('.pdf')]
                
                if merge_options and pdf_files:
                    status_text.text("PDFを年度・種別ごとに結合中...")
                    merged_files = group_and_merge_by_year(pdf_files, ticker, company_name)
                    upload_targets.extend(merged_files)
                else:
                    upload_targets.extend(pdf_files)
                    
                upload_targets.extend(csv_files)
                
                progress_bar.progress(85)
                
                # 6. Google Driveへアップロード
                status_text.text("Google Driveへアップロード中...")
                folder_link, file_links = upload_to_drive(display_name, upload_targets, group_folder_name=group_folder_name)
                progress_bar.progress(100)
                
                status_text.success(f"{display_name} 完了！ ({len(upload_targets)}件)")
                if folder_link:
                    st.markdown(f"📁 **{display_name}:** [Google Driveで確認]({folder_link})")
                    st.session_state.all_folder_links.append((display_name, folder_link))
                st.session_state.all_file_links_by_base[base_label].extend(file_links)
                
            except Exception as e:
                status_text.error(f"{display_name} の処理中にエラー: {str(e)}")
                print(f"Error processing {display_name}: {e}")
                st.exception(e)
                
    # 【指示11改修】処理完了：誤操作防止スクリプトを確実に解除し、状態をリセット
    components.html("""
        <script>
            if (window.parent.__preventCloseHandler) {
                window.parent.removeEventListener('beforeunload', window.parent.__preventCloseHandler);
                window.parent.__preventCloseHandler = null;
            }
            window.parent.onbeforeunload = null;
        </script>
    """, height=0)
    st.session_state.start_processing = False

st.markdown("---")
if "all_folder_links" in st.session_state and st.session_state.all_folder_links:
    st.success("🎉 すべての銘柄の処理が完了しました！")
    for t, lnk in st.session_state.all_folder_links:
         st.markdown(f"- **{t}**: [Google Driveで確認]({lnk})")
         
    # NotebookLM用 URLリストの表示
    if "all_file_links_by_base" in st.session_state and st.session_state.all_file_links_by_base:
        st.markdown("---")
        st.markdown("### 🧠 NotebookLM への自動格納用URL")
        st.info("以下のURLリストを各グループごとにコピーし、NotebookLMの「ソースの追加」→「ウェブサイト」欄にペーストすることで一括読み込みが可能です！")
        
        for base_label, links in st.session_state.all_file_links_by_base.items():
            if links:
                st.markdown(f"**{base_label} グループ**")
                st.code("\n".join(links), language="text")
                
                if st.button(f"🤖 {base_label}をNotebookLMに自動転送（実験的）", key=f"bot_{base_label}"):
                    import subprocess
                    import sys
                    import os
                    import tempfile
                    import json
                    bot_path = os.path.join(os.path.dirname(__file__), "src", "automation", "notebooklm_bot.py")
                    
                    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json", encoding="utf-8") as tf:
                        json.dump({"links": links, "notebook_name": base_label}, tf)
                        temp_file_path = tf.name
                        
                    subprocess.Popen([sys.executable, bot_path, temp_file_path])
                    st.success("🤖 ブラウザを起動しました！別ウィンドウでお待ちください（初回は手動でGoogleログインが必要です）。")
elif "start_processing" in st.session_state and st.session_state.start_processing:
    if not st.session_state.all_folder_links:
        st.warning("アップロードに成功した銘柄がありませんでした。")

st.markdown("---")
st.markdown("### 🛠 既存のURLをNotebookLMに転送 (手動入力)")
with st.expander("既にGoogle DriveにあるURLを転送する場合はこちら"):
    st.info("過去に生成したGoogle DriveのフォルダURL、またはファイルURLリストを直接入力してください。")
    
    folder_url_input = st.text_input("📁 Google Drive フォルダURL", key="folder_url_input", help="ここにフォルダURLを貼り付けてボタンを押すと、自動でNotebookLMへ転送されます。")
    if st.button("🤖 フォルダURLからNotebookLMに一括転送", key="bot_folder"):
        if folder_url_input:
            from src.cloud.gdrive import get_file_links_from_folder_url
            try:
                fetched_links, fetched_folder_name = get_file_links_from_folder_url(folder_url_input)
                if fetched_links:
                    st.success(f"「{fetched_folder_name}」から {len(fetched_links)}件のファイルリンクを取得しました。ブラウザを起動します！")
                    import subprocess
                    import sys
                    import os
                    import tempfile
                    import json
                    bot_path = os.path.join(os.path.dirname(__file__), "src", "automation", "notebooklm_bot.py")
                    
                    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json", encoding="utf-8") as tf:
                        json.dump({"links": fetched_links, "notebook_name": fetched_folder_name}, tf)
                        temp_file_path = tf.name
                        
                    subprocess.Popen([sys.executable, bot_path, temp_file_path])
                else:
                    st.warning("フォルダ内にファイルが見つかりませんでした。")
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
        else:
            st.warning("フォルダURLを入力してください。")
