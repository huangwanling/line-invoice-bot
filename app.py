import os
import requests
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup

# 引入 LINE BOT SDK 的必備工具
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# 🔒 【安全機制】從雲端環境變數讀取密碼，程式碼內完全不留任何明文金鑰
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 1. 爬取財政部最新發票號碼的爬蟲函式
def get_invoice_numbers():
    try:
        url = 'https://invoice.etax.nat.gov.tw/'
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        html = requests.get(url, headers=headers)
        html.encoding = 'utf-8'
        soup = BeautifulSoup(html.text, 'html.parser')
        
        # 撈取中獎號碼字串（特別獎、特獎、頭獎）
        numbers = soup.find_all('span', class_='etw-color-red')
        
        invoice_list = []
        for num in numbers:
            text = num.text.strip()
            if text:
                invoice_list.append(text)
                
        return invoice_list
    except Exception as e:
        print(f"爬蟲發生錯誤: {e}")
        return []

# 2. 自動比對發票末三碼的中獎邏輯
def check_prize(user_num, invoice_list):
    if not invoice_list:
        return "抱歉，目前無法取得財政部發票中獎號碼，請稍後再試。"
        
    try:
        sp_prize = invoice_list[0]               # 特別獎 (1000萬)
        g_prize = invoice_list[1]                # 特獎 (200萬)
        grand_prizes = invoice_list[2].split()   # 頭獎 (有三組，用空格切開)
        
        # 檢查特別獎
        if user_num == sp_prize[-3:]:
            return f"🎉 有機會中【特別獎 1000 萬】喔！請核對完整發票號碼是否有對中：{sp_prize}"
            
        # 檢查特獎
        if user_num == g_prize[-3:]:
            return f"🎉 有機會中【特獎 200 萬】喔！請核對完整發票號碼是否有對中：{g_prize}"
            
        # 檢查頭獎
        for grand in grand_prizes:
            if user_num == grand[-3:]:
                return f"🎉 恭喜對中【頭獎末三碼】，至少有 200 元小獎入帳！這組頭獎完整號碼是：{grand}"
                
        return "😭 殘念！這組末三碼沒有對中任何獎項，再接再厲！"
    except Exception as e:
        return f"對獎計算時發生錯誤: {e}"

# 3. 接收 Dialogflow 語意大腦傳過來的 Webhook 主要入口
@app.route('/', methods=['POST'])
def webhook():
    # 接收從 Dialogflow 傳過來的 JSON 資料
    req = request.get_json(silent=True, force=True)
    
    try:
        query_result = req.get('queryResult')
        parameters = query_result.get('parameters', {})
        
        # 撈取我們在 Dialogflow 設定的引數：user_number
        raw_number = parameters.get('user_number')
        if raw_number is not None:
            # 確保數字為三位數字串（去除浮點數並在前面補0）
            user_num = str(int(float(raw_number))).zfill(3)
            
            # 啟動財政部網頁爬蟲
            invoice_list = get_invoice_numbers()
            
            # 開始自動對獎並取得結果文字
            reply_text = check_prize(user_num, invoice_list)
        else:
            reply_text = "發票機器人聽不太懂唷，請直接輸入要對獎的發票末三碼數字（例如：123）。"
            
    except Exception as e:
        reply_text = f"伺服器處理錯誤: {e}"

    # 包裝成 Dialogflow 規範的 JSON 格式回傳
    response = {
        "fulfillmentText": reply_text
    }
    
    return jsonify(response)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)