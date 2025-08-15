import os
import json
from flask import Flask, request, abort, send_file
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageSendMessage
from linebot.exceptions import InvalidSignatureError
import requests
import google.generativeai as genai
from PIL import Image

# ====環境變數====
CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN", "")
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TAPO_USER = os.getenv("TAPO_USER", "")
TAPO_PASSWORD = os.getenv("TAPO_PASSWORD", "")
TAPO_IP = os.getenv("TAPO_IP", "")
LAMP_IP = os.getenv("LAMP_IP", "")
PLUG_IP = os.getenv("PLUG_IP", "")
OPENWEATHER_API = os.getenv("OPENWEATHER_API", "")

# 檢查必填環境變數
required_vars = [CHANNEL_ACCESS_TOKEN, CHANNEL_SECRET, GEMINI_API_KEY]
if not all(required_vars):
    raise RuntimeError("必填環境變數未設定：CHANNEL_ACCESS_TOKEN, CHANNEL_SECRET, GEMINI_API_KEY")

app = Flask(__name__)
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# 初始化 Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# ====家電控制====
def tapo_action(action):
    """控制 Tapo 設備"""
    if not all([TAPO_USER, TAPO_PASSWORD, TAPO_IP]):
        return "Tapo 設備未設定"
    
    try:
        from tapo import ApiClient
        api = ApiClient(TAPO_USER, TAPO_PASSWORD)
        results = []
        
        def ctrl(ip, cmd):
            if not ip:
                return "設備IP未設定"
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
            return "未支援指令"

        # 處理複合指令
        for act in action.split('+'):
            if act in ["snapshot", "left", "right", "up", "down"] or act.startswith("goto_preset_"):
                results.append(ctrl(TAPO_IP, act))
            elif act in ["on", "off"]:
                if "lamp" in action.lower():
                    results.append(f"燈:{ctrl(LAMP_IP, act)}")
                elif "plug" in action.lower():
                    results.append(f"插座:{ctrl(PLUG_IP, act)}")
                else:
                    results.append(f"插座:{ctrl(PLUG_IP, act)}")
            else:
                results.append(f"未知指令:{act}")
        
        return "; ".join(results)
    except Exception as e:
        return f"設備控制錯誤: {str(e)}"

def check_snapshot_brightness(img_path="snapshot.jpg", threshold=50):
    """檢查快照亮度"""
    try:
        img = Image.open(img_path).convert("L")
        avg = sum(img.getdata()) / (img.width * img.height)
        return avg > threshold
    except:
        return True

def tapo_action_with_light_fallback(action):
    """帶亮度自動補償的設備控制"""
    result = tapo_action(action)
    if "snapshot" in action and "已拍照" in result:
        if not check_snapshot_brightness("snapshot.jpg"):
            lamp_result = tapo_action("on")
            snapshot_result = tapo_action("snapshot")
            result += f" | 太暗自動開燈重拍: {lamp_result}, {snapshot_result}"
    return result

# ====AI智能理解====
def smart_home_ai(user_msg):
    """使用 Gemini 理解用戶意圖"""
    if not GEMINI_API_KEY:
        return {"type": "unknown", "reply": "AI服務未設定"}
    
    sys_prompt = """
你是台灣用戶的智慧助理，處理家電控制、購物、行程、天氣等需求。
回傳 JSON 格式：{"type":"device/shopping/calendar/weather", "cmd":"具體指令", "reply":"回覆訊息"}

家電指令：snapshot(拍照), left/right/up/down(移動), on/off(開關), goto_preset_1~8(預設點)
購物：搜尋台灣購物網站
行程：Google日曆建議
天氣：台灣地區天氣查詢

範例：
輸入："拍個照" -> {"type":"device", "cmd":"snapshot", "reply":"正在拍照..."}
輸入："買牛奶" -> {"type":"shopping", "cmd":"牛奶", "reply":"為您搜尋牛奶商品"}
"""
    
    try:
        model = genai.GenerativeModel("gemini-pro")
        response = model.generate_content([sys_prompt, user_msg])
        return json.loads(response.text.strip())
    except json.JSONDecodeError:
        return {"type": "unknown", "reply": f"AI回覆：{response.text if 'response' in locals() else user_msg}"}
    except Exception as e:
        return {"type": "unknown", "reply": f"AI處理錯誤: {str(e)}"}

