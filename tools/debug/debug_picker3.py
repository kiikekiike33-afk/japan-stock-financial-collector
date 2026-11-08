import time
import os
from playwright.sync_api import sync_playwright

def run_debug():
    profile_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "notebooklm_profile"))
    
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
                        print("Selected 1 file. Now finding the 挿入 button...")
                        
                        time.sleep(2)
                        
                        # Find all elements that contain exactly "挿入" in their text, but have no children containing it
                        leaf_nodes = frame.evaluate('''() => {
                            const results = [];
                            const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT, null, false);
                            let node;
                            while (node = walk.nextNode()) {
                                if (node.innerText && node.innerText.includes("挿入")) {
                                    // check if it's a leaf containing the text (or only text node children)
                                    if (node.children.length === 0 || Array.from(node.children).every(c => !c.innerText || !c.innerText.includes("挿入"))) {
                                        results.push({
                                            tag: node.tagName,
                                            role: node.getAttribute("role"),
                                            classes: node.className,
                                            html: node.outerHTML
                                        });
                                    }
                                }
                            }
                            return results;
                        }''')
                        
                        print(f"Found {len(leaf_nodes)} leaf nodes with text 挿入:")
                        for idx, node in enumerate(leaf_nodes):
                            print(f"Node {idx}: TAG={node['tag']} ROLE={node['role']} CLASS={node['classes']}")
                            print(f"HTML: {node['html']}")
                            print("-" * 50)
                            
                except Exception as e:
                    print(f"Error: {e}")
        
        time.sleep(2)
        context.close()

if __name__ == "__main__":
    run_debug()
