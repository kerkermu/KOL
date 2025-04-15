import os
import json
import time
from datetime import datetime
import pymysql
from playwright.sync_api import sync_playwright

class TikTokScraper:
    def __init__(self):
        self.users = ["joyaijia", "solo_guide"]
    
    def connect_db(self, host, user, password, database):
        return pymysql.connect(host=host, user=user, password=password, database=database, charset="utf8mb4")
    
    def normalize_number(self, value):
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

    def save_to_db(self, db, username, profile_data, video_data):
        cursor = db.cursor()

        # 存入用戶資訊
        cursor.execute("""
            INSERT INTO tiktok_users (username, likes, followers)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE 
            likes = VALUES(likes),
            followers = VALUES(followers)
        """, (username, self.normalize_number(profile_data["likes"]), self.normalize_number(profile_data["followers"])))

        # 取得 user_id
        cursor.execute("SELECT id FROM tiktok_users WHERE username = %s", (username,))
        user_id = cursor.fetchone()[0]

        # 刪除舊的影片資訊
        cursor.execute("DELETE FROM tiktok_videos WHERE user_id = %s", (user_id,))

        # 存入新的影片資訊
        for video in video_data:
            views = self.normalize_number(video["views"])
            likes = self.normalize_number(video["likes"])
            comments = self.normalize_number(video["comments"])
            saves = self.normalize_number(video["saves"])
            shares = self.normalize_number(video["shares"])

            cursor.execute("""
                INSERT INTO tiktok_videos (user_id, video_number, views, likes, comments, saves, shares, url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (user_id, video["video_number"], views, likes, comments, saves, shares, video["url"]))

        db.commit()
        cursor.close()

    def scrape_profile(self, username, context):
        try:
            page = context.new_page()
            url = f"https://www.tiktok.com/@{username}"
            page.goto(url)
            page.wait_for_load_state('networkidle')
            time.sleep(8)
            
            profile_data = {
                'username': username,
                'likes': self._get_text(page, "strong[data-e2e='likes-count']"),
                'followers': self._get_text(page, "strong[data-e2e='followers-count']"),
            }
            
            print(f"正在爬取 {username} 的資料...")
            print(f"喜歡數: {profile_data['likes']}")
            print(f"追蹤人數: {profile_data['followers']}")
            
            videos = self.scrape_videos(page, context)
            page.close()
            
            return {'profile': profile_data, 'videos': videos}
            
        except Exception as e:
            print(f"爬取用戶 {username} 時發生錯誤: {str(e)}")
            return {'profile': {}, 'videos': []}

    def scrape_videos(self, page, context):
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(5)
            
            page.wait_for_selector("div[data-e2e='user-post-item']", timeout=30000)
            time.sleep(5)
            
            video_data = page.evaluate("""() => {
                return Array.from(document.querySelectorAll("div[data-e2e='user-post-item']"))
                .slice(0, 20).map((video, index) => ({
                    video_number: index + 1,
                    views: video.querySelector("strong[data-e2e='video-views']")?.innerText || 'N/A',
                    url: video.querySelector("a")?.href || ''
                }));
            }""")
            
            videos = []
            print(f"\n開始爬取影片資料...")
            
            for video in video_data:
                print(f"\n正在爬取第 {video['video_number']} 部影片:")
                print(f"觀看次數: {video['views']}")
                
                if video['url']:
                    video_info = self.scrape_video_details(video, context)
                    videos.append(video_info)
                    time.sleep(2)
                
            return videos
            
        except Exception as e:
            print(f"爬取影片列表時發生錯誤: {str(e)}")
            return []

    def scrape_video_details(self, video, context):
        try:
            video_page = context.new_page()
            video_page.goto(video['url'])
            video_page.wait_for_load_state('networkidle')
            time.sleep(8)
            
            stats = video_page.evaluate("""() => {
                const getStat = (selectors) => selectors.map(s => document.querySelector(s)?.innerText).find(v => v) || 'N/A';
                return {
                    likes: getStat(['strong[data-e2e="like-count"]']),
                    comments: getStat(['strong[data-e2e="comment-count"]']),
                    saves: getStat(['strong[data-e2e="undefined-count"]']),
                    shares: getStat(['strong[data-e2e="share-count"]'])
                };
            }""")
            
            video_page.close()
            return {**video, **stats}
            
        except Exception as e:
            print(f"爬取視頻詳情時發生錯誤: {str(e)}")
            return {**video, 'likes': 'N/A', 'comments': 'N/A', 'saves': 'N/A', 'shares': 'N/A'}

    def _get_text(self, page, selector):
        try:
            element = page.wait_for_selector(selector, timeout=10000)
            return element.inner_text()
        except:
            return "N/A"

    def scrape_all_profiles(self):
        all_data = {}
        
        # 連接本地 & Google Cloud VM 的 MariaDB
        local_db = self.connect_db("10.167.214.50", "hank", "1234", "tiktok_data")
        cloud_db = self.connect_db("34.30.153.56", "hank", "1234", "tiktok_data")
        
        try:
            for username in self.users:
                print(f"\n{'='*50}")
                print(f"開始爬取用戶 {username} 的資料")
                print(f"{'='*50}\n")
                
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(
                        viewport={'width': 1920, 'height': 1080},
                        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    )
                    
                    try:
                        user_data = self.scrape_profile(username, context)
                        all_data[username] = user_data
                        print(f"\n完成爬取用戶 {username} 的資料")
                        
                        # 存入本地和 Google Cloud VM 的 MariaDB
                        self.save_to_db(local_db, username, user_data['profile'], user_data['videos'])
                        self.save_to_db(cloud_db, username, user_data['profile'], user_data['videos'])
                    
                    finally:
                        browser.close()
                
                time.sleep(10)
            
            # 確保 output 目錄存在
            output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
            os.makedirs(output_dir, exist_ok=True)
            
            # 使用當前日期作為檔案名
            timestamp = datetime.now().strftime("%Y%m%d")
            json_filename = f"tiktok_data_{timestamp}.json"
            json_path = os.path.join(output_dir, json_filename)
            
            # 保存 JSON 檔案
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(all_data, f, ensure_ascii=False, indent=2)
            print(f"\n所有數據已保存到 {json_path}")
            
        finally:
            # 關閉資料庫連線
            local_db.close()
            cloud_db.close()

if __name__ == "__main__":
    scraper = TikTokScraper()
    scraper.scrape_all_profiles()