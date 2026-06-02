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

# --- 核心邏輯：更新資料 ---
def update_data():
    try:
        # 使用財政部公開資料網址
        url = 'https://invoice.etax.nat.gov.tw/invoice.html'
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=15)
        res.encoding = 'utf-8'
        # 此處保留您原先的 BeautifulSoup 邏輯，但若持續失敗請改用 API
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(res.text, 'html.parser')
        
        period = soup.select_one('.etw-tittle-1').text.strip()
        numbers = [n.text.strip() for n in soup.select('.etw-style-red')]
        
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
    except Exception:
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
            reply = f"【{d['period']}】\n特別獎：{d['numbers'][0]}\n特獎：{d['numbers'][1]}"
        else:
            reply = "資料庫尚未初始化，請訪問 /update。"
    else:
        reply = "請點選下方選單。"
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

if __name__ == "__main__":
    app.run()