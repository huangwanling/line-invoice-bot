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

app = Flask(__name__)

# --- Firebase 初始化 ---
# 請確保您的環境變數已正確設定 JSON 字串
cred = credentials.Certificate(json.loads(os.environ.get('FIREBASE_CREDENTIALS')))
firebase_admin.initialize_app(cred)
db = firestore.client()

# --- LINE Bot 初始化 ---
line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))

# --- 爬蟲函式 ---
def get_invoice_numbers():
    try:
        url = 'https://invoice.etax.nat.gov.tw/index.html'
        response = requests.get(url)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 抓取期別資訊
        period = soup.find('h2', class_='etw-tittle-1').text.strip()
        
        # 抓取號碼資訊
        # 根據官網結構抓取紅字數字
        numbers = [n.text.strip() for n in soup.find_all('span', class_='etw-color-red')]
        
        return f"{period}\n特別獎：{numbers[0]}\n特獎：{numbers[1]}\n頭獎：{numbers[2]}、{numbers[3]}、{numbers[4]}"
    except Exception as e:
        return "暫時無法讀取開獎號碼"

# --- 對獎邏輯 ---
def check_win(number):
    # 這裡預設了對獎邏輯，請根據您實際的需求進行調整
    winning_ends = ["810", "230", "781"] # 範例號碼
    return "中獎啦！" if number in winning_ends else "沒中獎"

# --- LINE 訊息處理 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    user_id = event.source.user_id

    if msg == "查看近四個月的發票中獎號碼":
        reply = get_invoice_numbers()
    
    elif msg == "查看我的近十筆發票紀錄":
        docs = db.collection('invoice_records').where('user_id', '==', user_id)\
                 .order_by('created_at', direction='DESCENDING').limit(10).stream()
        
        reply = "【您的最近 10 筆紀錄】\n"
        has_record = False
        for d in docs:
            has_record = True
            data = d.to_dict()
            time_str = data['created_at'].strftime('%m/%d %H:%M')
            reply += f"[{time_str}] {data['invoice_number']} : {data['status']}\n"
        
        if not has_record:
            reply = "目前沒有對獎紀錄。"

    elif msg.isdigit() and len(msg) == 3:
        status = check_win(msg)
        
        # 寫入 Firebase
        db.collection('invoice_records').add({
            'user_id': user_id,
            'invoice_number': msg,
            'status': status,
            'created_at': datetime.now()
        })
        reply = f"發票末三碼 {msg} 經比對結果為：{status}"
    
    else:
        reply = "歡迎！請直接輸入末三碼對獎，或使用下方按鈕查詢紀錄。"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    handler.handle(body, signature)
    return 'OK'

if __name__ == "__main__":
    app.run()