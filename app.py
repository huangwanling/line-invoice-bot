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
# 請確保 Vercel 的 Environment Variables 設定了 FIREBASE_CREDENTIALS
cred_dict = json.loads(os.environ.get('FIREBASE_CREDENTIALS'))
cred = credentials.Certificate(cred_dict)
firebase_admin.initialize_app(cred)
db = firestore.client()

line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))

# --- 核心功能：爬蟲 ---
def get_winning_info():
    """爬取官網並返回期別、號碼列表與規則說明"""
    try:
        url = 'https://invoice.etax.nat.gov.tw/index.html'
        res = requests.get(url)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        
        period = soup.find('h2', class_='etw-tittle-1').text.strip()
        # 抓取所有紅色字的號碼 (特別獎、特獎、頭獎)
        red_numbers = [n.text.strip() for n in soup.find_all('span', class_='etw-color-red')]
        
        # 整理顯示內容
        info = f"【{period} 中獎號碼】\n"
        info += f"特別獎：{red_numbers[0]}\n特獎：{red_numbers[1]}\n頭獎：{', '.join(red_numbers[2:5])}\n"
        info += "\n💡 中獎規則：\n二獎：末7碼相同(4萬)\n三獎：末6碼相同(1萬)\n四獎：末5碼相同(4千)\n五獎：末4碼相同(1千)\n六獎：末3碼相同(2百)"
        
        return info, red_numbers
    except:
        return "暫時無法獲取最新號碼，請稍後再試。", []

# --- 對獎邏輯 ---
def check_prize(input_number):
    _, red_numbers = get_winning_info()
    if not red_numbers: return "無法比對"
    
    # 比對頭獎末三碼 (六獎)
    for head in red_numbers[2:5]:
        if input_number == head[-3:]:
            return "🎉 中獎啦！【六獎】(200元)"
    
    return "很可惜，未中獎。"

# --- 處理訊息 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    user_id = event.source.user_id

    # 按鈕：查看中獎號碼
    if msg == "查看中獎號碼":
        info, _ = get_winning_info()
        reply = info
        
    # 按鈕：查看歷史紀錄
    elif msg == "查看我的近十筆發票紀錄":
        docs = db.collection('invoice_records').where('user_id', '==', user_id)\
                 .order_by('created_at', direction=firestore.Query.DESCENDING).limit(10).stream()
        
        reply = "【您最近的發票紀錄】\n"
        for doc in docs:
            data = doc.to_dict()
            time_str = data['created_at'].strftime("%m/%d %H:%M")
            reply += f"{time_str} 輸入 {data['invoice_number']} -> {data['status']}\n"
        
        if reply == "【您最近的發票紀錄】\n": reply = "目前尚無對獎紀錄。"

    # 輸入：對獎
    elif msg.isdigit() and len(msg) == 3:
        status = check_prize(msg)
        # 存入 Firebase
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