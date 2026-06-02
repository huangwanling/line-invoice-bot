import os
import json
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, abort
import firebase_admin
from firebase_admin import credentials, firestore
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# --- 初始化 (連接 Vercel 環境變數) ---
cred = credentials.Certificate(json.loads(os.environ.get('FIREBASE_CREDENTIALS')))
firebase_admin.initialize_app(cred)
db = firestore.client()
line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))

# --- 功能函式 ---
def get_invoice_numbers():
    try:
        url = 'https://invoice.etax.nat.gov.tw/'
        soup = BeautifulSoup(requests.get(url).text, 'html.parser')
        # 爬取紅色字的號碼
        numbers = [n.text.strip() for n in soup.find_all('span', class_='etw-color-red')]
        return "\n".join(numbers) if numbers else "暫時無法取得號碼。"
    except: return "爬蟲發生錯誤。"

def get_user_records(user_id):
    docs = db.collection('invoice_records').where('user_id', '==', user_id).order_by('time', direction='DESCENDING').limit(5).stream()
    records = [f"{d.to_dict()['number']} ({d.to_dict()['time'].strftime('%m/%d %H:%M')})" for d in docs]
    return "\n".join(records) if records else "目前還沒有紀錄喔！"

# --- 處理 LINE 訊息 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    
    # 這裡就是你的「按鈕對應邏輯」
    if msg == "本期開獎":
        reply = "【本期中獎號碼】\n" + get_invoice_numbers()
    elif msg == "開始對獎":
        reply = "收到！請直接輸入當期發票末三碼數字（例如：123）"
    elif msg == "歷史紀錄":
        reply = "【您的最近對獎紀錄】\n" + get_user_records(event.source.user_id)
    
    # 手動輸入數字對獎
    elif msg.isdigit() and len(msg) == 3:
        # 你原本的 check_prize 邏輯可放在這裡
        db.collection('invoice_records').add({
            'user_id': event.source.user_id, 
            'number': msg, 
            'time': firestore.SERVER_TIMESTAMP
        })
        reply = f"已收到您的發票號碼：{msg}，已存入紀錄！"
    else:
        reply = "歡迎使用！請使用下方選單進行操作。"
        
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    handler.handle(body, signature)
    return 'OK'

if __name__ == "__main__":
    app.run()