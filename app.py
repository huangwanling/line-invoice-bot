import os
import json
import requests
from bs4 import BeautifulSoup
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

# --- 優化後的資料抓取邏輯 ---
def get_invoice_numbers():
    try:
        # 加入 headers 模擬真實瀏覽器，降低被阻擋機率
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        url = 'https://invoice.etax.nat.gov.tw/index.html'
        res = requests.get(url, headers=headers, timeout=15)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 財政部目前號碼的 CSS 類別通常是 etw-style-red
        numbers_data = soup.select('.etw-style-red')
        results = [n.text.strip() for n in numbers_data if len(n.text.strip()) >= 3]
        
        return "【最新中獎號碼】\n" + "\n".join(results[:10]) if results else "暫時抓取不到號碼，請稍後再試。"
    except Exception as e:
        return f"爬蟲發生錯誤: {str(e)}"

# --- 資料庫查詢邏輯 ---
def get_user_records(user_id):
    try:
        docs = db.collection('invoice_records').where('user_id', '==', user_id).order_by('time', direction='DESCENDING').limit(10).stream()
        records = [f"末三碼: {d.to_dict()['number']}" for d in docs]
        return "【您最近的 10 筆紀錄】\n" + ("\n".join(records) if records else "尚無紀錄")
    except Exception as e:
        return f"無法讀取紀錄: {str(e)}"

# --- LINE 處理 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    user_id = event.source.user_id

    if msg == "查看近四個月的發票中獎號碼":
        reply = get_invoice_numbers()
    elif msg == "查看我的近十筆發票紀錄":
        reply = get_user_records(user_id)
    elif msg.isdigit() and len(msg) == 3:
        db.collection('invoice_records').add({
            'user_id': user_id, 
            'number': msg, 
            'time': datetime.now()
        })
        reply = f"已紀錄您的發票末三碼: {msg}。"
    else:
        reply = "歡迎！請直接輸入發票末三碼對獎，或使用下方選單。"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

if __name__ == "__main__":
    app.run()