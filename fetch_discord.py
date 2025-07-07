import os
import requests
import html
import time
import math

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

def get_avatar_url(user_id, avatar_hash):
    """根據用戶 ID 和頭貼 hash 生成頭貼 URL"""
    if avatar_hash:
        # 如果有自定義頭貼
        return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png"
    else:
        # 如果是預設頭貼 (新版 Discord 用戶沒有 discriminator)
        # Discord 預設頭貼現在是基於用戶 ID 的 hash，但對於嵌入式頭貼，通常會用一個通用的預設圖
        return f"https://cdn.discordapp.com/embed/avatars/0.png" # 預設使用 0 號頭貼

def fetch_initial_post_data(thread_id, guild_id):
    """獲取指定論壇貼文的初始貼文內容、作者資訊、伺服器暱稱及反應。"""
    # 論壇貼文的 ID 就是其初始貼文的訊息 ID
    message_url = f"https://discord.com/api/v9/channels/{thread_id}/messages/{thread_id}"
    try:
        msg_response = requests.get(message_url, headers=headers, timeout=5)
        msg_response.raise_for_status()
        message = msg_response.json() # 這會直接回傳單個訊息物件，而不是列表
        content = message.get('content', '')
        author = message.get('author', {})
        reactions = message.get('reactions', []) # 獲取 reactions 數據

        # --- 獲取伺服器暱稱 ---
        # 預設使用原始作者的 username，這是最基本的保證
        author_name_to_display = author.get('username', '未知作者') 

        if 'id' in author and guild_id: # 確保有用戶 ID 和伺服器 ID
            member_url = f"https://discord.com/api/v9/guilds/{guild_id}/members/{author['id']}"
            try:
                member_response = requests.get(member_url, headers=headers, timeout=5)
                member_response.raise_for_status()
                member_data = member_response.json()
                
                # 優先使用暱稱 (nick)
                if member_data.get('nick'):
                    author_name_to_display = member_data['nick']
                # 其次使用成員資料中的 global_name (嵌套在 user 物件下)
                elif member_data.get('user', {}).get('global_name'):
                    author_name_to_display = member_data['user']['global_name']
                # 最後使用原始作者資料中的 global_name
                elif author.get('global_name'):
                    author_name_to_display = author['global_name']
                # 如果以上都沒有，則保持原來的 username

            except requests.exceptions.RequestException as e:
                # 如果獲取成員資訊失敗，可能是 Bot 沒有權限，或者用戶已不在伺服器
                print(f"警告：獲取用戶 {author.get('id')} 在伺服器 {guild_id} 的成員資訊失敗: {e}")
            time.sleep(0.1) # 每次獲取成員資訊後稍微延遲

        return content, author, author_name_to_display, reactions
    except requests.exceptions.RequestException as e:
        print(f"獲取初始貼文 {thread_id} 的訊息時出錯: {e}")
    return None, None, None, None # Return None for all if failed

def calculate_star_rating(reactions):
    """根據反應計算平均星級評分。"""
    star_emoji_map = {
        '1️⃣': 1,
        '2️⃣': 2,
        '3️⃣': 3,
        '4️⃣': 4,
        '5️⃣': 5,
    }
    total_score = 0
    total_votes = 0

    for reaction in reactions:
        emoji_name = reaction['emoji']['name']
        count = reaction['count']
        if emoji_name in star_emoji_map:
            total_score += star_emoji_map[emoji_name] * count
            total_votes += count
    
    if total_votes > 0:
        return total_score / total_votes
    return 0

def render_stars(average_rating):
    """將平均分數轉換為 HTML 星級圖案。"""
    filled_star = '★'
    empty_star = '☆'
    # 將平均分數四捨五入到最接近的整數，然後生成星星
    num_filled = round(average_rating)
    return f"<span class=\"star-rating\">{filled_star * num_filled}{empty_star * (5 - num_filled)}</span>"

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

def generate_post_html(title, summary, invite_link, author_display_name, author_avatar_url, tags_html, star_rating_html=""):
    """生成單個貼文的 HTML 片段。"""
    html_snippet = f"""
    <div class="post-card">
        <div class="post-header">
            <img src="{author_avatar_url}" alt="{author_display_name}'s avatar" class="author-avatar">
            <span class="author-name">{author_display_name}</span>
        </div>
        <h3>{title}</h3>
        <p>{summary}</p>
        {star_rating_html} <!-- 新增星級評分 -->
        {tags_html}
    """
    
    if invite_link:
        html_snippet += f'<a href="{invite_link}" target="_blank" rel="noopener noreferrer" class="join-link">點此加入社群參與討論 &raquo;</a>'
        
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

