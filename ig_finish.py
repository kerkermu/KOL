import os
import json
import time
import random
import logging
import pymysql
import re
from playwright.sync_api import sync_playwright
from datetime import datetime
from tqdm import tqdm

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler('instagram_scraper.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# 配置參數
USERNAMES = ["iamteresa0424", "solo_guide"]
MAX_REELS = 20
TIMEOUT = 30000

def get_random_user_agent():
    """生成隨機用戶代理"""
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ]
    return random.choice(user_agents)

def add_random_delay(min_delay=2, max_delay=4):
    """添加隨機延遲"""
    time.sleep(random.uniform(min_delay, max_delay))

def convert_views(views_text):
    """轉換觀看次數"""
    views_text = views_text.replace(',', '')
    match = re.search(r'(\d+(\.\d+)?)萬', views_text)
    if match:
        return int(float(match.group(1)) * 10000)
    elif views_text.isdigit():
        return int(views_text)
    return 0

def extract_likes_comments(text):
    """從 meta 標籤提取 likes 和 comments 數字，支持多種格式和異常處理"""
    # 多重正則表達式模式
    patterns = [
        r'(\d+(?:,\d+)?(?:K)?)\s*likes,\s*(\d+(?:,\d+)?)\s*comments',
        r'(\d+(?:,\d+)?(?:K)?)\s*like,\s*(\d+(?:,\d+)?)\s*comment',
        r'(\d+(?:\.\d+)?[Kk])\s*likes,\s*(\d+)\s*comments',
        r'(\d+(?:,\d+)?)\s*個讚,\s*(\d+)\s*則留言'
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # 處理讚數
            likes_str = match.group(1).replace(',', '')
            if 'K' in likes_str.upper():
                likes = int(float(likes_str.replace('K', '').replace('k', '')) * 1000)
            else:
                likes = int(likes_str)

            # 處理留言數
            comments_str = match.group(2).replace(',', '')
            comments = int(comments_str)

            return likes, comments

    # 如果所有模式都失敗，嘗試更寬鬆的匹配
    flexible_match = re.search(r'(\d+(?:\.\d+)?[Kk]?)\s*(?:likes?|個讚),\s*(\d+)\s*(?:comments?|則留言)', text, re.IGNORECASE)
    if flexible_match:
        likes_str = flexible_match.group(1).replace(',', '')
        if 'K' in likes_str.upper():
            likes = int(float(likes_str.replace('K', '').replace('k', '')) * 1000)
        else:
            likes = int(likes_str)

        comments_str = flexible_match.group(2).replace(',', '')
        comments = int(comments_str)

        return likes, comments

    # 如果仍然找不到，返回預設值
    return 0, 0

def get_reels_likes_comments(page, reels_url):
    """從特定 Reels URL 提取讚數和留言數"""
    if reels_url == "N/A":
        return {"likes": 0, "comments": 0, "url": reels_url}

    try:
        # 導航到 Reels 頁面
        page.goto(reels_url, timeout=TIMEOUT)
        page.wait_for_load_state("networkidle", timeout=TIMEOUT)
        add_random_delay()

        # 嘗試從 meta 標籤提取
        meta_elements = [
            page.query_selector('meta[property="og:description"]'),
            page.query_selector('meta[name="description"]')
        ]
        
        for meta_element in meta_elements:
            if meta_element:
                meta_content = meta_element.get_attribute("content")
                likes, comments = extract_likes_comments(meta_content)
                if likes > 0 or comments > 0:
                    return {"likes": likes, "comments": comments, "url": reels_url}

        # 如果 meta 標籤無法提取，則嘗試網頁上的元素
        likes, comments = 0, 0

        # 嘗試從頁面元素提取讚數
        likes_selectors = [
            'a[href$="/liked_by/"] span span',
            'div[role="button"] span:has-text("讚")',
            'div[role="button"] span:has-text("likes")'
        ]
        
        for selector in likes_selectors:
            likes_element = page.query_selector(selector)
            if likes_element:
                likes_text = likes_element.inner_text().replace('個讚', '').replace('likes', '').replace(',', '')
                if likes_text.isdigit():
                    likes = int(likes_text)
                    break

        # 嘗試從頁面元素提取留言數
        comments_selectors = [
            'div[role="button"] span:has-text("留言")',
            'div[role="button"] span:has-text("comments")'
        ]
        
        for selector in comments_selectors:
            comments_elements = page.query_selector_all(selector)
            for elem in comments_elements:
                comments_text = elem.inner_text()
                if '則留言' in comments_text or 'comments' in comments_text:
                    comments_text = comments_text.replace('則留言', '').replace('comments', '').replace(',', '')
                    try:
                        comments = int(comments_text)
                        break
                    except ValueError:
                        pass

        return {"likes": likes, "comments": comments, "url": reels_url}
    
    except Exception as e:
        logging.error(f"Error extracting data from {reels_url}: {e}")
        return {"likes": 0, "comments": 0, "url": reels_url}

def connect_db(host, user, password, database):
    return pymysql.connect(host=host, user=user, password=password, database=database, charset="utf8mb4")

def normalize_number(value):
    """統一化數字格式"""
    if isinstance(value, (int, float)):
        return int(value)
    if not value:
        return 0

    value = str(value).replace(',', '').replace('K', '000').replace('M', '000000')
    try:
        return int(float(value))
    except ValueError:
        return 0

def save_to_db(db, username, profile_data, reels_data):
    cursor = db.cursor()

    # 存入用戶資訊
    cursor.execute("""
        INSERT INTO instagram_users (username, user_name, posts_count, followers_count)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE 
        user_name = VALUES(user_name),
        posts_count = VALUES(posts_count),
        followers_count = VALUES(followers_count)
    """, (username, profile_data["user_name"], normalize_number(profile_data["posts_count"]), normalize_number(profile_data["followers_count"])))

    # 取得 user_id
    cursor.execute("SELECT id FROM instagram_users WHERE username = %s", (username,))
    user_id = cursor.fetchone()[0]

    # 刪除舊的 Reels 資訊
    cursor.execute("DELETE FROM instagram_reels WHERE user_id = %s", (user_id,))

    # 存入新的 Reels 資訊
    for reel in reels_data:
        views = normalize_number(reel["views"])
        likes = normalize_number(reel["likes"])
        comments = normalize_number(reel["comments"])

        cursor.execute("""
            INSERT INTO instagram_reels (user_id, reel_index, views, likes, comments, url)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (user_id, reel["reel_index"], views, likes, comments, reel["link"]))

    db.commit()
    cursor.close()

def get_instagram_data(username):
    """爬取 Instagram 用戶的 Reels 資訊"""
    with sync_playwright() as p:
        try:
            # 配置瀏覽器選項
            browser_params = {
                "headless": True,
                "args": [
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-extensions',
                    '--disable-gpu',
                    '--disable-dev-shm-usage'
                ]
            }
            
            browser = p.chromium.launch(**browser_params)
            context = browser.new_context(
                storage_state="ig_login_state.json",
                viewport={'width': 1920, 'height': 1080},
                user_agent=get_random_user_agent(),
                java_script_enabled=True,
                locale='zh-TW',
                timezone_id='Asia/Taipei'
            )
            
            # 設置額外的 HTTP 標頭
            context.set_extra_http_headers({
                'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
                'Accept': 'text/html,application/xhtml+xml,application/xml',
                'Accept-Encoding': 'gzip, deflate, br'
            })

            page = context.new_page()
            page.set_default_timeout(TIMEOUT)

            # 導航到用戶主頁
            profile_url = f"https://www.instagram.com/{username}/"
            page.goto(profile_url)
            page.wait_for_selector("header", timeout=TIMEOUT)
            add_random_delay()
            
            # 提取用戶基本資訊
            user_name = page.query_selector('header section h2').inner_text()
            posts = page.query_selector_all('header section ul li')[0].query_selector('span').inner_text()
            followers = page.query_selector_all('header section ul li')[1].query_selector('span').inner_text()
            
            # 導航到 Reels 頁面
            reels_url = f"https://www.instagram.com/{username}/reels/"
            page.goto(reels_url)
            page.wait_for_selector("main", timeout=TIMEOUT)
            add_random_delay()

            # 收集 Reels 資訊
            reels_data = []
            seen_urls = set()

            # 捲動並收集 Reels
            with tqdm(total=MAX_REELS, desc=f"Scraping reels for {username}") as pbar:
                while len(reels_data) < MAX_REELS:
                    svg_icons = page.query_selector_all("svg[aria-label='觀看次數圖示']")
                    
                    for svg in svg_icons:
                        if len(reels_data) >= MAX_REELS:
                            break
                        
                        try:
                            # 找到 Reels 連結
                            reel_link_element = svg.evaluate_handle("(el) => el.closest('a')")
                            reel_link = reel_link_element.get_attribute("href")
                            reel_url = f"https://www.instagram.com{reel_link}" if reel_link else "N/A"
                            
                            if reel_url in seen_urls:
                                continue
                            seen_urls.add(reel_url)

                            # 找到觀看次數
                            view_container = svg.evaluate_handle("(el) => el.closest('div').parentElement")
                            spans = view_container.query_selector_all("span")
                            
                            for span in spans:
                                views_text = span.inner_text().strip()
                                views = convert_views(views_text)
                                
                                if views > 0:
                                    reel_data = {
                                        "reel_index": len(reels_data) + 1, 
                                        "views": views, 
                                        "link": reel_url
                                    }
                                    reels_data.append(reel_data)
                                    pbar.update(1)
                                    break

                        except Exception as e:
                            logging.error(f"Error processing reel: {e}")
                            continue

                    # 捲動頁面
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    add_random_delay()
                    
                    # 如果無法找到更多 Reels，則停止
                    if len(page.query_selector_all("svg[aria-label='觀看次數圖示']")) <= len(seen_urls):
                        break

            browser.close()

            return {
                "username": username,
                "user_name": user_name,
                "posts_count": posts,
                "followers_count": followers,
                "reels_data": reels_data
            }

        except Exception as e:
            logging.error(f"Error scraping {username}: {e}")
            return None

def main():
    """主程式"""
    all_data = []
    
    # 第一階段：收集基本 Reels 資訊
    for user in USERNAMES:
        user_data = get_instagram_data(user)
        if user_data:
            all_data.append(user_data)

    # 連接本地 & Google Cloud VM 的 MariaDB
    local_db = connect_db("10.167.214.50", "hank", "1234", "instagram_data")
    cloud_db = connect_db("34.30.153.56", "hank", "1234", "instagram_data")

    # 第二階段：補充 Reels 詳細資訊（讚數、留言數）
    with sync_playwright() as p:
        browser_params = {
            "headless": True,
            "args": [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-extensions',
                '--disable-gpu',
                '--disable-dev-shm-usage'
            ]
        }
        
        browser = p.chromium.launch(**browser_params)
        context = browser.new_context(
            storage_state="ig_login_state.json",
            viewport={'width': 1920, 'height': 1080},
            user_agent=get_random_user_agent(),
            java_script_enabled=True,
            locale='zh-TW',
            timezone_id='Asia/Taipei'
        )
        
        page = context.new_page()
        page.set_default_timeout(TIMEOUT)

        try:
            for user_data in tqdm(all_data, desc="Fetching detailed Reels data"):
                for reel in tqdm(user_data['reels_data'], desc=f"Processing reels for {user_data['username']}", leave=False):
                    if 'likes' in reel and 'comments' in reel:
                        continue

                    reel_details = get_reels_likes_comments(page, reel['link'])
                    reel.update({
                        'likes': reel_details['likes'],
                        'comments': reel_details['comments']
                    })

                # 存入本地和 Google Cloud VM 的 MariaDB
                save_to_db(local_db, user_data['username'], user_data, user_data['reels_data'])
                save_to_db(cloud_db, user_data['username'], user_data, user_data['reels_data'])

        except Exception as e:
            logging.error(f"Error during detailed Reels data extraction: {e}")
        
        finally:
            browser.close()

    # 建立 output 目錄
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
    os.makedirs(output_dir, exist_ok=True)

    # 生成並儲存 JSON 檔案
    date_str = datetime.now().strftime("%Y%m%d")
    filename = os.path.join(output_dir, f"ig_data_{date_str}.json")

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=4, ensure_ascii=False)

    logging.info(f"JSON data saved as {filename}")

    # 關閉資料庫連線
    local_db.close()
    cloud_db.close()

if __name__ == "__main__":
    main()