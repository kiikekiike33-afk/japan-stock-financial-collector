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
    # 処理中の誤操作（タブ閉じ・リロード）防止スクリプト
    components.html("""
        <script>
            const preventClose = function(e) {
                e.preventDefault();
                e.returnValue = '';
            };
            window.parent.addEventListener('beforeunload', preventClose);
        </script>
    """, height=0)

    import src.utils.config as config
    if not config.EDINET_API_KEY or config.EDINET_API_KEY == "your_edinet_api_key_here" or "ここに" in config.EDINET_API_KEY:
        st.error(".env ファイルに「EDINET APIキー」を設定してください。")
        st.stop()
    
    # 全角→半角変換 (英数字対応)
    zenkaku_chars = "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ，　"
    hankaku_chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz, "
    trans_map = str.maketrans(zenkaku_chars, hankaku_chars)
    normalized_input = ticker_input.translate(trans_map)
    raw_tickers = re.split(r'[,\s]+', normalized_input.strip())
    base_tickers = [t.strip().upper() for t in raw_tickers if t.strip().isalnum() and len(t.strip()) == 4]
    
    if not base_tickers:
        st.error("正しい4桁の証券コードを入力してください。")
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
        
        # グループフォルダ名（競合を含む場合のみ）
        if include_peers and len(group_tickers) > 1:
            peer_str = "、".join(group_tickers[1:])
            group_folder_name = f"{base_ticker}_{base_name}_競合（{peer_str}）" if base_name else f"{base_ticker}_競合（{peer_str}）"
        else:
            group_folder_name = None
        
        # グループ内の各銘柄を処理
        for idx, ticker in enumerate(group_tickers):
            c_name = name_map.get(ticker, "") or ""
            display_name = f"{ticker}_{c_name}" if c_name else ticker
            
            st.markdown(f"#### 🚀 [{idx+1}/{len(group_tickers)}] {display_name}")
            
            # EDINET Code mapping (optional now)
            edinet_code = ticker_to_edinet(ticker)
            if edinet_code:
                st.success(f"EDINETコード: {edinet_code}")
            else:
                st.warning(f"EDINETコードが辞書に見つかりません。証券コード ({ticker}) から直接書類を検索します。")
                
            status_text = st.empty()
            progress_bar = st.progress(0)
            
            try:
                # 1. EDINET
                status_text.text(f"EDINETから有価証券報告書等を取得中... (過去{target_years}年)")
                edinet_pdfs = fetch_and_save_edinet_reports(ticker, edinet_code, target_years)
                progress_bar.progress(30)
                
                # 2. TDnet (IR Bank)
                status_text.text("適時開示情報を取得中...")
                tdnet_pdfs = search_and_download_tdnet_docs(ticker, target_years)
                progress_bar.progress(50)
                
                # 3. ESG / 統合報告書
                esg_pdfs = []
                if fetch_esg:
                     status_text.text("統合報告書・ESGレポートを検索中...")
                     esg_pdfs = fetch_integrated_esg_reports(ticker, company_name=c_name)
                progress_bar.progress(60)
                
                all_pdfs = edinet_pdfs + tdnet_pdfs + esg_pdfs
                # 重複パスを削除
                all_pdfs = list(dict.fromkeys(all_pdfs))
                
                if not all_pdfs:
                    status_text.warning(f"{display_name} の該当ドキュメントが見つかりませんでした。")
                    continue
                # 4. Merge
                upload_targets = all_pdfs
                if merge_options:
                    status_text.text("年度ごとにPDFを結合中...")
                    merged_pdfs = group_and_merge_by_year(all_pdfs, ticker, company_name=c_name)
                    if merged_pdfs:
                        upload_targets = merged_pdfs
                progress_bar.progress(80)
                # 4.5. 株価データの取得
                if fetch_stock:
                    status_text.text("過去3年分の株価・出来高データを取得中...")
                    stock_pdf = fetch_3y_stock_data(ticker, company_name=c_name)
                    if stock_pdf:
                        upload_targets.append(stock_pdf)
                
                # 5. Google Driveへアップロード
                status_text.text("Google Driveへアップロード中...")
                folder_link, file_links = upload_to_drive(display_name, upload_targets, group_folder_name=group_folder_name)
                progress_bar.progress(100)
                
                status_text.success(f"{display_name} 完了！ ({len(upload_targets)}件)")
                st.markdown(f"📁 **{display_name}:** [Google Driveで確認]({folder_link})")
                st.session_state.all_folder_links.append((display_name, folder_link))
                st.session_state.all_file_links_by_base[base_label].extend(file_links)
                
            except Exception as e:
                status_text.error(f"{display_name} の処理中にエラー: {str(e)}")
                print(f"Error processing {display_name}: {e}")
                st.exception(e)
    # 処理完了：誤操作防止スクリプトを解除
    components.html("""
        <script>
            window.parent.onbeforeunload = null;
        </script>
    """, height=0)

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
                    
                    # リンクを一時ファイルに保存して渡す（文字数オーバー対策）
                    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json", encoding="utf-8") as tf:
                        json.dump({"links": links, "notebook_name": base_label}, tf)
                        temp_file_path = tf.name
                        
                    subprocess.Popen([sys.executable, bot_path, temp_file_path])
                    st.success("🤖 ブラウザを起動しました！別ウィンドウでお待ちください（初回は手動でGoogleログインが必要です）。")
elif "start_processing" in st.session_state and st.session_state.start_processing:
    # If it was processed but nothing found
    if not st.session_state.all_folder_links:
        st.warning("アップロードに成功した銘柄がありませんでした。")

st.markdown("---")
st.markdown("### 🛠 既存のURLをNotebookLMに転送 (手動入力)")
with st.expander("既にGoogle DriveにあるURLを転送する場合はこちら"):
    st.info("過去に生成したGoogle DriveのフォルダURL、またはファイルURLリストを直接入力してください。")
    
    # フォルダURL
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
                    
                    # リンクを一時ファイルに保存して渡す（文字数オーバー対策）
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
            

