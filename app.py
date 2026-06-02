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
cred = credentials.Certificate(json.loads(os.environ.get('FIREBASE_CREDENTIALS')))
firebase_admin.initialize_app(cred)
db = firestore.client()
line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))

# --- 核心：修正後的爬蟲 ---
def get_winning_numbers():
    try:
        url = 'https://invoice.etax.nat.gov.tw/index.html'
        res = requests.get(url, timeout=10)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 使用更穩健的定位方式：找整個表格區塊
        period = soup.find('h2', class_='etw-tittle-1').text.strip()
        
        # 抓取所有特別獎、特獎、頭獎的紅色數字
        red_numbers = [n.text.strip() for n in soup.find_all('span', class_='etw-color-red')]
        
        # 特別獎: index 0, 特獎: index 1, 頭獎: index 2~4
        return period, red_numbers[0], red_numbers[1], red_numbers[2:5]
    except Exception as e:
        return None, None, None, None

def check_win(number):
    period, special, grand, heads = get_winning_numbers()
    if not period:
        return "暫時無法讀取開獎號碼，請稍後再試。"
    
    if number == special[-3:]:
        return f"🎉 中獎！【特別獎】(1000萬)\n期別：{period}\n末三碼：{number}"
    if number == grand[-3:]:
        return f"🎉 中獎！【特獎】(200萬)\n期別：{period}\n末三碼：{number}"
    for h in heads:
        if number == h[-3:]:
            return f"🎉 中獎！【頭獎/增開獎】(20萬)\n期別：{period}\n末三碼：{number}"
            
    return f"發票 {number} 經比對 {period}：未中獎"

# --- 訊息處理 (關鍵：確保文字完全一致) ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    user_id = event.source.user_id

    # 這裡對應你截圖中的按鈕文字
    if msg == "查看本期中獎號碼":
        period, special, grand, heads = get_winning_numbers()
        if not period:
            reply = "無法讀取，請稍後再試。"
        else:
            reply = f"【{period} 中獎號碼】\n特別獎：{special}\n特獎：{grand}\n頭獎：{', '.join(heads)}\n\n💡 六獎：末3碼與頭獎相同(200元)"
        
    elif msg == "查看過往對獎歷史":
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
        reply = "歡迎！請直接輸入末三碼對獎，或使用選單。"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    handler.handle(body, signature)
    return 'OK'

if __name__ == "__main__":
    app.run()