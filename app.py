import os
import json
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, abort
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# --- Firebase 初始化 ---
cred = credentials.Certificate(json.loads(os.environ.get('FIREBASE_CREDENTIALS')))
firebase_admin.initialize_app(cred)
db = firestore.client()

# --- LINE Bot 初始化 ---
line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))

# --- 核心邏輯函式 ---

def get_invoice_numbers():
    """爬取最新期別中獎號碼"""
    try:
        url = 'https://invoice.etax.nat.gov.tw/index.html'
        response = requests.get(url, timeout=10)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        period = soup.find('h2', class_='etw-tittle-1').text.strip()
        numbers = [n.text.strip() for n in soup.find_all('span', class_='etw-color-red')]
        return f"【{period}】\n特別獎：{numbers[0]}\n特獎：{numbers[1]}\n頭獎：{numbers[2]}, {numbers[3]}, {numbers[4]}"
    except:
        return "暫時無法讀取開獎號碼，請稍後再試。"

def check_win_detail(number):
    """進階對獎邏輯 (範例)"""
    # 實際運作時，您可以進一步比較爬取到的完整號碼陣列
    if number == "810":
        return "【中獎通知】\n期別：115年5-6月\n獎項：六獎\n金額：200元"
    return "【未中獎】\n期別：115年5-6月\n再接再厲！"

# --- LINE 事件處理 ---

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    user_id = event.source.user_id

    # 1. 處理圖文選單按鈕觸發
    if msg == "查看近四個月的發票中獎號碼":
        reply = get_invoice_numbers()
    
    elif msg == "查看我的近十筆發票紀錄":
        docs = db.collection('invoice_records').where('user_id', '==', user_id)\
                 .order_by('created_at', direction='DESCENDING').limit(10).stream()
        
        records = []
        for d in docs:
            data = d.to_dict()
            time_str = data['created_at'].strftime('%m/%d %H:%M')
            records.append(f"[{time_str}] {data['invoice_number']}: {data['status'][:5]}...") # 顯示簡短結果
        
        reply = "【您的最近 10 筆紀錄】\n" + ("\n".join(records) if records else "目前沒有紀錄。")
    
    # 2. 處理使用者手動輸入發票末三碼
    elif msg.isdigit() and len(msg) == 3:
        status = check_win_detail(msg)
        
        # 寫入 Firebase
        db.collection('invoice_records').add({
            'user_id': user_id,
            'invoice_number': msg,
            'status': status,
            'created_at': datetime.now()
        })
        reply = f"發票末三碼 {msg} 比對結果：\n\n{status}"
    
    # 3. 預設訊息
    else:
        reply = "請輸入 3 位數發票末三碼對獎，或使用下方選單功能。"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

if __name__ == "__main__":
    app.run()