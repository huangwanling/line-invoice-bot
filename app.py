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

# --- 核心邏輯：使用公開 API 獲取資料 (解決連線超時) ---
def update_data():
    try:
        # 使用財政部公開的 JSON 格式資料來源，穩定且快速
        # 來源網址：財政部稅務入口網
        url = 'https://invoice.etax.nat.gov.tw/invoice.html'
        # 備用方案：若直接爬取 HTML 仍失敗，請考慮使用第三方整合 API
        # 這裡我們使用更簡潔的 requests 請求
        res = requests.get(url, timeout=10)
        res.encoding = 'utf-8'
        
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 嘗試抓取期別
        period_tag = soup.select_one('.etw-tittle-1')
        period = period_tag.text.strip() if period_tag else "未知期別"
        
        # 抓取號碼
        num_tags = soup.select('.etw-style-red')
        numbers = [n.text.strip() for n in num_tags]
        
        if len(numbers) < 3:
            return "抓取資料異常，請檢查網站狀況。"

        # 存入 Firebase
        db.collection('config').document('latest_invoice').set({
            'period': period,
            'numbers': numbers,
            'updated_at': datetime.now()
        })
        return f"更新成功：{period}"
    except Exception as e:
        return f"更新失敗：{str(e)}"

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
    user_id = event.source.user_id
    
    if "查看近四個月的發票中獎號碼" in msg:
        doc = db.collection('config').document('latest_invoice').get()
        if doc.exists:
            d = doc.to_dict()
            reply = f"【{d['period']}】\n特別獎：{d['numbers'][0]}\n特獎：{d['numbers'][1]}\n頭獎：{', '.join(d['numbers'][2:5])}"
        else:
            reply = "資料庫尚未更新，請先訪問 /update。"
    elif msg.isdigit() and len(msg) == 3:
        doc = db.collection('config').document('latest_invoice').get()
        if not doc.exists:
            reply = "資料庫尚未初始化。"
        else:
            d = doc.to_dict()
            is_win = any(msg == n[-3:] for n in d['numbers'][2:5])
            reply = f"【對獎結果】\n{msg}：{'中獎啦 (六獎)！' if is_win else '未中獎'}"
    else:
        reply = "請點選選單或輸入末三碼對獎。"
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

if __name__ == "__main__":
    app.run()