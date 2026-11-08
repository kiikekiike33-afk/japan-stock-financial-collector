import time
import os
from playwright.sync_api import sync_playwright

def run_debug():
    profile_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "notebooklm_profile"))
    import subprocess
    try:
        cmd = 'wmic process where "name=\'chrome.exe\' and commandline like \'%notebooklm_profile%\'" call terminate'
        subprocess.run(cmd, shell=True, capture_output=True)
        time.sleep(2)
    except:
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
        page.goto("https://notebooklm.google.com/")
        
        found = None
        for _ in range(20):
            for sel in ['button[aria-label="ノートブックを新規作成"]', 'text="新しいノートブック"', 'text="New notebook"', 'text="新規作成"']:
                if page.locator(sel).count() > 0:
                    found = sel
                    break
            if found: break
            time.sleep(1)
            
        if found:
            page.locator(found).first.click()
            time.sleep(3)
            
            clicked_drive = False
            for s in ["Google ドライブ", "Google Drive", "ドライブ"]:
                loc = page.locator(f'text="{s}"')
                if loc.count() > 0:
                    loc.first.click()
                    clicked_drive = True
                    break
                    
            if clicked_drive:
                time.sleep(5)
                try:
                    frame_element = page.wait_for_selector('iframe[src*="docs.google.com/picker"]', timeout=30000)
                    frame = frame_element.content_frame()
                    print("Picker opened.")
                    time.sleep(5)
                    
                    list_view_btn = frame.locator('[aria-label="リスト表示"], [aria-label="List view"]').first
                    if list_view_btn.count() > 0:
                        list_view_btn.click()
                        time.sleep(2)
                    
                    first_real = frame.locator('div[role="row"]:has(svg), div[role="gridcell"]:has(svg), div[role="option"]:has(svg), div[role="row"] img').first
                    if first_real.count() > 0:
                        first_real.click(force=True)
                        page.keyboard.press("Home")
                        page.keyboard.down("Shift")
                        for _ in range(5):
                            page.keyboard.press("ArrowDown")
                            time.sleep(0.1)
                        page.keyboard.up("Shift")
                        print("Selected 6 files. Now checking buttons...")
                        
                        all_btns = frame.locator('*:has-text("挿入"), *:has-text("Insert"), *:has-text("選択"), *:has-text("Select")')
                        print(f"Total matching elements: {all_btns.count()}")
                        
                        # Find potential buttons by tag or role
                        real_buttons = frame.locator('button, div[role="button"]')
                        c = real_buttons.count()
                        print(f"Total real buttons in frame: {c}")
                        for i in range(c):
                            try:
                                text = real_buttons.nth(i).inner_text()
                                if text and len(text.strip()) > 0:
                                    print(f"Button {i} text: '{text.strip()}' HTML: {real_buttons.nth(i).evaluate('el => el.outerHTML[:150]')}")
                            except:
                                pass
                                
                    else:
                        print("No files to select.")
                except Exception as e:
                    print(f"Error: {e}")
        
        time.sleep(2)
        context.close()

if __name__ == "__main__":
    run_debug()
