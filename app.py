from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageSendMessage
import os

app = Flask(__name__)

# 從 Render (或 Heroku) 設定的環境變數取得金鑰 —— 只寫一次即可
CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN", "")
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET", "")

if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
    raise RuntimeError("請設定環境變數 CHANNEL_ACCESS_TOKEN 與 CHANNEL_SECRET")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# LINE Webhook 入口
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    print("LINE Webhook event:", body)  # debug
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

# 處理用戶傳來的訊息
@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    text = event.message.text.strip().lower()
    
    if text == "指令" or text == "help":
        reply = "可用指令：\n- 狀態\n- 監控（會回一張圖）\n- 開燈\n- 關燈\n- 溫度"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        
    elif text == "狀態":
        reply = "家中狀態：客廳燈關、門窗關、溫度26.3°C（示範）"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        
    elif text == "監控":
        img_url = "https://placekitten.com/640/360"   # 這裡以後再換你的監控快照網址！
        line_bot_api.reply_message(
            event.reply_token,
            ImageSendMessage(
                original_content_url=img_url,
                preview_image_url=img_url
            )
        )
        
    elif text == "開燈":
        reply = "已開燈（示範）"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        
    elif text == "關燈":
        reply = "已關燈（示範）"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        
    elif text == "溫度":
        reply = "目前室溫：26.3°C（示範）"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
        
    else:
        reply = f"你說：{event.message.text}\n輸入「指令」可看全部可用指令"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
