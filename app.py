import os
from flask import Flask, request, abort, send_file
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageSendMessage
from linebot.exceptions import InvalidSignatureError
import requests
from tapo import ApiClient
import google.generativeai as genai  # Gemini API
from PIL import Image

# ====環境變數====
CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN", "")
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TAPO_USER = os.getenv("TAPO_USER", "")
TAPO_PASSWORD = os.getenv("TAPO_PASSWORD", "")
TAPO_IP = os.getenv("TAPO_IP", "")  # 攝影機 IP
LAMP_IP = os.getenv("LAMP_IP", "")  # 燈具 IP
PLUG_IP = os.getenv("PLUG_IP", "")  # 插座 IP
OPENWEATHER_API = os.getenv("OPENWEATHER_API", "")

for k in [CHANNEL_ACCESS_TOKEN, CHANNEL_SECRET, GEMINI_API_KEY, TAPO_USER, TAPO_PASSWORD, TAPO_IP, OPENWEATHER_API]:
    if not k:
        raise RuntimeError("必填環境變數未設定：請確認 .env 設定妥當！")

app = Flask(__name__)
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)
genai.configure(api_key=GEMINI_API_KEY)
api = ApiClient(TAPO_USER, TAPO_PASSWORD)

# ====家電指令====
def tapo_action(action):
    results = []
    def ctrl(ip, cmd):
        device = api.child(ip)
        if cmd == "snapshot":
            snap = device.get_snapshot()
            with open("snapshot.jpg", "wb") as f:
                f.write(snap)
            return "已拍照"
        elif cmd == "on":
            device.turn_on()
            return "開啟"
        elif cmd == "off":
            device.turn_off()
            return "關閉"
        elif cmd == "left":
            device.motor.left()
            return "往左"
        elif cmd == "right":
            device.motor.right()
            return "往右"
        elif cmd == "up":
            device.motor.up()
            return "上"
        elif cmd == "down":
            device.motor.down()
            return "下"
        elif cmd.startswith("goto_preset_"):
            idx = int(cmd.split("_")[-1])
            device.go_to_preset(idx)
            return f"到預設點{idx}"
        return "未支援"

    # 多指令語法如 right+snapshot / on+snapshot
    for act in action.split('+'):
        if act in ["snapshot", "left", "right", "up", "down"] or act.startswith("goto_preset_"):
            results.append(ctrl(TAPO_IP, act))
        elif act in ["on", "off"]:
            # 根據內容自動切換燈具/插座
            if "lamp" in action.lower():
                results.append(f"燈:{ctrl(LAMP_IP, act)}")
            elif "plug" in action.lower():
                results.append(f"插座:{ctrl(PLUG_IP, act)}")
            else:
                results.append(f"插座:{ctrl(PLUG_IP, act)}")
        else:
            results.append("指令未支援")
    return "; ".join(results)

# ====偵測快照亮度變通====
def check_snapshot_brightness(img_path="snapshot.jpg", threshold=50):
    try:
        img = Image.open(img_path).convert("L")
        avg = sum(img.getdata()) / (img.width * img.height)
        return avg > threshold
    except:
        return True

def tapo_action_with_light_fallback(action):
    result = tapo_action(action)
    if "snapshot" in action:
        if not check_snapshot_brightness("snapshot.jpg"):
            tapo_action("on")
            tapo_action("snapshot")
            result += "︱太暗自動開燈重拍"
    return result

# ====Gemini全能理解（贈送日常模組）====
def smart_home_ai(user_msg):
    sys_prompt = """
你是台灣用戶的智慧助理，能處理家電控制、購物、安排行程、查天氣等日常事務。
遇到家電操作請分析底層指令(如 snapshot, left, lamp+on)，遇網購請直接幫忙在momo蝦皮PChomeYahoo博客來搜尋、回傳最適品項的網址。
安排行程請列出建議，並給Google日曆新增事件相關提示網址。
查天氣自動根據台灣地區、以用戶預設地(清水區、台中市)。
能根據場景自動判斷，如環境太暗會先開燈再拍照，回傳相關結果、圖檔或網址。
這裡是LINE Bot，請回格式：{"type":"device/shopping/calendar/weather", "cmd":"家電指令", "urls":[購物或網址], "reply":"你想講的話"}，不要用繁瑣描述，直接給最有用內容。
"""
    model = genai.GenerativeModel("gemini-pro")
    response = model.generate_content([sys_prompt, user_msg])
    import json
    try:
        return json.loads(response.text)
    except:
        return {"type":"unknown", "reply":response.text}

# ====台灣天氣查詢====
def weather_func(loc="台中市清水區"):
    url = f"https://api.openweathermap.org/data/2.5/weather?q={loc}&appid={OPENWEATHER_API}&lang=zh_tw&units=metric"
    r = requests.get(url).json()
    if "main" in r:
        text = f"{loc} 天氣：{r['weather'][0]['description']} 溫度: {r['main']['temp']}°C 濕度: {r['main']['humidity']}%"
    else:
        text = "查詢失敗"
    return text

# ====Google行事曆引導====
def calendar_func(plan):
    return f"請至 https://calendar.google.com/calendar/r/eventedit 填入: {plan}"

# ====全台購物搜尋====
def shopping_func(keyword):
    base_urls = {
        "momo": f"https://www.momoshop.com.tw/mosearch/{keyword}.html",
        "pchome": f"https://ecshweb.pchome.com.tw/search/v3.3/all/results?q={keyword}",
        "shopee": f"https://shopee.tw/search?keyword={keyword}",
        "yahoo": f"https://tw.buy.yahoo.com/search/product?p={keyword}",
        "books": f"https://search.books.com.tw/search/query/key/{keyword}/cat/all",
    }
    reply = [f"{k}: {v}" for k, v in base_urls.items()]
    return reply

# ====LINE主進程====
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature","")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    user_msg = event.message.text.strip()
    ai_struct = smart_home_ai(user_msg)
    # device
    if ai_struct.get("type", "") == "device":
        reply_info = tapo_action_with_light_fallback(ai_struct.get("cmd", ""))
        items = [TextSendMessage(text=ai_struct.get("reply",""))]
        # 傳圖片
        if "snapshot" in ai_struct.get("cmd",""):
            img_url = "https://你的靜態主機/snapshot.jpg"  # 如開放 Render 靜態
            items.append(ImageSendMessage(original_content_url=img_url, preview_image_url=img_url))
        line_bot_api.reply_message(event.reply_token, items)
    # shopping
    elif ai_struct.get("type", "") == "shopping":
        reply_list = shopping_func(ai_struct.get("cmd", user_msg))
        items = [TextSendMessage(text=ai_struct.get("reply",""))] + [TextSendMessage(text="\n".join(reply_list))]
        line_bot_api.reply_message(event.reply_token, items)
    # calendar
    elif ai_struct.get("type", "") == "calendar":
        link = calendar_func(ai_struct.get("cmd", user_msg))
        items = [TextSendMessage(text=ai_struct.get("reply","")), TextSendMessage(text=link)]
        line_bot_api.reply_message(event.reply_token, items)
    # weather
    elif ai_struct.get("type", "") == "weather":
        wtxt = weather_func(ai_struct.get("cmd","台中市清水區"))
        items = [TextSendMessage(text=ai_struct.get("reply","")), TextSendMessage(text=wtxt)]
        line_bot_api.reply_message(event.reply_token, items)
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=ai_struct.get("reply","無法判斷需求")))

# ====讓 Render 可以靜態取 snapshot====
@app.route("/snapshot.jpg")
def send_img():
    return send_file("snapshot.jpg", mimetype="image/jpeg")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
