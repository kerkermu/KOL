from playwright.sync_api import sync_playwright

def save_login_state():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # 瀏覽器保持開啟
        context = browser.new_context()
        page = context.new_page()

        # 打開 Instagram 登入頁面
        page.goto("https://www.instagram.com/accounts/login/")
        print("請手動登入 Instagram...")
        page.wait_for_timeout(30000)  # 等待 30 秒完成登入

        # 保存登入狀態
        context.storage_state(path="ig_login_state.json")
        print("登入狀態已保存到 'ig_login_state.json'")

        # 關閉瀏覽器
        browser.close()

save_login_state()
