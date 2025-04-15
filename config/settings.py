import os

# 基礎路徑配置
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')

# 數據路徑配置
RAW_DATA_DIR = os.path.join(OUTPUT_DIR, 'raw')
PROCESSED_DATA_DIR = OUTPUT_DIR

# API 配置
API_HOST = 'localhost'
API_PORT = 5000 