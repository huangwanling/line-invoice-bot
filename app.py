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
cred_dict = json.loads(os.environ.get('FIREBASE_CREDENTIALS'))
cred = credentials.Certificate(cred_dict)
firebase_admin.initialize_app(cred)
db = firestore.client()
line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))

# --- 爬蟲函式：精確解析財政部最新網頁標籤 ---
def get_winning_numbers():
    try:
        url = 'https://invoice.etax.nat.gov.tw/index.html'
        res = requests.get(url, timeout=10)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        
        period = soup.find('h2', class_='etw-tittle-1').text.strip()
        
        # 抓取所有包含號碼的標籤
        # 財政部現在使用 etw-tbiggest 來標示號碼
        prize_elements = soup.find_all('span', class_='etw-tbiggest')
        
        # 0:特別獎, 1:特獎, 2:頭獎(包含三組)
        special = prize_elements[0].text.strip()
        grand = prize_elements[1].text.strip()
        heads_raw = prize_elements[2].text.strip()
        heads = heads_raw.split('、')
        
        return period, special, grand, heads
    except Exception as e:
        return None, None, None, str(e)

# --- 對獎邏輯 ---
def check_win(number):
    period, special, grand, heads = get_winning_numbers()
    if period is None:
        return f"系統偵錯：爬蟲抓取失敗 (Error: {heads})"
    
    if number == special[-3:]:
        return f"🎉 中獎！【特別獎】\n期別：{period}\n號碼：{number}\n獎金：1000萬元"
    if number == grand[-3:]:
        return f"🎉 中獎！【特獎】\n期別：{period}\n號碼：{number}\n獎金：200萬元"
    for h in heads:
        if number == h[-3:]:
            return f"🎉 中獎！【頭獎/六獎】\n期別：{period}\n號碼：{number}\n獎金：200元(六獎) / 若全對可達20萬"
            
    return f"發票 {number} 經比對 {period}：未中獎"

# --- LINE 訊息處理 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    user_id = event.source.user_id

    if msg == "查看中獎號碼":
        period, special, grand, heads = get_winning_numbers()
        reply = f"【{period} 中獎號碼】\n特別獎：{special}\n特獎：{grand}\n頭獎：{', '.join(heads)}\n\n💡 六獎(200元)為對中頭獎末三碼。"
        
    elif msg == "查看我的近十筆發票紀錄":
        # 確保 Firebase 複合索引已建立完成
        docs = db.collection('invoice_records').where('user_id', '==', user_id)\
                 .order_by('time', direction='DESCENDING').limit(10).stream()
        reply = "【您最近的發票紀錄】\n"
        for d in docs:
            data = d.to_dict()
            time_str = data['time'].strftime('%m/%d %H:%M')
            reply += f"[{time_str}] {data['number']}: {data['result']}\n"
            
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
        reply = "歡迎使用！請輸入末三碼對獎，或點選下方選單。"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    handler.handle(body, signature)
    return 'OK'

if __name__ == "__main__":
    app.run()