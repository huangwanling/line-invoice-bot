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

# --- 核心邏輯：使用公開 API 獲取資料 (穩定版) ---
def update_data():
    try:
        # 使用第三方維護的穩定 API
        response = requests.get("https://invoice.run.place/latest", timeout=10)
        data = response.json()
        
        # 整理資料
        period = data['period']
        numbers = [
            data['super_prize'],  # 特別獎
            data['spc_prize'],    # 特獎
            data['first_prize1'], # 頭獎1
            data['first_prize2'], # 頭獎2
            data['first_prize3']  # 頭獎3
        ]
        
        # 寫入 Firebase
        db.collection('config').document('latest_invoice').set({
            'period': period,
            'numbers': numbers,
            'updated_at': datetime.now()
        })
        return f"更新成功！最新期別：{period}"
    except Exception as e:
        return f"更新失敗，請檢查 API 或網路：{str(e)}"

# --- 路由 ---
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

# --- LINE 訊息處理 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    if "查看近四個月的發票中獎號碼" in msg:
        doc = db.collection('config').document('latest_invoice').get()
        if doc.exists:
            d = doc.to_dict()
            reply = f"【{d['period']}】\n特別獎：{d['numbers'][0]}\n特獎：{d['numbers'][1]}\n頭獎：{', '.join(d['numbers'][2:])}"
        else:
            reply = "資料庫尚未初始化，請訪問 /update。"
    else:
        reply = "請點選下方選單或輸入末三碼對獎。"
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

if __name__ == "__main__":
    app.run()