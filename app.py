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

# --- 初始化 ---
cred = credentials.Certificate(json.loads(os.environ.get('FIREBASE_CREDENTIALS')))
firebase_admin.initialize_app(cred)
db = firestore.client()
line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))

# --- 核心功能：爬蟲與對獎 ---
def get_winning_numbers():
    url = 'https://invoice.etax.nat.gov.tw/index.html'
    res = requests.get(url)
    res.encoding = 'utf-8'
    soup = BeautifulSoup(res.text, 'html.parser')
    period = soup.find('h2').text.strip()
    
    # 這裡抓取官網的對應數字
    # 特別獎/特獎/頭獎列表
    prizes = [n.text.strip() for n in soup.find_all('p', class_='etw-tbig')]
    first_prizes = soup.find('p', class_='etw-tbig-1').text.strip().split('、')
    
    return period, prizes[0], prizes[1], first_prizes

def check_win(number):
    period, special, grand, heads = get_winning_numbers()
    
    # 比對邏輯
    if number == special[-3:]:
        return f"🎉 中獎！【特別獎】\n期別：{period}\n號碼：{number}\n獎金：1000萬元"
    if number == grand[-3:]:
        return f"🎉 中獎！【特獎】\n期別：{period}\n號碼：{number}\n獎金：200萬元"
    for h in heads:
        if number == h[-3:]:
            return f"🎉 中獎！【頭獎】\n期別：{period}\n號碼：{number}\n獎金：20萬元"
            
    return f"發票 {number} 經比對 {period}：未中獎"

# --- 處理訊息 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    user_id = event.source.user_id

    if msg == "查看中獎號碼":
        period, special, grand, heads = get_winning_numbers()
        reply = f"【{period} 中獎號碼】\n特別獎：{special}\n特獎：{grand}\n頭獎：{', '.join(heads)}"
        
    elif msg == "我的發票紀錄":
        docs = db.collection('invoice_records').where('user_id', '==', user_id)\
                 .order_by('time', direction='DESCENDING').limit(10).stream()
        reply = "【您最近 10 筆紀錄】\n"
        for d in docs:
            data = d.to_dict()
            reply += f"[{data['time'].strftime('%m/%d %H:%M')}] {data['result']}\n"
            
    elif msg.isdigit() and len(msg) == 3:
        result = check_win(msg)
        db.collection('invoice_records').add({
            'user_id': user_id, 
            'number': msg, 
            'result': result,
            'time': firestore.SERVER_TIMESTAMP
        })
        reply = result
    else:
        reply = "歡迎使用！請輸入末三碼對獎，或使用下方選單。"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    handler.handle(body, signature)
    return 'OK'

if __name__ == "__main__":
    app.run()