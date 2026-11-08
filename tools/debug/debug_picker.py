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
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://notebooklm.google.com/")
        
        print("Waiting for New Notebook...")
        new_notebook_selectors = ['button[aria-label="ノートブックを新規作成"]', 'text="新しいノートブック"', 'text="New notebook"', 'text="新規作成"']
        found = None
        for _ in range(20):
            for sel in new_notebook_selectors:
                if page.locator(sel).count() > 0:
                    found = sel
                    break
            if found: break
            time.sleep(1)
            
        if not found:
            print("Could not find New Notebook button.")
            context.close()
            return
            
        page.locator(found).first.click()
        print("Clicked New Notebook.")
        time.sleep(3)
        
        # Click Google Drive
        drive_selectors = ["Google ドライブ", "Google Drive", "ドライブ"]
        clicked_drive = False
        for s in drive_selectors:
            loc = page.locator(f'text="{s}"')
            if loc.count() > 0:
                loc.first.click()
                clicked_drive = True
                break
                
        if not clicked_drive:
            print("Could not click Google Drive.")
            context.close()
            return
            
        print("Waiting for iframe...")
        time.sleep(5)
        
        try:
            frame_element = page.wait_for_selector('iframe[src*="docs.google.com/picker"]', timeout=30000)
            frame = frame_element.content_frame()
            print("Picker opened. Taking screenshot 1...")
            page.screenshot(path="picker1.png")
            
            print("Waiting for files to load in picker...")
            time.sleep(5)
            
            list_view_btn = frame.locator('[aria-label="リスト表示"], [aria-label="List view"]').first
            if list_view_btn.count() > 0:
                list_view_btn.click()
                print("Switched to List View.")
                time.sleep(2)
                
            page.screenshot(path="picker2.png")
            
            first_real_file = frame.locator('div[role="row"]:has(svg), div[role="gridcell"]:has(svg), div[role="option"]:has(svg), div[role="row"] img').first
            if first_real_file.count() > 0:
                first_real_file.click(force=True)
                print("Clicked first file.")
                time.sleep(1)
                
                page.keyboard.press("Home")
                time.sleep(1)
                
                page.keyboard.down("Shift")
                for _ in range(5):
                    page.keyboard.press("ArrowDown")
                    time.sleep(0.1)
                page.keyboard.up("Shift")
                print("Selected 6 files.")
                
                page.screenshot(path="picker3.png")
                
                select_btn = frame.locator('button:has-text("選択"), button:has-text("Select"), div[role="button"]:has-text("選択")')
                print(f"Select button count: {select_btn.count()}")
                for i in range(select_btn.count()):
                    print(f"Btn {i}: {select_btn.nth(i).evaluate('el => el.outerHTML')}")
                
                # Print all buttons with text containing "選択" or "Select"
                all_btns = frame.locator('*:has-text("選択"), *:has-text("Select")')
                print(f"Elements with '選択' count: {all_btns.count()}")
                # Just get the last 5 elements
                for i in range(max(0, all_btns.count() - 5), all_btns.count()):
                    print(f"Elem {i}: {all_btns.nth(i).evaluate('el => el.tagName + ` ` + el.className + ` ` + el.innerText')}")
                
            else:
                print("No files found in root.")
                
        except Exception as e:
            print(f"Error: {e}")
            
        time.sleep(2)
        context.close()

if __name__ == "__main__":
    run_debug()
