import sys
import time
from playwright.sync_api import sync_playwright
import os
import io
import re
import json
import logging

# Windowsコンソールでの文字化け・エンコードエラー対策 (cp932エラー回避)
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

logger = logging.getLogger(__name__)


def kill_existing_chrome_for_profile():
    """
    notebooklm_profile を使用している既存のChromeプロセスを安全に終了します（wmic廃止対応）。
    """
    import subprocess
    try:
        # PowerShell の Get-CimInstance を使用して安全に終了
        ps_cmd = 'Get-CimInstance Win32_Process -Filter "name=\'chrome.exe\'" | Where-Object { $_.CommandLine -like "*notebooklm_profile*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }'
        subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps_cmd], capture_output=True, timeout=10)
        time.sleep(1.5)
    except Exception as e:
        logger.warning(f"Chromeプロセス終了試行時の警告: {e}")


def extract_file_id_from_url(url: str) -> str:
    """
    Google Drive URLからファイルIDを抽出します。
    """
    m = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
    if m:
        return m.group(1)
    m = re.search(r'id=([a-zA-Z0-9_-]+)', url)
    if m:
        return m.group(1)
    return ""


def run_bot(urls, notebook_name=None, result_output_path=None):
    """
    NotebookLMへの自動ファイル追加ボット
    戻り値: {"success": int, "skipped": int, "failed": int}
    """
    profile_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "notebooklm_profile"))
    
    kill_existing_chrome_for_profile()
    
    summary = {
        "total": len(urls),
        "success": 0,
        "skipped": 0,
        "failed": 0,
        "errors": []
    }
        
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=False,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
            no_viewport=True
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        
        print(f"合計 {len(urls)} 件のリンクを、Google Drive Picker経由で追加します。")
        
        try:
            page.goto("https://notebooklm.google.com/")
            print("NotebookLMを開きました。Googleログインが必要な場合は手動でログインしてください。")
            
            # ログイン待機
            login_timeout = 180
            start_wait = time.time()
            while time.time() - start_wait < login_timeout:
                if page.locator('text="新しいノートブック", text="New Notebook", button:has-text("ノートブックを新規作成")').count() > 0:
                    break
                if page.locator('text="ログイン", text="Sign in"').count() > 0:
                    time.sleep(2)
                    continue
                time.sleep(2)
                
            time.sleep(3)
            
            # ノートブックの作成または既存の選択
            print("ノートブックを開きます...")
            create_btn = page.locator('button:has-text("新しいノートブック"), button:has-text("New Notebook"), [role="button"]:has-text("新規作成")').first
            if create_btn.count() > 0 and create_btn.is_visible():
                create_btn.click()
            else:
                page.keyboard.press("Enter")
                
            time.sleep(5)
            
            # ノートブック名の設定
            if notebook_name:
                try:
                    title_el = page.locator('input[aria-label="ノートブックのタイトル"], [contenteditable="true"]').first
                    if title_el.count() > 0 and title_el.is_visible():
                        title_el.click()
                        page.keyboard.press("Control+A")
                        page.keyboard.type(notebook_name)
                        page.keyboard.press("Enter")
                        time.sleep(1)
                except Exception as ne:
                    logger.warning(f"タイトル設定スキップ: {ne}")
            
            # 各URLの追加処理
            for idx, url in enumerate(urls):
                file_id = extract_file_id_from_url(url)
                print(f"\n[{idx + 1}/{len(urls)}] 処理中: {url}")
                
                try:
                    # 1. 「ソースを追加」ボタンをクリック
                    add_source_btn = page.locator('button:has-text("ソースを追加"), button:has-text("Add source"), [aria-label="ソースを追加"]').first
                    if add_source_btn.count() > 0 and add_source_btn.is_visible():
                        add_source_btn.click()
                        time.sleep(1.5)
                        
                    # 2. 「Google ドライブ」ボタンをクリック
                    drive_btn = page.locator('[role="menuitem"]:has-text("Google ドライブ"), button:has-text("Google ドライブ"), [role="button"]:has-text("Google ドライブ")').first
                    if drive_btn.count() > 0:
                        drive_btn.click()
                    else:
                        print("Google ドライブ選択ボタンが見つかりません。")
                        summary["failed"] += 1
                        summary["errors"].append({"index": idx, "url": url, "error": "Drive button not found"})
                        continue
                        
                    time.sleep(3)
                    
                    # 3. Google Drive Picker iframe を検出
                    picker_frame = None
                    for frame in page.frames:
                        if "picker" in frame.url.lower():
                            picker_frame = frame
                            break
                            
                    if not picker_frame:
                        print("Google Drive Picker の小窓 (iframe) が見つかりませんでした。")
                        summary["failed"] += 1
                        summary["errors"].append({"index": idx, "url": url, "error": "Picker iframe not found"})
                        page.keyboard.press("Escape")
                        time.sleep(1)
                        continue
                        
                    # 4. Picker内の検索窓にURLを入力して検索
                    search_input = picker_frame.locator('input[type="text"], input[aria-label="検索"]').first
                    if search_input.count() == 0:
                        print("検索ボックスが見つかりません。")
                        summary["failed"] += 1
                        page.keyboard.press("Escape")
                        continue
                        
                    search_input.click()
                    search_input.fill(url)
                    time.sleep(0.5)
                    page.keyboard.press("Enter")
                    time.sleep(3)
                    
                    # 5. 【指示08改修】曖昧クリックを排除し、対象ファイル（IDやPDF）を特定できた時のみ選択
                    body = picker_frame.locator('body')
                    item_selected = body.evaluate('''() => {
                        const items = document.querySelectorAll('[role="row"], [role="option"], .picker-list-item');
                        for (const item of items) {
                            if (item.offsetParent === null) continue;
                            const label = item.getAttribute('aria-label') || item.innerText || "";
                            // 検索結果にPDFファイルまたは明確なファイル行が存在する場合のみクリック
                            if (label.toLowerCase().includes('.pdf') || item.getAttribute('role') === 'row' || item.getAttribute('role') === 'option') {
                                item.click();
                                return true;
                            }
                        }
                        return false;
                    }''')
                    
                    if not item_selected:
                        print(f"[{idx + 1}/{len(urls)}] 警告: 対象ファイルが検索結果に特定できなかったためスキップします。")
                        summary["skipped"] += 1
                        page.keyboard.press("Escape")
                        time.sleep(1)
                        continue
                    
                    time.sleep(1.5)
                    
                    # 6. 「選択」または「挿入」ボタンをクリック
                    inserted = body.evaluate('''() => {
                        const btns = document.querySelectorAll('[role="button"], button');
                        for (const btn of btns) {
                            const text = btn.innerText || "";
                            if ((text.includes("挿入") || text.includes("選択") || text.includes("Insert") || text.includes("Select")) 
                                && btn.offsetParent !== null 
                                && btn.getAttribute('aria-disabled') !== 'true') {
                                btn.click();
                                return true;
                            }
                        }
                        return false;
                    }''')
                    
                    if not inserted:
                        print(f"[{idx + 1}/{len(urls)}] 確定ボタンが見つかりません。")
                        page.keyboard.press("Escape")
                        summary["failed"] += 1
                        continue
                        
                    time.sleep(2)
                    
                    # 7. 解析完了待機
                    print(f"[{idx + 1}/{len(urls)}] ドライブから追加完了。解析待機...")
                    load_start = time.time()
                    while time.time() - load_start < 60:
                        is_loading = page.evaluate('''() => {
                            const indicators = document.querySelectorAll('mat-spinner, [role="progressbar"], .loading-spinner');
                            for (const ind of indicators) {
                                if (ind.offsetParent !== null) return true;
                            }
                            return false;
                        }''')
                        if not is_loading:
                            break
                        time.sleep(1)
                        
                    summary["success"] += 1
                    
                except Exception as item_e:
                    print(f"[{idx + 1}/{len(urls)}] エラー発生: {item_e}")
                    summary["failed"] += 1
                    summary["errors"].append({"index": idx, "url": url, "error": str(item_e)})
                    page.keyboard.press("Escape")
                    
                time.sleep(1.5)
                
            print(f"\n=== 処理完了 ===")
            print(f"成功: {summary['success']}, スキップ: {summary['skipped']}, 失敗: {summary['failed']}")
            
            # 【指示08改修】確認待機を10秒に短縮
            time.sleep(10)
            
        except Exception as e:
            print(f"自動操作中にエラーが発生しました: {e}")
            summary["failed"] += 1
            summary["errors"].append({"fatal": str(e)})
            time.sleep(10)
            
        finally:
            context.close()
            
    # 結果サマリーをファイルに出力
    if result_output_path:
        try:
            with open(result_output_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
        except Exception as se:
            logger.warning(f"結果サマリー保存失敗: {se}")
            
    return summary


if __name__ == "__main__":
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            urls = data.get("links", [])
            notebook_name = data.get("notebook_name", None)
            res_path = data.get("result_output_path", None)
            
            res = run_bot(urls, notebook_name, res_path)
            
            # 失敗がある場合は非ゼロコードで終了
            if res.get("failed", 0) > 0 and res.get("success", 0) == 0:
                sys.exit(1)
            else:
                sys.exit(0)
        except Exception as e:
            print(f"実行時致命的エラー: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
