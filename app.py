import os
import json
import requests
from flask import Flask, request, abort
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from linebot.exceptions import InvalidSignatureError

app = Flask(__name__)

# --- 初始化 ---
cred_dict = json.loads(os.environ.get('FIREBASE_CREDENTIALS'))
cred = credentials.Certificate(cred_dict)
firebase_admin.initialize_app(cred)
db = firestore.client()

line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))

# --- 核心邏輯：直接獲取公開 API 資料 (不再爬蟲) ---
def update_data():
    try:
        # 使用財政部公開資料來源 API，這非常穩定
        api_url = "https://invoice.run.place/latest"
        response = requests.get(api_url, timeout=10)
        data = response.json()
        
        # 整理資料格式
        period = data['period']
        numbers = [
            data['super_prize'],  # 特別獎
            data['spc_prize'],    # 特獎
            data['first_prize1'], # 頭獎 1
            data['first_prize2'], # 頭獎 2
            data['first_prize3']  # 頭獎 3
        ]
        
        # 寫入 Firebase
        db.collection('config').document('latest_invoice').set({
            'period': period,
            'numbers': numbers,
            'updated_at': datetime.now()
        })
        return f"更新成功！最新期別：{period}"
    except Exception as e:
        return f"更新失敗：請檢查 API 狀況 - {str(e)}"

# --- 路由與其他邏輯維持不變 ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@app.route("/update")
def update():
    return update_data()

# (後面您的 LineBot 處理邏輯保持不變)