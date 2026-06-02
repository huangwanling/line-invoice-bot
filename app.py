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

# --- 功能邏輯 ---
def get_winning_numbers():
    """爬取財政部最新中獎號碼"""
    try:
        url = 'https://invoice.etax.nat.gov.tw/'
        soup = BeautifulSoup(requests.get(url).text, 'html.parser')
        # 爬取標題與號碼
        titles = [t.text for t in soup.find_all('th', class_='title')]
        numbers = [n.text.strip() for n in soup.find_all('span', class_='etw-color-red')]
        
        reply = "【最新中獎號碼】\n"
        # 簡單組合顯示 (建議根據實際爬取結構微調)
        for i in range(min(len(titles), len(numbers))):
            reply += f"{titles[i]}: {numbers[i]}\n"
        return reply
    except: return "暫時無法取得號碼，請稍後再試。"

def check_if_win(num):
    """判斷末三碼是否中頭獎 (簡易版)"""
    # 這裡你可以擴充，爬取頭獎號碼並進行比對
    # 暫時邏輯：若輸入末三碼符合頭獎號碼之末三碼即視為中獎
    winning_ends = ["810", "230", "781"] # 範例號碼，請依實際情況替換
    return num in winning_ends

# --- 處理 LINE 訊息 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    user_id = event.source.user_id

    # 1. 點擊「查看中獎號碼」按鈕
    if msg == "查看中獎號碼":
        reply = get_winning_numbers()
    
    # 2. 點擊「查看我的近十筆發票紀錄」按鈕
    elif msg == "查看我的近十筆發票紀錄":
        docs = db.collection('invoice_records').where('user_id', '==', user_id)\
                 .order_by('created_at', direction=firestore.Query.DESCENDING).limit(10).stream()
        
        reply = "【您的最近 10 筆紀錄】\n"
        for d in docs:
            data = d.to_dict()
            time_str = data['created_at'].strftime("%m/%d %H:%M")
            status = data.get('status', '未確認')
            reply += f"{time_str} 輸入{data['invoice_number']}: {status}\n"
        if not reply.endswith('\n'): reply = "目前沒有對獎紀錄。"
    
    # 3. 一般輸入發票末三碼
    elif msg.isdigit() and len(msg) == 3:
        is_win = check_if_win(msg)
        status = "🎉 中獎啦！" if is_win else "沒中獎"
        
        # 存入 Firebase (包含時間與中獎狀態)
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