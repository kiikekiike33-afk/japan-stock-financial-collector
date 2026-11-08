# 日本株財務データ収集 & Google Drive連携ツール

証券コードを入力するだけで、有価証券報告書（EDINET）、適時開示情報（TDnet）、ESG・統合報告書（Web検索）、過去の株価・出来高データを自動収集・結合し、Google DriveやNotebookLMへワンストップで連携するツールです。

---

## 🌟 主な機能

- **EDINET 有価証券報告書取得**: 過去1年〜10年の有価証券報告書・四半期報告書を自動ダウンロード
- **TDnet 決算短信取得**: 過去3年分の決算短信を自動取得
- **ESG・統合報告書のWeb検索**: DuckDuckGo検索を用いて最新の統合報告書・サステナビリティレポートを発見・収集
- **株価・出来高データ取得**: Yahoo Finance（yfinance）から過去3年分の株価推移をCSVとして出力
- **年度別PDF自動結合**: 散らばるレポートを年度・種別ごとに自動で1つのPDFに結合
- **Google Drive 自動アップロード**: 銘柄ごとのフォルダを作成し、整理した状態でDriveへ同期
- **NotebookLM 連携**: 収集した資料をNotebookLMのソースとして自動登録

---

## 📁 フォルダ構成

```text
├── app.py                     # Streamlit メインアプリケーション
├── launcher.pyw               # バックグラウンド起動スクリプト
├── launch_silent.vbs          # コマンドプロンプトを非表示で起動するVBS
├── 日本株財務データ収集アプリ起動.bat  # ワンクリック起動用バッチ
├── requirements.txt           # 依存ライブラリ一覧
├── .env.example               # 環境変数テンプレート
├── .gitignore                 # 機密情報・キャッシュの除外設定
└── src/
    ├── api/                   # 各種データ取得（EDINET, TDnet, ESG, 株価, 競合他社）
    ├── automation/            # NotebookLM等のブラウザ自動化（Playwright）
    ├── cloud/                 # Google Drive アップロード連携
    ├── processing/            # PDF結合・データ整形処理
    └── utils/                 # 設定・証券コード変換等のユーティリティ
```

---

## 🚀 セットアップ手順

### 1. 依存ライブラリのインストール

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. 環境変数の設定

`.env.example` をコピーして `.env` を作成し、EDINET APIキーを設定します。

```bash
cp .env.example .env
```

`.env` 内の `EDINET_API_KEY` に金融庁から取得したAPIキーを入力してください。

### 3. Google Drive API 連携（任意）

Google Driveへの自動アップロードを利用する場合は、Google Cloud Consoleで作成した `credentials.json` を本プロジェクトのルートディレクトリに配置してください。

---

## 🖥️ 起動方法

### ローカルPCでの起動

Windows環境では、`日本株財務データ収集アプリ起動.bat` をダブルクリックするだけでブラウザが開き、アプリが起動します。

コマンドラインから起動する場合：

```bash
streamlit run app.py
```

---

## 📱 スマホでの利用 & Muse連携について

- **スマホからの閲覧・操作**: Streamlit Community Cloud（無料）と連携することで、スマホのブラウザからどこでも操作できるようになります。
- **Meta AIエージェント「Muse」との連携**: 本GitHubリポジトリをMuseアプリに接続することで、スマホから「〇〇機能を追加して」「エラーを修正して」と指示を出し、Museにコードを直接編集・改善させることができます。
