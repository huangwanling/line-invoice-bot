import os
import requests
from flask import Flask, request, abort
from bs4 import BeautifulSoup
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# 從環境變數讀取金鑰
line_bot_api = LineBotApi(os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))

# 1. 爬蟲函式 (保持不變)
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

# 2. 對獎邏輯 (保持不變)
def check_prize(user_num, invoice_list):
    if not invoice_list: return "目前無法取得中獎號碼，請稍後再試。"
    try:
        sp_prize, g_prize = invoice_list[0], invoice_list[1]
        grand_prizes = invoice_list[2].split()
        if user_num == sp_prize[-3:]: return f"🎉【特別獎 1000 萬】末三碼對中！完整號碼：{sp_prize}"
        if user_num == g_prize[-3:]: return f"🎉【特獎 200 萬】末三碼對中！完整號碼：{g_prize}"
        for grand in grand_prizes:
            if user_num == grand[-3:]: return f"🎉【頭獎末三碼】對中！完整號碼：{grand}"
        return "😭 殘念！這組末三碼沒有對中任何獎項。"
    except: return "對獎計算時發生錯誤。"

# 3. LINE Webhook 入口
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# 4. 處理 LINE 訊息 (整合爬蟲)
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text.strip()
    
    # 如果使用者輸入的是 3 位數字，執行對獎
    if user_text.isdigit() and len(user_text) == 3:
        invoice_list = get_invoice_numbers()
        reply_text = check_prize(user_text, invoice_list)
    else:
        reply_text = "請輸入「發票末三碼」數字（例如：123），我將為您即時對獎！"
        
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

if __name__ == "__main__":
    app.run()