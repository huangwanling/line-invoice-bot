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
from linebot.exceptions import InvalidSignatureError

app = Flask(__name__)

# --- 初始化 ---
# 確保您的 Vercel Environment Variables 已經設定好 FIREBASE_CREDENTIALS
cred_dict = json.loads(os.environ.get('FIREBASE_CREDENTIALS'))
cred = credentials.Certificate(cred_dict)
firebase_admin.initialize_app(cred)
db = firestore.client()

line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))

# --- 爬蟲並更新至 Firebase ---
def update_data():
    try:
        url = 'https://invoice.etax.nat.gov.tw/index.html'
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=10)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 抓取期別與號碼
        period = soup.find('h2', class_='etw-tittle-1').text.strip()
        numbers = [n.text.strip() for n in soup.find_all('span', class_='etw-color-red')]
        
        db.collection('config').document('latest_invoice').set({
            'period': period,
            'numbers': numbers,
            'updated_at': datetime.now()
        })
        return f"更新成功：{period}"
    except Exception as e:
        return f"爬蟲失敗：{str(e)}"

# --- 路由 ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@app.route("/update")
def update():
    return update_data()

# --- LINE 訊息處理 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    user_id = event.source.user_id

    # 1. 處理選單按鈕
    if msg == "查看近四個月的發票中獎號碼":
        doc = db.collection('config').document('latest_invoice').get()
        if doc.exists:
            d = doc.to_dict()
            reply = f"【{d['period']}】\n特別獎：{d['numbers'][0]}\n特獎：{d['numbers'][1]}\n頭獎：{', '.join(d['numbers'][2:5])}"
        else:
            reply = "資料庫尚未初始化，請先訪問 /update 網址進行更新。"
    
    elif msg == "查看我的近十筆發票紀錄":
        docs = db.collection('invoice_records').where('user_id', '==', user_id).order_by('created_at', direction='DESCENDING').limit(10).stream()
        res = [f"[{d.to_dict()['created_at'].strftime('%m/%d')}] {d.to_dict()['invoice_number']}: {d.to_dict()['status']}" for d in docs]
        reply = "【近十筆紀錄】\n" + ("\n".join(res) if res else "無紀錄")
    
    # 2. 對獎邏輯
    elif msg.isdigit() and len(msg) == 3:
        doc = db.collection('config').document('latest_invoice').get()
        if not doc.exists:
            reply = "系統資料更新中，請稍後再試。"
        else:
            d = doc.to_dict()
            # 比對頭獎末三碼
            is_win = any(msg == n[-3:] for n in d['numbers'][2:5])
            status = "中獎啦！(六獎: 200元)" if is_win else "未中獎"
            
            # 寫入 Firebase
            db.collection('invoice_records').add({
                'user_id': user_id, 
                'invoice_number': msg, 
                'status': status, 
                'created_at': datetime.now()
            })
            reply = f"發票末三碼 {msg} 比對結果：\n【{status}】\n期別：{d['period']}"
    else:
        reply = "請點擊下方選單，或輸入 3 位數發票末三碼對獎。"
    
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

if __name__ == "__main__":
    app.run()