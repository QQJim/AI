部署步驟：

把這個資料夾變成 GitHub 專案（建立 repo，上傳 app.py、requirements.txt、Procfile、README.txt）

到 Render.com -> New -> Web Service -> 連 GitHub，選這個專案

設定環境變數：

CHANNEL_ACCESS_TOKEN（從 LINE Developer Console 的 Messaging API 頁面取得）

CHANNEL_SECRET（從 Basic settings 頁面）

Deploy 完成後取得你的網站網址，例如：https://xxxx.onrender.com

到 LINE Developer Console -> Messaging API -> Webhook URL 填 https://xxxx.onrender.com/callback -> 打開 Use webhook

用手機加你的 Bot 為好友（掃 QR Code），在 LINE 輸入「指令」測試