# ====其他功能====
def weather_func(loc="台中市清水區"):
    """查詢天氣"""
    if not OPENWEATHER_API:
        return "天氣服務未設定"
    
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={loc}&appid={OPENWEATHER_API}&lang=zh_tw&units=metric"
        r = requests.get(url, timeout=5).json()
        if "main" in r:
            return f"{loc} 天氣：{r['weather'][0]['description']} 溫度: {r['main']['temp']}°C 濕度: {r['main']['humidity']}%"
        else:
            return "天氣查詢失敗"
    except:
        return "天氣服務暫時無法使用"

def calendar_func(plan):
    """行程安排建議"""
    return f"請至 Google 日曆新增：{plan}\n網址: https://calendar.google.com/calendar/r/eventedit"

def shopping_func(keyword):
    """購物搜尋"""
    base_urls = {
        "momo": f"https://www.momoshop.com.tw/mosearch/{keyword}.html",
        "pchome": f"https://ecshweb.pchome.com.tw/search/v3.3/all/results?q={keyword}",
        "shopee": f"https://shopee.tw/search?keyword={keyword}",
        "yahoo": f"https://tw.buy.yahoo.com/search/product?p={keyword}",
        "books": f"https://search.books.com.tw/search/query/key/{keyword}/cat/all",
    }
    return [f"{k}: {v}" for k, v in base_urls.items()]

# ====Flask 路由====
@app.route("/", methods=["GET"])
def home():
    return "AI Smart Home Bot is running!"

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

@app.route("/snapshot.jpg")
def send_img():
    try:
        return send_file("snapshot.jpg", mimetype="image/jpeg")
    except:
        abort(404)

@handler.add(MessageEvent, message=TextMessage)
def handle_text(event):
    """處理文字訊息"""
    try:
        user_msg = event.message.text.strip()
        print(f"收到訊息: {user_msg}")
        
        # 測試指令
        if user_msg == "測試":
            line_bot_api.reply_message(
                event.reply_token, 
                TextSendMessage(text="Bot 運作正常！✅")
            )
            return
        
        # AI 理解用戶意圖
        ai_struct = smart_home_ai(user_msg)
        task_type = ai_struct.get("type", "unknown")
        
        # 處理不同類型的任務
        if task_type == "device":
            # 家電控制
            cmd = ai_struct.get("cmd", "")
            result = tapo_action_with_light_fallback(cmd)
            
            messages = [TextSendMessage(text=f"{ai_struct.get('reply', '')} \n結果: {result}")]
            
            # 如果有拍照，嘗試發送圖片
            if "snapshot" in cmd and "已拍照" in result:
                try:
                    img_url = f"https://{request.host}/snapshot.jpg"
                    messages.append(ImageSendMessage(
                        original_content_url=img_url, 
                        preview_image_url=img_url
                    ))
                except:
                    pass
            
            line_bot_api.reply_message(event.reply_token, messages)
            
        elif task_type == "shopping":
            # 購物搜尋
            keyword = ai_struct.get("cmd", user_msg)
            urls = shopping_func(keyword)
            
            messages = [
                TextSendMessage(text=ai_struct.get("reply", "")),
                TextSendMessage(text="\n".join(urls))
            ]
            line_bot_api.reply_message(event.reply_token, messages)
            
        elif task_type == "calendar":
            # 行程安排
            plan = ai_struct.get("cmd", user_msg)
            calendar_info = calendar_func(plan)
            
            messages = [
                TextSendMessage(text=ai_struct.get("reply", "")),
                TextSendMessage(text=calendar_info)
            ]
            line_bot_api.reply_message(event.reply_token, messages)
            
        elif task_type == "weather":
            # 天氣查詢
            location = ai_struct.get("cmd", "台中市清水區")
            weather_info = weather_func(location)
            
            messages = [
                TextSendMessage(text=ai_struct.get("reply", "")),
                TextSendMessage(text=weather_info)
            ]
            line_bot_api.reply_message(event.reply_token, messages)
            
        else:
            # 未知指令
            line_bot_api.reply_message(
                event.reply_token, 
                TextSendMessage(text=ai_struct.get("reply", "抱歉，我不太理解您的需求"))
            )
            
    except Exception as e:
        print(f"處理錯誤: {e}")
        try:
            line_bot_api.reply_message(
                event.reply_token, 
                TextSendMessage(text="系統處理中發生錯誤，請稍後再試")
            )
        except:
            pass

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
