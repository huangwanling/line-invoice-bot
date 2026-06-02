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

# --- Vercel 環境初始化 ---
# 請確保 Vercel 環境變數 FIREBASE_CREDENTIALS 存的是完整的 JSON 字串
firebase_config = json.loads(os.environ.get('FIREBASE_CREDENTIALS'))
cred = credentials.Certificate(firebase_config)
firebase_admin.initialize_app(cred)
db = firestore.client()

line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))

# --- 爬蟲函式 ---
def update_invoice_to_db():
    try:
        url = 'https://invoice.etax.nat.gov.tw/index.html'
        res = requests.get(url, timeout=10)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        period = soup.find('h2', class_='etw-tittle-1').text.strip()
        numbers = [n.text.strip() for n in soup.find_all('span', class_='etw-color-red')]
        
        db.collection('config').document('latest_invoice').set({
            'period': period,
            'numbers': numbers,
            'updated_at': datetime.now()
        })
        return True
    except:
        return False

# --- LINE 訊息處理 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    user_id = event.source.user_id

    # 1. 查看最新中獎號碼
    if msg == "查看近四個月的發票中獎號碼":
        doc_ref = db.collection('config').document('latest_invoice')
        doc = doc_ref.get()
        if not doc.exists:
            update_invoice_to_db()
            doc = doc_ref.get()
            
        if doc.exists:
            data = doc.to_dict()
            reply = f"【{data['period']}】\n特別獎：{data['numbers'][0]}\n特獎：{data['numbers'][1]}\n頭獎：{', '.join(data['numbers'][2:5])}"
        else:
            reply = "暫時無法讀取號碼，請稍後再試。"

    # 2. 查看過往紀錄
    elif msg == "查看我的近十筆發票紀錄":
        docs = db.collection('invoice_records').where('user_id', '==', user_id).order_by('created_at', direction='DESCENDING').limit(10).stream()
        records = [f"[{d.to_dict()['created_at'].strftime('%m/%d')}] {d.to_dict()['invoice_number']}: {d.to_dict()['status']}" for d in docs]
        reply = "【您的最近十筆紀錄】\n" + ("\n".join(records) if records else "無紀錄")

    # 3. 對獎邏輯
    elif msg.isdigit() and len(msg) == 3:
        doc = db.collection('config').document('latest_invoice').get()
        if not doc.exists:
            reply = "請先點擊選單「查看近四個月的發票中獎號碼」以更新最新資訊。"
        else:
            data = doc.to_dict()
            is_win = any(msg == n[-3:] for n in data['numbers'][2:5])
            status = "中獎啦！(六獎：200元)" if is_win else "未中獎"
            
            db.collection('invoice_records').add({
                'user_id': user_id, 'invoice_number': msg, 'status': status, 'created_at': datetime.now()
            })
            reply = f"發票末三碼 {msg} 結果：\n【{status}】\n期別：{data['period']}"
    else:
        reply = "請使用下方選單，或輸入 3 位數末三碼對獎。"

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