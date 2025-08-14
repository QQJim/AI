from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os
app = Flask(name)
CHANNEL_ACCESS_TOKEN = os.getenv("d8GK+ttA8ZeWjoAQK4ovyRSrilxt8Hwwua3lhEt8oFPZJApBaU/tF+iUbnigrWP9mNuaPSIJl0KoW+zKyRmEj5qzz90t5xwwf08UqVtD8qhNpbGX9aA4xI00Rvy1zjtURrMQPren4SS2xl9HLMqd/gdB04t89/1O/w1cDnyilFU=", "")
CHANNEL_SECRET = os.getenv("60333a4cb313d06854e23aad76883668", "")
if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
raise RuntimeError("請設定環境變數 CHANNEL_ACCESS_TOKEN 與 CHANNEL_SECRET")
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)
@app.route("/callback", methods=["POST"])
def callback():
signature = request.headers.get("X-Line-Signature", "")
body = request.get_data(as_text=True)
try:
handler.handle(body, signature)
except InvalidSignatureError:
abort(400)
return "OK"
@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
text = event.message.text.strip().lower()
# 最簡單的幾個指令
if text in ["help", "指令"]:
reply = "可用指令：狀態、監控、開燈、關燈、溫度"
elif text in ["狀態"]:
reply = "家中狀態：客廳燈關、門窗關、溫度26.3°C（示範）"
elif text in ["監控"]:
reply = "監控畫面示範：https://placekitten.com/640/360"
elif text in ["開燈"]:
reply = "已開燈（示範）"
elif text in ["關燈"]:
reply = "已關燈（示範）"
elif text in ["溫度"]:
reply = "目前室溫：26.3°C（示範）"
else:
reply = f"你說：{event.message.text}\n輸入「指令」可看可用指令"
line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
if name == "main":
app.run(host="0.0.0.0", port=5000)
