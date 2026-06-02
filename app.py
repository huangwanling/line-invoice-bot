import os
import json
import requests
from bs4 import BeautifulSoup
from flask import Flask, request
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# --- 初始化 ---
cred_dict = json.loads(os.environ.get('FIREBASE_CREDENTIALS'))
cred = credentials.Certificate(cred_dict)
firebase_admin.initialize_app(cred)
db = firestore.client()

line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))

# --- 核心爬蟲 ---
def get_winning_info():
    try:
        url = 'https://invoice.etax.nat.gov.tw/index.html'
        res = requests.get(url)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 抓取包含號碼的核心區塊
        content = soup.find('div', class_='etw-content-left')
        period = content.find('h2').text.strip()
        # 抓取所有紅色字的號碼 (0:特別獎, 1:特獎, 2,3,4:頭獎)
        numbers = [n.text.strip() for n in content.find_all('span', class_='etw-color-red')]
        
        return period, numbers
    except Exception as e:
        return None, None

# --- 對獎邏輯 ---
def check_prize(input_number):
    period, numbers = get_winning_info()
    if not numbers: return "暫時無法讀取開獎號碼"
    
    # 比對六獎 (頭獎末三碼)
    heads = numbers[2:5]
    for head in heads:
        if input_number == head[-3:]:
            return f"🎉 中獎！【六獎】(200元)\n期別：{period}\n號碼：{head}"
            
    return f"很可惜，末三碼 {input_number} 未中獎。"

# --- 處理 LINE 訊息 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    user_id = event.source.user_id

    if msg == "查看中獎號碼":
        period, numbers = get_winning_info()
        if not period:
            reply = "讀取號碼失敗，請稍後再試。"
        else:
            reply = f"【{period} 中獎號碼】\n特別獎：{numbers[0]}\n特獎：{numbers[1]}\n頭獎：{', '.join(numbers[2:5])}"
        
    elif msg == "查看我的近十筆發票紀錄":
        docs = db.collection('invoice_records').where('user_id', '==', user_id)\
                 .order_by('created_at', direction=firestore.Query.DESCENDING).limit(10).stream()
        
        reply = "【最近 10 筆紀錄】\n"
        has_record = False
        for d in docs:
            has_record = True
            data = d.to_dict()
            reply += f"{data['created_at'].strftime('%m/%d %H:%M')} 輸入{data['invoice_number']}: {data['status']}\n"
        
        if not has_record: reply = "尚無查詢紀錄。"

    elif msg.isdigit() and len(msg) == 3:
        status = check_prize(msg)
        # 存入 Firebase
        db.collection('invoice_records').add({
            'user_id': user_id,
            'invoice_number': msg,
            'status': status,
            'created_at': datetime.now()
        })
        reply = f"發票末三碼 {msg} 經比對：{status}"
    else:
        reply = "歡迎！請直接輸入末三碼對獎，或使用下方按鈕查詢。"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    handler.handle(body, signature)
    return 'OK'

if __name__ == "__main__":
    app.run()