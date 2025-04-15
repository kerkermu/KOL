import os
import sys
import json
from flask import Blueprint, jsonify, request

# 添加項目根目錄到 Python 路徑
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

from config.settings import PROCESSED_DATA_DIR

stats_bp = Blueprint('stats', __name__)

def normalize_number(value):
    """統一化數字格式"""
    if isinstance(value, (int, float)):
        return str(value)
    if not value:
        return "0"
    
    value = str(value).replace(',', '')
    multipliers = {'K': 1000, 'M': 1000000, '萬': 10000, '位粉絲': 1, '貼文': 1}
    
    for suffix, multiplier in multipliers.items():
        if suffix in value:
            try:
                number = float(value.replace(suffix, ''))
                return str(int(number * multiplier))
            except ValueError:
                return "0"
    
    return value.replace(',', '')

def normalize_data(raw_data, platform):
    """統一化不同平台的數據格式"""
    if platform == 'youtube':
        return {
            "basic_info": {
                "platform": "youtube",
                "followers_count": raw_data.get("頻道資訊", {}).get("訂閱數", "0"),
                "posts_count": raw_data.get("頻道資訊", {}).get("總影片數", "0"),
                "total_views": raw_data.get("頻道資訊", {}).get("總觀看數", "0")
            },
            "videos_data": [
                {
                    "views": video.get("觀看數", "0"),
                    "likes": video.get("按讚數", "0"),
                    "comments": video.get("留言數", "0")
                }
                for video in raw_data.get("最新影片統計", [])
            ]
        }
    elif platform == 'instagram':
        return {
            "basic_info": {
                "platform": "instagram",
                "followers_count": normalize_number(raw_data.get("followers_count", "0")),
                "posts_count": normalize_number(raw_data.get("posts_count", "0"))
            },
            "videos_data": [
                {
                    "views": normalize_number(reel.get("views", "0")),
                    "likes": normalize_number(reel.get("likes", "0")),
                    "comments": normalize_number(reel.get("comments", "0")),
                    "link": reel.get("link", "")
                }
                for reel in raw_data.get("reels_data", [])
            ]
        }
    elif platform == 'tiktok':
        profile = raw_data.get("profile", {})
        return {
            "basic_info": {
                "platform": "tiktok",
                "followers_count": profile.get("followers", "0"),
                "likes": profile.get("likes", "0")
            },
            "videos_data": [
                {
                    "views": video.get("views", "0"),
                    "likes": video.get("likes", "0"),
                    "comments": video.get("comments", "0"),
                    "shares": video.get("shares", "0")
                }
                for video in raw_data.get("videos", [])
            ]
        }
    return {}

def load_platform_data(platform, creator=None):
    """載入平台數據"""
    file_paths = {
        'youtube': os.path.join(PROCESSED_DATA_DIR, 'youtube_data_20250220.json'),
        'tiktok': os.path.join(PROCESSED_DATA_DIR, 'tiktok_data_20250220.json'),
        'instagram': os.path.join(PROCESSED_DATA_DIR, 'ig_data_20250223.json')
    }
    
    try:
        file_path = file_paths.get(platform)
        if not file_path or not os.path.exists(file_path):
            return {}

        with open(file_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            
            if platform == 'instagram':
                # Instagram 數據需要特殊處理
                if isinstance(raw_data, list):
                    data_dict = {item['username']: normalize_data(item, platform) 
                               for item in raw_data}
                    if creator:
                        return {creator: data_dict.get(creator)} if creator in data_dict else {}
                    return data_dict
            else:
                # YouTube 和 TikTok 數據處理
                if creator:
                    if creator in raw_data:
                        return {creator: normalize_data(raw_data[creator], platform)}
                    return {}
                return {k: normalize_data(v, platform) for k, v in raw_data.items()}

        return {}
    except Exception as e:
        print(f"載入{platform}數據時發生錯誤: {str(e)}")
        return {}

@stats_bp.route('/stats')
def get_stats():
    """獲取統計數據"""
    platform = request.args.get('platform', '').lower()
    creator = request.args.get('creator', '')

    if not platform:
        return jsonify({"error": "必須指定平台"}), 400

    data = load_platform_data(platform, creator)
    if not data:
        return jsonify({"error": f"找不到數據"}), 404

    return jsonify(data)

@stats_bp.route('/stats/platforms')
def get_platforms():
    """獲取所有平台的創作者列表"""
    platforms = {}
    for platform in ['youtube', 'instagram', 'tiktok']:
        data = load_platform_data(platform)
        platforms[platform] = list(data.keys())
    return jsonify(platforms)

@stats_bp.route('/stats/summary')
def get_stats_summary():
    """獲取數據摘要"""
    platform = request.args.get('platform', '').lower()
    if not platform:
        return jsonify({"error": "必須指定平台"}), 400

    data = load_platform_data(platform)
    summary = {
        "platform": platform,
        "total_creators": len(data),
        "creators": list(data.keys())
    }
    return jsonify(summary)