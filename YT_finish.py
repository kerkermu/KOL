import os
import json
import datetime
import pymysql
from googleapiclient.discovery import build

# ✅ 設定 API Key 和頻道 ID
API_KEY = "AIzaSyAVA7btRMalrJpBwjYS9Vw2moKjxwZPGg0"
CHANNELS = {
    "大食女": "UC9qUmuXg4KhTeakpPBJfL_w",
    "SOLO的玩樂指南": "UCOKniUyjQS82nbTsGxNJR-Q"
}

youtube = build("youtube", "v3", developerKey=API_KEY)

# ✅ 取得頻道的基本資訊
def get_channel_stats(channel_id):
    request = youtube.channels().list(
        part="statistics",
        id=channel_id
    )
    response = request.execute()

    if "items" in response and len(response["items"]) > 0:
        stats = response["items"][0]["statistics"]
        return {
            "訂閱數": stats.get("subscriberCount", "N/A"),
            "總影片數": stats.get("videoCount", "N/A"),
            "總觀看數": stats.get("viewCount", "N/A")
        }
    else:
        return None

# ✅ 取得最新 N 部影片的 ID
def get_latest_video_ids(channel_id, max_results=20):
    video_ids = []
    request = youtube.search().list(
        part="id",
        channelId=channel_id,
        maxResults=max_results,
        order="date",
        type="video"
    )
    response = request.execute()

    for item in response["items"]:
        video_ids.append(item["id"]["videoId"])

    return video_ids

# ✅ 取得影片的觀看數、按讚數、留言數
def get_video_stats(video_ids):
    video_data = []
    request = youtube.videos().list(
        part="statistics",
        id=",".join(video_ids)
    )
    response = request.execute()

    for item in response["items"]:
        video_id = item["id"]
        stats = item["statistics"]
        video_data.append({
            "影片 ID": video_id,
            "觀看數": stats.get("viewCount", "N/A"),
            "按讚數": stats.get("likeCount", "N/A"),
            "留言數": stats.get("commentCount", "N/A")
        })

    return video_data

# ✅ 連接資料庫
def connect_db(host, user, password, database):
    return pymysql.connect(host=host, user=user, password=password, database=database, charset="utf8mb4")

# ✅ 存入資料庫
def save_to_db(db, channel_name, channel_stats, video_stats):
    cursor = db.cursor()

    # 存入頻道資訊
    cursor.execute("""
        INSERT INTO channels (name, subscribers, total_videos, total_views)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE 
        subscribers = VALUES(subscribers),
        total_videos = VALUES(total_videos),
        total_views = VALUES(total_views)
    """, (channel_name, int(channel_stats["訂閱數"]), int(channel_stats["總影片數"]), int(channel_stats["總觀看數"])))

    # 取得 channel_id
    cursor.execute("SELECT id FROM channels WHERE name = %s", (channel_name,))
    channel_id = cursor.fetchone()[0]

    # 刪除舊的影片資訊
    cursor.execute("DELETE FROM videos WHERE channel_id = %s", (channel_id,))

    # 存入新的影片資訊
    for video in video_stats:
        views = int(video["觀看數"]) if video["觀看數"] != "N/A" else None
        likes = int(video["按讚數"]) if video["按讚數"] != "N/A" else None
        comments = int(video["留言數"]) if video["留言數"] != "N/A" else None

        cursor.execute("""
            INSERT INTO videos (channel_id, video_id, views, likes, comments)
            VALUES (%s, %s, %s, %s, %s)
        """, (channel_id, video["影片 ID"], views, likes, comments))

    db.commit()
    cursor.close()

if __name__ == "__main__":
    # 🚀 執行程序
    all_channel_data = {}
    current_date = datetime.datetime.now().strftime("%Y%m%d")
    
    # 建立 output 目錄
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
    os.makedirs(output_dir, exist_ok=True)
    
    json_filename = os.path.join(output_dir, f"youtube_data_{current_date}.json")

    # 連接本地 & Google Cloud VM 的 MariaDB
    local_db = connect_db("10.167.214.50", "hank", "1234", "youtube_data")
    cloud_db = connect_db("34.30.153.56", "hank", "1234", "youtube_data")

    try:
        for name, channel_id in CHANNELS.items():
            print(f"📢 正在處理 {name} 的頻道數據...")

            channel_stats = get_channel_stats(channel_id)
            video_ids = get_latest_video_ids(channel_id, max_results=20)
            video_stats = get_video_stats(video_ids)

            all_channel_data[name] = {
                "頻道資訊": channel_stats,
                "最新影片統計": video_stats
            }

            # 存入本地和 Google Cloud VM 的 MariaDB
            save_to_db(local_db, name, channel_stats, video_stats)
            save_to_db(cloud_db, name, channel_stats, video_stats)

        # ✅ 存成 JSON
        with open(json_filename, "w", encoding="utf-8") as json_file:
            json.dump(all_channel_data, json_file, ensure_ascii=False, indent=4)

        print(f"✅ 所有頻道數據已存成 {json_filename}")
        print("✅ 數據已存入本地和 Google Cloud VM 的 MariaDB！")

    finally:
        # 關閉資料庫連線
        local_db.close()
        cloud_db.close()
