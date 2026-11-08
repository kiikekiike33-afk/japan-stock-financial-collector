# 日本株財務データ収集 & Google Drive連携ツール

証券コードを入力するだけで、有価証券報告書（EDINET）、適時開示情報（TDnet / IR Bank）、ESG・統合報告書（Web検索）、過去の株価・出来高データを自動収集・結合し、Google DriveやNotebookLMへワンストップで連携するPCローカル実行型ツールです。

---

## 🌟 主な機能

- **EDINET 有価証券報告書取得**: 過去1年〜10年の有価証券報告書（120）・四半期報告書（140）を安全にダウンロード（日次一覧キャッシュ対応、docID付与による重複上書き防止）
- **TDnet 決算短信取得**: IR Bankの企業ページから決算短信・説明資料・業績予想修正等をダウンロード（PDFヘッダ検証機能付き）
  - ※取得範囲: IR Bankの仕様上、当該企業ページに一括掲載されている過去約10年分（2013年以降）が対象です。
- **ESG・統合報告書のWeb検索**: DuckDuckGo検索を用いて企業の統合報告書・サステナビリティレポートを厳格な企業名・年度検証付きで取得（100MBサイズ上限あり）
- **株価・出来高データ取得**: Yahoo Finance（yfinance）から過去3年分の株価推移をCSVとして出力
- **年度別PDF自動結合**: 散らばるレポートを年度・種別（四半期報告書は有報と分離）ごとに自動で結合
- **Google Drive 自動アップロード**: 銘柄ごとのフォルダを作成し同期（既存同名ファイルは自動スキップ）
- **NotebookLM 連携**: Playwright経由でGoogle Drive Pickerを自動操作し、収集した資料をNotebookLMのソースとして安全に登録

---

## 📁 フォルダ構成

```text
├── app.py                     # Streamlit メインアプリケーション
├── launcher.pyw               # バックグラウンド起動スクリプト
├── launch_silent.vbs          # コマンドプロンプトを非表示で起動するVBS
├── 日本株財務データ収集アプリ起動.bat  # ワンクリック起動用バッチ
├── requirements.txt           # 依存ライブラリ一覧（バージョン固定済み）
├── .env.example               # 環境変数テンプレート
├── .gitignore                 # 機密情報・キャッシュの除外設定
├── src/
│   ├── api/                   # 各種データ取得（EDINET, TDnet, ESG, 株価, 競合他社）
│   ├── automation/            # NotebookLM自動化（Playwright）
│   ├── cloud/                 # Google Drive アップロード連携
│   ├── processing/            # PDF結合・データ整形処理
│   └── utils/                 # 設定・証券コード変換等のユーティリティ
├── tools/
│   ├── auto_sync.ps1          # GitHub auto-sync 自動同期スクリプト
│   ├── auto_sync_task.xml     # タスクスケジューラ定義
│   └── debug/                 # 開発・解析用スクリプト置き場
└── tests/                     # 単体テスト群
```

---

## 🚀 セットアップ手順

### 1. 依存ライブラリのインストール

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. 環境変数の設定

`.env.example` をコピーして `.env` を作成し、各種設定を行います。

```bash
cp .env.example .env
```

- `EDINET_API_KEY`: 金融庁から取得したAPIキーを入力します。
- `GDRIVE_ROOT_FOLDER_ID`: （任意）Google Driveの保存先フォルダID。未設定の場合はマイドライブ直下に保存されます。

### 3. Google Drive API 連携（任意）

Google Driveへの自動アップロードを利用する場合は、Google Cloud Consoleで作成した OAuth クライアント情報 `credentials.json` を本プロジェクトのルートディレクトリに配置してください（初回実行時に対話型ブラウザ認証が行われ、`token.json` が生成されます）。

---

## 🖥️ 動作環境と利用方法（実態について）

### ローカルPCでの利用（推奨・基本設計）

本アプリは、以下の理由から**ローカルPC（Windows）での実行を前提**として設計されています：
1. **Google OAuth認証**: 初回ログイン時に対話型ローカルWebサーバーを開いてトークン（`token.json`）を生成します。
2. **NotebookLM自動化**: ローカルにインストールされたGoogle Chromeのプロファイル（Cookie・ログイン状態）をPlaywrightで直接制御します。

Windows環境では、`日本株財務データ収集アプリ起動.bat` をダブルクリックするだけでブラウザが開き、アプリが起動します。

### スマホでの閲覧・操作方法

完全クラウド（Streamlit Community Cloud等）上では上記OAuth認証やローカルChrome制御が動作しないため、スマホから操作する場合は以下の方法を推奨します：

- **同一Wi-Fiネットワーク経由**: PCでアプリを起動した状態で、コマンドラインに表示される `Network URL`（例: `http://192.168.x.x:8501`）を、同じWi-Fiに接続したスマホのブラウザで開くことで、スマホから直接データ収集を指示できます。

### Meta AIエージェント「Muse」との連携

本リポジトリの `auto-sync` ブランチを経由して、スマホのMuseから指示を出し、PC側のAntigravityがタスクを実行・報告する「自動指示ループ」に対応しています。
