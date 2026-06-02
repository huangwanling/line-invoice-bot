import os
import json
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, abort

# Firebase 與 LINE SDK
import firebase_admin
from firebase_admin import credentials, firestore
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# --- 1. 初始化服務 ---
# 讀取 Firebase 金鑰 (從環境變數)
cred_json = json.loads(os.environ.get('FIREBASE_CREDENTIALS'))
cred = credentials.Certificate(cred_json)
firebase_admin.initialize_app(cred)
db = firestore.client()

# 設定 LINE API
line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))

# --- 2. 核心功能函式 ---
def get_invoice_numbers():
    try:
        url = 'https://invoice.etax.nat.gov.tw/'
        headers = {'User-Agent': 'Mozilla/5.0'}
        html = requests.get(url, headers=headers)
        html.encoding = 'utf-8'
        soup = BeautifulSoup(html.text, 'html.parser')
        numbers = soup.find_all('span', class_='etw-color-red')
        return [num.text.strip() for num in numbers if num.text.strip()]
    except:
        return []

def check_prize(user_num, invoice_list):
    if not invoice_list: return "目前無法取得中獎號碼，請稍後再試。"
    try:
        sp_prize, g_prize = invoice_list[0], invoice_list[1]
        grand_prizes = invoice_list[2].split()
        if user_num == sp_prize[-3:]: return f"🎉【特別獎】末三碼對中！完整號碼：{sp_prize}"
        if user_num == g_prize[-3:]: return f"🎉【特獎】末三碼對中！完整號碼：{g_prize}"
        for grand in grand_prizes:
            if user_num == grand[-3:]: return f"🎉【頭獎末三碼】對中！完整號碼：{grand}"
        return "😭 殘念！這組末三碼沒有對中任何獎項。"
    except: return "對獎計算時發生錯誤。"

def save_invoice_record(user_id, user_num):
    db.collection('invoice_records').add({
        'user_id': user_id,
        'number': user_num,
        'time': firestore.SERVER_TIMESTAMP
    })

# --- 3. Webhook 入口 ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- 4. 訊息處理邏輯 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    
    # 判斷是否為對獎指令
    if msg.isdigit() and len(msg) == 3:
        invoice_list = get_invoice_numbers()
        reply_text = check_prize(msg, invoice_list)
        # 存入 Firebase
        save_invoice_record(event.source.user_id, msg)
        reply_text += "\n\n(紀錄已存入資料庫)"
    else:
        reply_text = "歡迎！請直接輸入「發票末三碼」數字（例如：123）我將為您即時對獎！"
        
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

if __name__ == "__main__":
    app.run()