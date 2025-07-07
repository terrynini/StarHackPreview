import os
import requests
import json
import html

# 從 GitHub Secrets 讀取環境變數
TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')

# 檢查 Secrets 是否成功載入
if not TOKEN or not CHANNEL_ID:
    print("錯誤：請在 GitHub Repository 的 Settings -> Secrets 中設定 DISCORD_TOKEN 和 DISCORD_CHANNEL_ID")
    exit(1)

# Discord API 的 URL
URL = f"https://discord.com/api/v9/channels/{CHANNEL_ID}/messages?limit=50" # 抓取最近 50 則訊息

# 設定請求標頭，包含 Bot 的授權權杖
headers = {
    "Authorization": f"Bot {TOKEN}"
}

# 發送 GET 請求
try:
    response = requests.get(URL, headers=headers, timeout=10)
    response.raise_for_status()  # 如果狀態碼不是 2xx，則拋出異常
except requests.exceptions.RequestException as e:
    print(f"讀取 Discord API 時發生錯誤: {e}")
    exit(1)

html_content = "<h1>從 Discord 來的最新討論</h1>\n"

messages = response.json()
# 將訊息從舊到新排序
messages.reverse()

for msg in messages:
    # 忽略沒有內容的訊息
    if not msg['content']:
        continue

    author = html.escape(msg['author']['username'])
    # 將訊息內容中的換行符號轉換為 <br>
    content = html.escape(msg['content']).replace('\n', '<br>')
    
    # 簡單的 HTML 格式化
    html_content += f'<div><strong>{author}</strong>: <p>{content}</p></div>\n<hr>\n'

# 讀取 HTML 模板
try:
    with open('template.html', 'r', encoding='utf-8') as f:
        template = f.read()
except FileNotFoundError:
    print("錯誤：找不到 template.html 檔案。")
    exit(1)

# 將抓到的內容替換掉模板中的佔位符
final_html = template.replace('<!-- DISCORD_MESSAGES -->', html_content)

# 將最終的 HTML 寫入 index.html
with open('index.html', 'w', encoding='utf-8') as f:
    f.write(final_html)

print("index.html 已經成功產生！")
