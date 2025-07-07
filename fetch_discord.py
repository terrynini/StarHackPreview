import os
import requests
import html

# 從 GitHub Secrets 讀取環境變數
TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')
INVITE_LINK = os.getenv('DISCORD_INVITE_LINK') # 新增：讀取邀請連結

# 檢查 Secrets 是否成功載入
if not TOKEN or not CHANNEL_ID:
    print("錯誤：請在 GitHub Repository 的 Settings -> Secrets 中設定 DISCORD_TOKEN 和 DISCORD_CHANNEL_ID")
    exit(1)

if not INVITE_LINK:
    print("警告：未設定 DISCORD_INVITE_LINK，將無法顯示加入社群的連結。")

# Discord API 的 URL，用來獲取頻道中的 "訊息"
# 對於論壇頻道，這些 "訊息" 就是每個貼文的起始訊息
URL = f"https://discord.com/api/v9/channels/{CHANNEL_ID}/messages?limit=25" # 抓取最近 25 個貼文

headers = {
    "Authorization": f"Bot {TOKEN}"
}

try:
    response = requests.get(URL, headers=headers, timeout=10)
    response.raise_for_status()
except requests.exceptions.RequestException as e:
    print(f"讀取 Discord API 時發生錯誤: {e}")
    exit(1)

html_content = ""
messages = response.json()

for msg in messages:
    # 關鍵：只有論壇的起始訊息才會有 'thread' 這個 object
    if 'thread' in msg and msg['content']:
        # 提取標題
        title = html.escape(msg['thread']['name'])
        
        # 提取主文並產生摘要
        content = msg['content']
        summary_limit = 120
        if len(content) > summary_limit:
            summary = html.escape(content[:summary_limit]).replace('\n', '<br>') + '...'
        else:
            summary = html.escape(content).replace('\n', '<br>')

        # 組合 HTML
        html_content += f"""
        <div class="post">
            <h3>{title}</h3>
            <p>{summary}</p>
        """
        
        # 如果有設定邀請連結，就顯示它
        if INVITE_LINK:
            html_content += f'<a href="{INVITE_LINK}" target="_blank" rel="noopener noreferrer">點此加入社群參與討論 &raquo;</a>'
            
        html_content += "</div>\n"

if not html_content:
    html_content = "<p>目前還沒有任何討論，快來發表第一篇吧！</p>"

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

print("index.html 已成功根據論壇內容產生！")