# Antigravity向けセットアップ指示書（初回のみ）

対象リポジトリ: `kiikekiike33-afk/japan-stock-financial-collector`（Public）
このアプリは Antigravity（ユーザーのPC）で作成され、Muse が監査・修正を担当する。
運用はパチスロアプリ（pachislot-analyzer）と同じ「GitHub経由の指示ループ」とする。

## 全体像

- `main` … 本番。Muse の修正はPR経由でのみ入り、マージはユーザーの指示があった時だけ。
- `auto-sync` … 作業用ブランチ。PC側コードの同期先であり、指示掲示板の置き場。
- `inbox/TASKS_FROM_MUSE.md` … Muse → Antigravity の指示掲示板。
- `inbox/REPORT_TO_MUSE.md` … Antigravity → Muse の報告掲示板（追記のみ、過去分を消さない）。

ユーザーが Antigravity に「最新の指示を実施して」と言ったら、
Antigravity は auto-sync を pull し、TASKS の未完了の指示を実施し、
結果を REPORT に追記して auto-sync へ push すること。以後の指示はこの往復だけで回す。

## 初回セットアップ（この指示書の実施手順）

1. **PC側プロジェクトとリポジトリを git で接続する**
   - 既存の作業フォルダ（起動スクリプトに残っていた `chrono-equinox` フォルダが候補）が
     このリポジトリの clone でない場合は、そのフォルダをリモート
     `https://github.com/kiikekiike33-afk/japan-stock-financial-collector.git`
     に接続するか、新規フォルダへ clone して移行する。
   - どちらの方法を取ったか、最終的なプロジェクトフォルダのフルパスを REPORT に書くこと。
2. **マージ済みP0修正を取り込む**
   - main の最新（PR #1 マージ済み、merge commit 12d80d6 以降）を pull する。
   - 取り込み後、コードが手元の作業内容と競合した場合は勝手に上書きせず、競合箇所を REPORT に書いて止まること。
3. **自動同期を用意する（パチンコと同じ方式、費用ゼロ・低負荷）**
   - Windowsタスクスケジューラで10分ごとに実行する同期スクリプトを用意する。
   - 動作: auto-sync ブランチに対して `pull --rebase` → 変更があればコミット → `push`。
     対象は auto-sync のみ。main へは一切 push しない。
   - 変更が無い回は何もしない（空コミットを作らない）。競合したら push せずログに残して止まる。
   - 同期対象から必ず除外: `.env`、`credentials.json`、`token.json`、`notebooklm_profile/`、
     `output/`、`temp_downloads/`、各種ログ・キャッシュ（`.gitignore` が既に除外しているか最初に確認すること）。
   - GitHub側は無料枠のみを使う。GitHub Actions等の有料・従量の仕組みは導入しない。
4. **動作確認**
   - `pip install -r requirements.txt`（matplotlib / japanize-matplotlib が増えている）後に
     `streamlit run app.py` でアプリが起動することだけ確認する（データ収集の実行はしない）。
   - EDINET APIキー等の秘密情報は、同期にも報告にも絶対に含めない。
5. **報告**
   - 上記1〜4の結果（接続方法、プロジェクトパス、自動同期の登録有無、起動確認の成否）を
     `inbox/REPORT_TO_MUSE.md` の指示2026-11-08-01 欄に追記し、auto-sync へ push する。

## 守ること

- 推定値・モック値を実データとして扱わない。取得できなかったものは「取得不可」と報告する。
- main へのマージや push はユーザーの明示指示がある時だけ（Muse がPRを作り、ユーザーが判断する）。
- 外部サイトへのアクセスは各サイトの規約と負荷に配慮し、自動取得の可否が不明なものは実施前に報告へ書く。
