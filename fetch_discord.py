import os
import requests
import html
import time

# 從 GitHub Secrets 讀取環境變數
TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = os.getenv('DISCORD_CHANNEL_ID')
INVITE_LINK = os.getenv('DISCORD_INVITE_LINK')

# 設定要抓取的最大貼文數量 (用於主頁面)
MAX_POSTS_TO_FETCH = 15 

# 設定 CTF 評價標籤的名稱
CTF_TAG_NAME = "CTF評價"

# 檢查 Secrets 是否成功載入
if not TOKEN or not CHANNEL_ID:
    print("錯誤：請在 GitHub Repository 的 Settings -> Secrets 中設定 DISCORD_TOKEN 和 DISCORD_CHANNEL_ID")
    exit(1)

headers = {
    "Authorization": f"Bot {TOKEN}"
}

def fetch_first_message_content(thread_id):
    """獲取指定貼文的第一則訊息內容。"""
    messages_url = f"https://discord.com/api/v9/channels/{thread_id}/messages?limit=1"
    try:
        msg_response = requests.get(messages_url, headers=headers, timeout=5)
        msg_response.raise_for_status()
        messages = msg_response.json()
        if messages:
            return messages[0].get('content', '')
    except requests.exceptions.RequestException as e:
        print(f"獲取貼文 {thread_id} 的訊息時出錯: {e}")
    return None

def get_forum_channel_details(channel_id):
    """獲取論壇頻道詳細資訊，包括標籤。"""
    url = f"https://discord.com/api/v9/channels/{channel_id}"
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"獲取頻道詳細資訊時發生錯誤: {e}")
        return None

def get_threads(channel_id, thread_type="active", limit=None):
    """獲取活躍或封存的貼文。"""
    if thread_type == "active":
        url = f"https://discord.com/api/v9/channels/{channel_id}/threads/active"
    elif thread_type == "archived":
        url = f"https://discord.com/api/v9/channels/{channel_id}/threads/archived/public?limit={limit if limit else 100}"
    else:
        return []

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json().get('threads', [])
    except requests.exceptions.RequestException as e:
        print(f"獲取 {thread_type} 貼文時發生錯誤: {e}")
        return []

def generate_post_html(title, summary, invite_link):
    """生成單個貼文的 HTML 片段。"""
    html_snippet = f"""
    <div class="post">
        <h3>{title}</h3>
        <p>{summary}</p>
    """
    
    if invite_link:
        html_snippet += f'<a href="{invite_link}" target="_blank" rel="noopener noreferrer">點此加入社群參與討論 &raquo;</a>'
        
    html_snippet += "</div>\n"
    return html_snippet

def write_html_file(filename, content, page_title):
    """將內容寫入 HTML 檔案。"""
    try:
        with open('template.html', 'r', encoding='utf-8') as f:
            template = f.read()
    except FileNotFoundError:
        print("錯誤：找不到 template.html 檔案。")
        exit(1)

    # 替換標題和內容
    final_html = template.replace('<!-- PAGE_TITLE -->', page_title)
    final_html = final_html.replace('<!-- DISCORD_MESSAGES -->', content)

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(final_html)

# --- 主執行邏輯 ---

# 1. 獲取論壇頻道詳細資訊以找到 CTF 標籤 ID
forum_details = get_forum_channel_details(CHANNEL_ID)
ctf_tag_id = None
if forum_details and 'available_tags' in forum_details:
    for tag in forum_details['available_tags']:
        if tag['name'] == CTF_TAG_NAME:
            ctf_tag_id = tag['id']
            break

if ctf_tag_id is None:
    print(f"警告：找不到名為 '{CTF_TAG_NAME}' 的標籤。CTF 評價頁面將不會生成。")

# 2. 獲取活躍和封存的貼文
active_threads = get_threads(CHANNEL_ID, "active")
time.sleep(0.5) # 避免速率限制
archived_threads = get_threads(CHANNEL_ID, "archived", limit=MAX_POSTS_TO_FETCH * 2) # 抓多一點以確保有足夠的最新貼文
time.sleep(0.5) # 避免速率限制

# 3. 合併並去重所有貼文
all_unique_threads = {}
for thread in active_threads + archived_threads:
    all_unique_threads[thread['id']] = thread

# 4. 根據創建時間排序 (通常 id 越大代表越新)
# 或者可以根據 'last_message_id' 或 'archive_timestamp' 排序，但 'id' 最簡單且通常足夠
sorted_threads = sorted(all_unique_threads.values(), key=lambda x: int(x['id']), reverse=True)

# 5. 篩選出最新的貼文和 CTF 貼文
latest_threads = []
ctf_threads = []

for thread in sorted_threads:
    # 檢查是否為 CTF 貼文
    if ctf_tag_id and 'applied_tags' in thread and ctf_tag_id in thread['applied_tags']:
        ctf_threads.append(thread)
    
    # 收集最新的貼文 (用於主頁面)
    if len(latest_threads) < MAX_POSTS_TO_FETCH:
        latest_threads.append(thread)

# --- 生成主頁面 (index.html) ---
html_content_main = ""
for thread in latest_threads:
    content = fetch_first_message_content(thread['id'])
    if content is None: # API 請求失敗
        continue

    summary_limit = 120
    if content:
        summary = html.escape(content[:summary_limit]).replace('\n', '<br>') + '...'
    else:
        summary = "<i>(此貼文無內文)</i>"
    
    html_content_main += generate_post_html(html.escape(thread['name']), summary, INVITE_LINK)
    time.sleep(0.2) # 每次獲取訊息後稍微延遲

if not html_content_main:
    html_content_main = "<p>目前還沒有任何討論，快來發表第一篇吧！</p>"

write_html_file('index.html', html_content_main, "社群討論精華")
print("index.html 已成功根據論壇內容產生！")

# --- 生成 CTF 評價頁面 (ctf_reviews.html) ---
if ctf_tag_id:
    html_content_ctf = ""
    for thread in ctf_threads:
        content = fetch_first_message_content(thread['id'])
        if content is None:
            continue

        summary_limit = 120
        if content:
            summary = html.escape(content[:summary_limit]).replace('\n', '<br>') + '...'
        else:
            summary = "<i>(此貼文無內文)</i>"
        
        html_content_ctf += generate_post_html(html.escape(thread['name']), summary, INVITE_LINK)
        time.sleep(0.2) # 每次獲取訊息後稍微延遲

    if not html_content_ctf:
        html_content_ctf = "<p>目前還沒有任何 CTF 評價貼文。</p>"

    write_html_file('ctf_reviews.html', html_content_ctf, "CTF 評價")
    print("ctf_reviews.html 已成功產生！")

print("所有頁面生成完畢。")