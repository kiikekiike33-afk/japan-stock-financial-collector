# 日本株財務データ収集 & Google Drive連携ツール

証券コードを入力するだけで、有価証券報告書（EDINET）、適時開示情報（TDnet / IR Bank）、ESG・統合報告書（Web検索）、過去の株価・出来高データを自動収集・結合し、Google Driveへワンストップで連携するツールです。ローカルPCでも Streamlit Cloud でも動作します。

---

## 🌟 主な機能

- **EDINET 有価証券報告書取得**: 過去1年〜10年の有価証券報告書（120）・四半期報告書（140）を安全にダウンロード（日次一覧キャッシュ対応、docID付与による重複上書き防止）
- **TDnet 決算短信取得**: IR Bankの企業ページから決算短信・説明資料・業績予想修正等をダウンロード（PDFヘッダ検証機能付き）
  - ※取得範囲: IR Bankの仕様上、当該企業ページに一括掲載されている過去約10年分（2013年以降）が対象です。
- **ESG・統合報告書のWeb検索**: DuckDuckGo検索を用いて企業の統合報告書・サステナビリティレポートを厳格な企業名・年度検証付きで取得（100MBサイズ上限あり）
- **株価・出来高データ取得**: Yahoo Finance（yfinance）から過去3年分の株価推移をCSVとして出力
- **年度別PDF自動結合**: 散らばるレポートを年度・種別（四半期報告書は有報と分離）ごとに自動で結合
- **Google Drive 自動アップロード**: 銘柄ごとのフォルダを作成し同期（既存同名ファイルは自動スキップ）

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
│   ├── cloud/                 # Google Drive アップロード連携
│   ├── processing/            # PDF結合・データ整形処理
│   └── utils/                 # 設定・証券コード変換等のユーティリティ
├── tools/
│   ├── auto_sync.ps1          # GitHub auto-sync 自動同期スクリプト
│   ├── auto_sync_task.xml     # タスクスケジューラ定義
└── tests/                     # 単体テスト群
```

---

## 🚀 セットアップ手順

### 1. 依存ライブラリのインストール

```bash
pip install -r requirements.txt
```

### 2. 環境変数の設定

`.env.example` をコピーして `.env` を作成し、各種設定を行います。

```bash
cp .env.example .env
```

- `EDINET_API_KEY`: 金融庁から取得したAPIキーを入力します。
- `GDRIVE_ROOT_FOLDER_ID`: （任意）Google Driveの保存先フォルダID。未設定の場合はマイドライブ直下に保存されます。

### 3. Google Drive API 連携（任意）

Google Driveへの自動アップロードを利用する場合は、次のどちらかで認証します。

- **ローカルPC**: Google Cloud Consoleで作成した OAuth クライアント情報 `credentials.json` を本プロジェクトのルートディレクトリに配置してください（初回実行時に対話型ブラウザ認証が行われ、`token.json` が生成されます）。
- **Streamlit Cloud**: ブラウザ認証ができないため、PCで一度生成した `token.json` の中身を、アプリの Secrets に `GDRIVE_TOKEN_JSON` として設定してください（更新トークンで自動的に認証が継続します）。

---

## 🖥️ 動作環境と利用方法

### ローカルPCでの利用

Windows環境では、`日本株財務データ収集アプリ起動.bat` をダブルクリックするだけでブラウザが開き、アプリが起動します。

### Streamlit Cloud での利用

Streamlit Community Cloud にデプロイすれば、スマホからもそのまま利用できます。デプロイ時にアプリの Secrets へ以下を設定してください。

- `EDINET_API_KEY`: 金融庁のAPIキー
- `GDRIVE_TOKEN_JSON`: PCで生成した `token.json` の中身（Google Drive連携を使う場合）
- `GDRIVE_ROOT_FOLDER_ID`: （任意）保存先フォルダID

注意点:
- Cloud のディスクは再起動で消えるため、EDINET 日次一覧キャッシュは保持されません（毎回まっさらな状態から走査します）。
- 無料枠のリソース制限があるため、長期間・多数銘柄の一括実行は途中で制限に当たる場合があります。

※ NotebookLM への自動登録機能は廃止しました（旧バージョンにあった Playwright による自動転送は削除済み）。アップロード済みファイルのURL一覧はアプリ内に表示されるので、必要な場合はコピーして手動でご利用ください。

### Meta AIエージェント「Muse」との連携

本リポジトリの `auto-sync` ブランチを経由して、スマホのMuseから指示を出し、PC側のAntigravityがタスクを実行・報告する「自動指示ループ」に対応しています。
