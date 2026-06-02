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

def get_winning_numbers():
    """ 穩定版爬蟲：加入錯誤捕捉，避免 NoneType 錯誤 """
    try:
        url = 'https://invoice.etax.nat.gov.tw/index.html'
        res = requests.get(url, timeout=10)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 尋找核心容器
        content = soup.find('div', class_='etw-content-left')
        if not content: return None, None, None, None
        
        period = content.find('h2').text.strip()
        # 抓取所有紅色字的號碼
        numbers = [n.text.strip() for n in content.find_all('span', class_='etw-color-red')]
        
        # 確保有足夠的資料，避免 IndexError
        if len(numbers) < 5: return None, None, None, None
        
        return period, numbers[0], numbers[1], numbers[2:5]
    except:
        return None, None, None, None

def check_win(number):
    period, special, grand, heads = get_winning_numbers()
    if not period:
        return "系統目前無法讀取官網號碼，請稍後再試。"
    
    if number == special[-3:]:
        return f"🎉 中獎！【特別獎】\n期別：{period}\n末三碼：{number}"
    if number == grand[-3:]:
        return f"🎉 中獎！【特獎】\n期別：{period}\n末三碼：{number}"
    for h in heads:
        if number == h[-3:]:
            return f"🎉 中獎！【頭獎/增開獎】\n期別：{period}\n末三碼：{number}"
    return f"發票 {number} 經比對 {period}：未中獎"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    user_id = event.source.user_id

    # 【重要】這裡的關鍵字必須跟你 LINE 選單按鈕設定的「文字」完全一致
    if msg == "查看本期中獎號碼":
        period, special, grand, heads = get_winning_numbers()
        if not period:
            reply = "無法讀取，請稍後再試。"
        else:
            reply = f"【{period} 中獎號碼】\n特別獎：{special}\n特獎：{grand}\n頭獎：{', '.join(heads)}"
            
    elif msg == "查看過往對獎歷史":
        try:
            docs = db.collection('invoice_records').where('user_id', '==', user_id)\
                     .order_by('time', direction='DESCENDING').limit(10).stream()
            reply = "【您最近 10 筆紀錄】\n"
            for d in docs:
                data = d.to_dict()
                reply += f"[{data['time'].strftime('%m/%d %H:%M')}] {data['result']}\n"
        except Exception as e:
            reply = "歷史紀錄讀取失敗，可能是索引尚未建立完成。"
            
    elif msg.isdigit() and len(msg) == 3:
        result = check_win(msg)
        # 只有在成功對獎後才寫入 Firebase
        if "無法讀取" not in result:
            db.collection('invoice_records').add({
                'user_id': user_id, 
                'number': msg, 
                'result': result,
                'time': firestore.SERVER_TIMESTAMP
            })
        reply = result
    else:
        reply = "請使用下方選單，或直接輸入發票末三碼對獎。"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    handler.handle(body, signature)
    return 'OK'

if __name__ == "__main__":
    app.run()