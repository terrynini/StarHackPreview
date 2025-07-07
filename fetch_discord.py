import os
import requests
import html
import time

# 從 GitHub Secrets 讀取環境變數
TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')
INVITE_LINK = os.getenv('DISCORD_INVITE_LINK')

# 檢查 Secrets 是否成功載入
if not TOKEN or not CHANNEL_ID:
    print("錯誤：請在 GitHub Repository 的 Settings -> Secrets 中設定 DISCORD_TOKEN 和 DISCORD_CHANNEL_ID")
    exit(1)

# --- 正確的 API 端點 ---
# 1. 先獲取論壇中所有已封存的公開貼文
THREADS_URL = f"https://discord.com/api/v9/channels/{CHANNEL_ID}/threads/archived/public?limit=25" # 抓取最近 25 個貼文

headers = {
    "Authorization": f"Bot {TOKEN}"
}

def fetch_first_message(thread_id):
    """獲取指定貼文的第一則訊息"""
    messages_url = f"https://discord.com/api/v9/channels/{thread_id}/messages?limit=1"
    try:
        msg_response = requests.get(messages_url, headers=headers, timeout=5)
        msg_response.raise_for_status()
        messages = msg_response.json()
        if messages:
            return messages[0]['content']
    except requests.exceptions.RequestException as e:
        print(f"獲取貼文 {thread_id} 的訊息時出錯: {e}")
    return None

try:
    # 步驟 1: 獲取貼文列表
    response = requests.get(THREADS_URL, headers=headers, timeout=10)
    response.raise_for_status()
    data = response.json()
    threads = data.get('threads', [])
except requests.exceptions.RequestException as e:
    print(f"讀取 Discord API (獲取貼文列表) 時發生錯誤: {e}")
    exit(1)

html_content = ""

# 步驟 2: 遍歷每個貼文，獲取其主文
for thread in threads:
    title = html.escape(thread['name'])
    thread_id = thread['id']
    
    # 步驟 3: 獲取主文內容
    content = fetch_first_message(thread_id)
    
    if not content:
        continue

    # 產生摘要
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
    
    if INVITE_LINK:
        html_content += f'<a href="{INVITE_LINK}" target="_blank" rel="noopener noreferrer">點此加入社群參與討論 &raquo;</a>'
        
    html_content += "</div>\n"
    
    # 為了避免觸發 Discord 的 API 速率限制，每次請求之間稍微延遲
    time.sleep(0.5)

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
