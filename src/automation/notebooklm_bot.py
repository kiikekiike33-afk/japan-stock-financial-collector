import sys
import time
from playwright.sync_api import sync_playwright
import os
import io
import re

# Windowsコンソールでの文字化け・エンコードエラー対策 (cp932エラー回避)
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def js_click(page, text_candidates):
    for text in text_candidates:
        result = page.evaluate(f"""
            (() => {{
                const elements = document.querySelectorAll('button, a, div[role="button"], div[role="menuitem"], li[role="menuitem"], span[role="button"], mat-list-item');
                for (const el of elements) {{
                    const t = el.innerText ? el.innerText.trim() : '';
                    if (t.includes('{text}') && el.offsetParent !== null && !el.disabled) {{
                        el.click();
                        return true;
                    }}
                }}
                return false;
            }})()
        """)
        if result:
            return True
    return False


def run_bot(urls, notebook_name=None):
    profile_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "notebooklm_profile"))
    
    import subprocess
    try:
        cmd = 'wmic process where "name=\'chrome.exe\' and commandline like \'%notebooklm_profile%\'" call terminate'
        subprocess.run(cmd, shell=True, capture_output=True)
        time.sleep(2)
    except Exception as e:
        pass
        
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=False,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
            no_viewport=True
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        
        print(f"合計 {len(urls)} 件のリンクを、「Googleドライブから選択」方式で1件ずつ追加します。")
        
        try:
            # === ノートブックの作成 ===
            page.goto("https://notebooklm.google.com/")
            print("NotebookLMを開きました。Googleログインが必要な場合は手動でログインしてください。")
            
            new_notebook_selectors = [
                'button[aria-label="ノートブックを新規作成"]',
                'div[aria-label="ノートブックを新規作成"]',
                'text="新規作成"',
                'text="新しいノートブック"'
            ]
            
            found_selector = None
            for _ in range(60):
                for sel in new_notebook_selectors:
                    if page.locator(sel).count() > 0:
                        found_selector = sel
                        break
                if found_selector:
                    break
                time.sleep(1)
                
            if not found_selector:
                print("タイムアウト: 「新しいノートブック」ボタンが見つかりませんでした。")
                context.close()
                return
                
            page.locator(found_selector).first.click()
            print("新規ノートブックを作成しました。")
            time.sleep(5)
            
            # ソース追加モーダルを一旦閉じる
            page.keyboard.press("Escape")
            time.sleep(1)
            page.keyboard.press("Escape")
            time.sleep(2)
            
            # タイトル変更
            if notebook_name:
                print(f"ノートブックの名前を「{notebook_name}」に変更します...")
                clicked_more = page.evaluate("""
                    (() => {
                        const buttons = document.querySelectorAll('button');
                        for (const btn of buttons) {
                            if (btn.innerText && btn.innerText.trim().includes('more_vert')) {
                                btn.click();
                                return true;
                            }
                        }
                        return false;
                    })()
                """)
                if clicked_more:
                    time.sleep(1.5)
                    clicked_customize = js_click(page, ["ノートブックのカスタマイズ", "Customize notebook", "カスタマイズ", "Customize"])
                    if clicked_customize:
                        time.sleep(2)
                        title_selectors = ['input[aria-label="ノートブックのタイトル"]', 'input[aria-label="Notebook title"]', 'dialog input[type="text"]', '[role="dialog"] input[type="text"]', 'input[type="text"]']
                        for t_sel in title_selectors:
                            if page.locator(t_sel).count() > 0:
                                name_input = page.locator(t_sel).first
                                name_input.click(click_count=3)
                                time.sleep(0.5)
                                page.keyboard.type(notebook_name)
                                time.sleep(0.5)
                                page.keyboard.press("Enter")
                                time.sleep(0.5)
                                break
                        
                        js_click(page, ["保存", "完了", "Save", "Done"])
                        time.sleep(1)
                        page.keyboard.press("Escape")
                        time.sleep(1)
                        page.keyboard.press("Escape")
                        time.sleep(1)
                        print("タイトルを保存しました。")
            
            # === Googleドライブ(Picker)ベースで1つずつソースを追加する ===
            print(f"\n--- Google Drive Picker方式（1件ずつ）で処理を開始します ---")
            
            for idx, url in enumerate(urls):
                print(f"\n[{idx + 1}/{len(urls)}] ファイルをGoogleドライブから検索して追加します...")
                
                # 1. 「ソースを追加」ボタンが押せるようになるまで待つ
                wait_start = time.time()
                is_ready = False
                while time.time() - wait_start < 600:
                    try:
                        ready = page.evaluate('''() => {
                            const btns = document.querySelectorAll('button');
                            for (const b of btns) {
                                if ((b.innerText && b.innerText.includes("ソースを追加")) || 
                                    (b.getAttribute('aria-label') && b.getAttribute('aria-label').includes("ソースを追加"))) {
                                    if (b.offsetParent !== null && !b.disabled) return true;
                                }
                            }
                            return false;
                        }''')
                        if ready:
                            is_ready = True
                            break
                    except: pass
                    time.sleep(1)
                
                time.sleep(1)
                
                # 2. 「ソースを追加」メニューを開く
                js_click(page, ["ソースを追加", "新しいソース", "Add source", "+"])
                time.sleep(1.5)
                
                # 3. 「Google ドライブ」ボタンをクリック
                clicked_drive = js_click(page, ["Google ドライブ", "Google Drive", "ドライブ", "Drive"])
                if not clicked_drive:
                    print(f"[{idx + 1}/{len(urls)}] 警告: Google ドライブボタンが見つかりません。")
                    page.keyboard.press("Escape")
                    time.sleep(1)
                    continue
                    
                time.sleep(3) # Google Picker iframe が開くまで待機
                
                # 4. Picker iframe を取得
                # Google Pickerは通常 iframe で表示される
                try:
                    picker_frame = page.frame_locator('iframe[src*="docs.google.com/picker"], iframe.picker-frame').last
                    
                    # 検索ボックスを探す
                    search_input = picker_frame.locator('input[type="text"], input[aria-label*="検索"], input[aria-label*="Search"]').first
                    search_input.wait_for(state="visible", timeout=10000)
                    
                    search_input.click(force=True)
                    time.sleep(0.5)
                    # ファイルIDだけだとヒットしない可能性があるので、URL自体またはファイルIDを入れる
                    # 今回は検索精度を高めるため URL 自体を入力する
                    search_input.fill(url)
                    time.sleep(0.5)
                    page.keyboard.press("Enter")
                    time.sleep(3) # 検索結果が出るまで待機
                    
                    # 5. 検索結果の一番上をクリックして選択
                    body = picker_frame.locator('body')
                    item_selected = body.evaluate('''() => {
                        const items = document.querySelectorAll('[role="row"], [role="option"], .picker-list-item, [role="button"]');
                        for (const item of items) {
                            // "リスト内のアイテム"的な要素で可視のものを探す
                            if (item.offsetParent !== null && item.innerText && item.getAttribute('role') !== 'button') {
                                item.click();
                                return true;
                            }
                            // Roleがbuttonでも、aria-labelに拡張子(PDFなど)が含まれていればファイル
                            if (item.offsetParent !== null && item.getAttribute('aria-label') && item.getAttribute('aria-label').toLowerCase().includes('.pdf')) {
                                item.click();
                                return true;
                            }
                        }
                        
                        // 念のため全部舐める
                        for (const item of items) {
                            if (item.offsetParent !== null && item.innerText) {
                                item.click();
                                return true;
                            }
                        }
                        return false;
                    }''')
                    
                    if not item_selected:
                        print(f"[{idx + 1}/{len(urls)}] 警告: 検索結果のアイテムが見つかりませんでした。")
                    
                    time.sleep(1.5)
                    
                    # 6. 「選択」または「挿入」ボタンをクリック（青い確定ボタン）
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
                        
                        // テキストで見つからなければ、Pickerの青いプライマリアクションボタンを探す
                        const actionBtns = document.querySelectorAll('div.jfk-button-action[role="button"]');
                        for (const btn of actionBtns) {
                            if (btn.offsetParent !== null && btn.getAttribute('aria-disabled') !== 'true') {
                                btn.click();
                                return true;
                            }
                        }
                        return false;
                    }''')
                    
                    if not inserted:
                        print(f"[{idx + 1}/{len(urls)}] 挿入ボタンが見つからないため、Enterキーでフォールバックします。")
                        page.keyboard.press("Enter")
                        
                    time.sleep(2)
                    
                    # 7. 解析完了を待機
                    print(f"[{idx + 1}/{len(urls)}] ドライブから追加中... 解析完了を待ちます。")
                    load_start = time.time()
                    while time.time() - load_start < 120:
                        is_loading = page.evaluate('''() => {
                            const indicators = document.querySelectorAll('mat-spinner, [role="progressbar"], .loading-spinner');
                            for (const ind of indicators) {
                                if (ind.offsetParent !== null) return true;
                            }
                            const texts = document.querySelectorAll('*');
                            for (const t of texts) {
                                if (t.innerText === "読み込み中" || t.innerText === "Loading") return true;
                            }
                            return false;
                        }''')
                        if not is_loading:
                            break
                        time.sleep(1)
                        
                except Exception as e:
                    print(f"[{idx + 1}/{len(urls)}] Picker操作中にエラーが発生しました: {e}")
                    page.keyboard.press("Escape")
                    
                time.sleep(2)
                
            print("\nすべてのファイルの転送処理が完了しました！10分間ブラウザを維持します。")
            time.sleep(600)
            
        except Exception as e:
            print(f"自動操作中にエラーが発生しました: {e}")
            time.sleep(600)
            
        finally:
            context.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        import json
        file_path = sys.argv[1]
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            urls = data.get("links", [])
            notebook_name = data.get("notebook_name", None)
            run_bot(urls, notebook_name)
        except Exception as e:
            pass
