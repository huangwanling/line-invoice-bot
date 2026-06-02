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

# --- 爬蟲與對獎核心 ---
def get_invoice_data():
    """ 爬取官網並回傳：期別, 特別獎, 特獎, 頭獎列表 """
    try:
        url = 'https://invoice.etax.nat.gov.tw/index.html'
        response = requests.get(url, timeout=10)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        
        period = soup.find('h2', class_='etw-tittle-1').text.strip()
        numbers = [n.text.strip() for n in soup.find_all('span', class_='etw-color-red')]
        # numbers[0]:特別獎, numbers[1]:特獎, numbers[2:5]:頭獎
        return period, numbers[0], numbers[1], numbers[2:5]
    except:
        return None, None, None, None

def check_win(number):
    period, special, grand, heads = get_invoice_data()
    if not period:
        return "暫時無法讀取開獎號碼"
    
    if number == special[-3:]:
        return f"🎉中獎！特別獎 (1000萬) - {period}"
    if number == grand[-3:]:
        return f"🎉中獎！特獎 (200萬) - {period}"
    for h in heads:
        if number == h[-3:]:
            return f"🎉中獎！頭獎 (20萬) - {period}"
            
    return "沒中獎"

# --- LINE 訊息處理 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    user_id = event.source.user_id

    if msg == "查看近四個月的發票中獎號碼":
        period, special, grand, heads = get_invoice_data()
        if not period:
            reply = "無法讀取，請稍後再試。"
        else:
            reply = f"【{period}】\n特別獎：{special}\n特獎：{grand}\n頭獎：{', '.join(heads)}"
    
    elif msg == "查看我的近十筆發票紀錄":
        # 注意：若此處報錯，請點擊錯誤訊息中的連結建立 Firebase 索引
        docs = db.collection('invoice_records').where('user_id', '==', user_id)\
                 .order_by('created_at', direction='DESCENDING').limit(10).stream()
        
        reply = "【您的最近 10 筆紀錄】\n"
        records = [f"[{d.to_dict()['created_at'].strftime('%m/%d %H:%M')}] {d.to_dict()['invoice_number']} : {d.to_dict()['status']}" for d in docs]
        reply += "\n".join(records) if records else "目前沒有紀錄。"

    elif msg.isdigit() and len(msg) == 3:
        status = check_win(msg)
        db.collection('invoice_records').add({
            'user_id': user_id,
            'invoice_number': msg,
            'status': status,
            'created_at': firestore.SERVER_TIMESTAMP
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