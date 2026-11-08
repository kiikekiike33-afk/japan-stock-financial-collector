import os
import time
from playwright.sync_api import sync_playwright

def inspect_notebooklm():
    profile_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "notebooklm_profile"))
    
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=True,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://notebooklm.google.com/")
        time.sleep(10) # wait for load
        
        with open("notebooklm_dump.html", "w", encoding="utf-8") as f:
            f.write(page.content())
            
        print("HTML dumped to notebooklm_dump.html")
        context.close()

if __name__ == "__main__":
    inspect_notebooklm()
