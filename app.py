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
    """ 專業版爬蟲：加入 Headers 模擬瀏覽器，確保不被官網擋下 """
    try:
        url = 'https://invoice.etax.nat.gov.tw/index.html'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        res = requests.get(url, headers=headers, timeout=15)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        
        # 尋找所有紅色號碼區塊
        red_spans = soup.find_all('span', class_='etw-color-red')
        if not red_spans or len(red_spans) < 3:
            return None, None, None, None
            
        period = soup.find('h2', class_='etw-tittle-1').text.strip()
        special = red_spans[0].text.strip()
        grand = red_spans[1].text.strip()
        heads = [s.text.strip() for s in red_spans[2:5]]
        
        return period, special, grand, heads
    except Exception as e:
        print(f"爬蟲發生錯誤: {e}")
        return None, None, None, None

def check_win(number):
    period, special, grand, heads = get_winning_numbers()
    if not period:
        return "系統目前無法讀取官網號碼，請稍後再試。"
    
    if number == special[-3:]:
        return f"🎉 中獎！【特別獎】(1000萬)\n期別：{period}\n末三碼：{number}"
    if number == grand[-3:]:
        return f"🎉 中獎！【特獎】(200萬)\n期別：{period}\n末三碼：{number}"
    for h in heads:
        if number == h[-3:]:
            return f"🎉 中獎！【頭獎/增開獎】(20萬)\n期別：{period}\n末三碼：{number}"
    return f"發票 {number} 經比對 {period}：未中獎"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    msg = event.message.text.strip()
    user_id = event.source.user_id

    # 確保字串與 LINE 後台圖文選單設定的「動作文字」完全一致
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
            reply = "歷史紀錄讀取失敗，請確認 Firebase 索引設定。"
            
    elif msg.isdigit() and len(msg) == 3:
        result = check_win(msg)
        if "中獎" in result or "未中獎" in result:
            db.collection('invoice_records').add({
                'user_id': user_id, 
                'number': msg, 
                'result': result,
                'time': firestore.SERVER_TIMESTAMP
            })
        reply = result
    else:
        reply = "歡迎！請直接輸入末三碼對獎，或使用下方選單。"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    handler.handle(body, signature)
    return 'OK'

if __name__ == "__main__":
    app.run()