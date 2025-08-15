from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageSendMessage
import requests
import openai
import os

# LINE/OPENAI config
app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN", "")
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MAC_SERVER_URL = ("http://172.23.204.137:8711", "")  

if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET or not OPENAI_API_KEY or not MAC_SERVER_URL:
    raise RuntimeError("環境變數: CHANNEL_ACCESS_TOKEN, CHANNEL_SECRET, OPENAI_API_KEY, MAC_SERVER_URL 必填！")

line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)
openai.api_key = OPENAI_API_KEY

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
    user_msg = event.message.text.strip()
    prompt = (
        "你是智能家居助理，能控制攝影機（snapshot/left/right/up/down/goto_preset_1~8），"
        "判斷指令後只回英文格式如'snapshot', 'right+snapshot', 'goto_preset_2+snapshot'。"
        "（不需回中文描述）\n\n用戶訊息: " + user_msg
    )
    try:
        gpt_rsp = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": prompt}]
        ).choices[0].message.content.strip().lower()
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="AI理解錯誤：" + str(e)))
        return
    # call Mac 伺服器做抓圖動作
    try:
        act_rsp = requests.post(f"{MAC_SERVER_URL}/yolo_action", json={"action": gpt_rsp}, timeout=30)
        resj = act_rsp.json()
        desc = resj.get("desc", "描述取得失敗")
        img_url = f"{MAC_SERVER_URL}/snapshot.jpg"
        msg = f"AI解讀：{gpt_rsp}\n{desc}"
        line_bot_api.reply_message(event.reply_token, [
            TextSendMessage(text=msg),
            ImageSendMessage(
                original_content_url=img_url,
                preview_image_url=img_url
            )
        ])
    except Exception as e:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"執行失敗: {str(e)}"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
