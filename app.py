import os
import json
import requests
from bs4 import BeautifulSoup
from flask import Flask, request
import firebase_admin
from firebase_admin import credentials, firestore
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# --- 初始化 ---
cred = credentials.Certificate(json.loads(os.environ.get('FIREBASE_CREDENTIALS')))
firebase_admin.initialize_app(cred)
db = firestore.client()
line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))

# --- 功能函式 ---
def get_invoice_numbers():
    try:
        url = 'https://invoice.etax.nat.gov.tw/'
        response = requests.get(url)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        numbers_data = soup.find_all('span', class_='etw-color-red')
        results = [n.text.strip() for n in numbers_data if len(n.text.strip()) >= 3]
        return "【近四個月中獎號碼】\n" + "\n".join(results[:10])
    except Exception as e:
        return f"暫時無法抓取最新號碼: {e}"

def get_user_records(user_id):
    try:
        query = db.collection('invoice_records').where('user_id', '==', user_id).order_by('time', direction='DESCENDING').limit(10)
        docs = query.stream()
        records = [f"末三碼: {d.to_dict()['number']}" for d in docs]
        return "【您最近的 10 筆紀錄】\n" + ("\n".join(records) if records else "尚無紀錄")
    except Exception as e:
        return f"無法讀取紀錄: {e}"

# --- 處理訊息 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    user_id = event.source.user_id

    # 【關鍵點：這些文字必須與你 LINE 後台圖文選單設定的完全一致】
    if msg == "查看近四個月的發票中獎號碼":
        reply = get_invoice_numbers()
    elif msg == "查看我的近十筆發票紀錄":
        reply = get_user_records(user_id)
    elif msg.isdigit() and len(msg) == 3:
        db.collection('invoice_records').add({'user_id': user_id, 'number': msg, 'time': firestore.SERVER_TIMESTAMP})
        reply = f"已紀錄您的發票末三碼: {msg}。"
    else:
        reply = "歡迎！請直接輸入發票後三碼對獎，或使用下方選單。"
        
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    handler.handle(body, signature)
    return 'OK'

if __name__ == "__main__":
    app.run()