# 1. 獲取論壇頻道詳細資訊以找到 CTF 標籤 ID 和所有標籤映射
forum_details = get_forum_channel_details(CHANNEL_ID)
ctf_tag_id = None
tag_map = {}
forum_guild_id = None

if forum_details:
    forum_guild_id = forum_details.get('guild_id')
    if 'available_tags' in forum_details:
        for tag in forum_details['available_tags']:
            tag_map[tag['id']] = tag['name']
            if tag['name'] == CTF_TAG_NAME:
                ctf_tag_id = tag['id']

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
    content, author_data, author_display_name, reactions = fetch_initial_post_data(thread['id'], forum_guild_id)
    if content is None and author_data is None: # API 請求失敗
        continue

    summary_limit = 120
    if content:
        summary = html.escape(content[:summary_limit]).replace('\n', '<br>') + '...'
    else:
        summary = "<i>(此貼文無內文)</i>"
    
    author_id = author_data.get('id')
    avatar_hash = author_data.get('avatar')
    author_avatar_url = get_avatar_url(author_id, avatar_hash)

    thread_tags_html = ""
    if 'applied_tags' in thread and tag_map:
        tags_list = []
        for tag_id in thread['applied_tags']:
            if tag_id in tag_map:
                tags_list.append(tag_map[tag_id])
        if tags_list:
            thread_tags_html = '<div class="tags-container">'
            for tag_name in tags_list:
                thread_tags_html += f'<span class="tag-item">{html.escape(tag_name)}</span>'
            thread_tags_html += '</div>'

    # CTF 評價的星級評分只在 CTF 頁面顯示，主頁面不顯示
    star_rating_html = ""

    html_content_main += generate_post_html(
        html.escape(thread['name']),
        summary,
        INVITE_LINK,
        author_display_name,
        author_avatar_url,
        thread_tags_html,
        star_rating_html
    )
    time.sleep(0.2) # 每次獲取訊息後稍微延遲

if not html_content_main:
    html_content_main = "<p>目前還沒有任何討論，快來發表第一篇吧！</p>"

write_html_file('index.html', html_content_main, "社群討論精華")
print("index.html 已成功根據論壇內容產生！")

# --- 生成 CTF 評價頁面 (ctf_reviews.html) ---
if ctf_tag_id:
    html_content_ctf = ""
    for thread in ctf_threads:
        content, author_data, author_display_name, reactions = fetch_initial_post_data(thread['id'], forum_guild_id)
        if content is None and author_data is None: # API 請求失敗
            continue

        summary_limit = 120
        if content:
            summary = html.escape(content[:summary_limit]).replace('\n', '<br>') + '...'
        else:
            summary = "<i>(此貼文無內文)</i>"
        
        author_id = author_data.get('id')
        avatar_hash = author_data.get('avatar')
        author_avatar_url = get_avatar_url(author_id, avatar_hash)

        thread_tags_html = ""
        if 'applied_tags' in thread and tag_map:
            tags_list = []
            for tag_id in thread['applied_tags']:
                if tag_id in tag_map:
                    tags_list.append(tag_map[tag_id])
            if tags_list:
                thread_tags_html = '<div class="tags-container">'
                for tag_name in tags_list:
                    thread_tags_html += f'<span class="tag-item">{html.escape(tag_name)}</span>'
                thread_tags_html += '</div>'

        # 計算並渲染星級評分
        average_rating = calculate_star_rating(reactions)
        star_rating_html = ""
        if average_rating > 0:
            star_rating_html = render_stars(average_rating)

        html_content_ctf += generate_post_html(
            html.escape(thread['name']),
            summary,
            INVITE_LINK,
            author_display_name,
            author_avatar_url,
            thread_tags_html,
            star_rating_html # 傳遞星級評分 HTML
        )
        time.sleep(0.2) # 每次獲取訊息後稍微延遲

    if not html_content_ctf:
        html_content_ctf = "<p>目前還沒有任何 CTF 評價貼文。</p>"

    write_html_file('ctf_reviews.html', html_content_ctf, "CTF 評價")
    print("ctf_reviews.html 已成功產生！")

print("所有頁面生成完畢。")