import os
import requests
import json
# 從 GitHub Secrets 讀取環境變數
TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')
# Discord API 的 URL
URL = f"https://discord.com/api/v9/channels/{CHANNEL_ID}/messages"
# 設定請求標頭，包含 Bot 的授權權杖
headers = {
    "Authorization": f"Bot {TOKEN}"
}
# 發送 GET 請求
response = requests.get(URL, headers=headers)
html_content = "<h1>從 Discord 來的最新消息</h1>\n"
if response.status_code == 200:
    messages = response.json()
    # 將訊息轉換成 HTML (這裡只取前 10 則)
    for msg in messages[:10]:
        author = msg['author']['username']
        content = msg['content']
        # 簡單的 HTML 格式化
        html_content += f'<div><strong>{author}</strong>: <p>{content}
</p></div>\n<hr>\n'
else:
    html_content += "<p>讀取訊息失敗！</p>"
    print(f"Error: {response.status_code}, {response.text}")
# 讀取 HTML 模板
with open('template.html', 'r', encoding='utf-8') as f:
    template = f.read()
# 將抓到的內容替換掉模板中的佔位符
final_html = template.replace('<!-- DISCORD_MESSAGES -->', html_content)
# 將最終的 HTML 寫入 index.html
with open('index.html', 'w', encoding='utf-8') as f:
    f.write(final_html)
print("index.html 已經成功產生！")
