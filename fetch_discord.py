import os
import requests
import html
import time
import math
import datetime
import pytz
import re

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

# 快取頻道名稱，避免重複請求
channel_name_cache = {}

def get_avatar_url(user_id, avatar_hash):
    """根據用戶 ID 和頭貼 hash 生成頭貼 URL"""
    if avatar_hash:
        # 如果有自定義頭貼
        return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png"
    else:
        # 如果是預設頭貼 (新版 Discord 用戶沒有 discriminator)
        return f"https://cdn.discordapp.com/embed/avatars/0.png" # 預設使用 0 號頭貼

def get_guild_icon_url(guild_id, icon_hash):
    """根據伺服器 ID 和 icon hash 生成伺服器 icon URL"""
    if icon_hash:
        return f"https://cdn.discordapp.com/icons/{guild_id}/{icon_hash}.png"
    return "" # 如果沒有 icon，返回空字串

def render_discord_emojis(text):
    """將 Discord 自定義表情符號轉換為圖片標籤。"""
    # 匹配 <a:name:id> (動態) 或 <:name:id> (靜態) 格式的表情符號
    emoji_pattern = re.compile(r"<(a?):(\w+):(\d+)>", re.IGNORECASE)

    def replace_emoji(match):
        animated = match.group(1) == 'a'
        emoji_name = match.group(2)
        emoji_id = match.group(3)
        ext = "gif" if animated else "png"
        # 確保 alt 屬性中的 emoji_name 被正確轉義
        return f'<img src="https://cdn.discordapp.com/emojis/{emoji_id}.{ext}" alt="{html.escape(emoji_name)}" class="discord-emoji">'

    return emoji_pattern.sub(replace_emoji, text)

def resolve_channel_mentions(text, guild_id):
    """將 Discord 頻道提及 (<#CHANNEL_ID>) 轉換為頻道名稱連結。"""
    if not text or not guild_id:
        return text

    channel_mention_pattern = re.compile(r"<#(\d+)>", re.IGNORECASE)

    def replace_channel_mention(match):
        channel_id = match.group(1)
        print(f"偵錯：正在嘗試解析頻道提及 ID: {channel_id}")
        if channel_id in channel_name_cache:
            channel_name = channel_name_cache[channel_id]
            print(f"偵錯：頻道 ID {channel_id} 從快取中獲取名稱: {channel_name}")
        else:
            channel_url = f"https://discord.com/api/v9/channels/{channel_id}"
            try:
                response = requests.get(channel_url, headers=headers, timeout=5)
                response.raise_for_status()
                channel_data = response.json()
                channel_name = channel_data.get('name', f'unknown-channel-{channel_id}')
                channel_name_cache[channel_id] = channel_name
                print(f"偵錯：成功獲取頻道 ID {channel_id} 的名稱: {channel_name}")
                time.sleep(0.1) # Be polite to the API
            except requests.exceptions.RequestException as e:
                print(f"錯誤：獲取頻道 ID {channel_id} 的資訊失敗: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    print(f"錯誤詳情：狀態碼 {e.response.status_code}, 回應: {e.response.text}")
                channel_name = f'unknown-channel-{channel_id}' # 使用預設名稱
                channel_name_cache[channel_id] = channel_name # Cache error to avoid repeated requests
            
        # 構建 Discord deep link 到頻道
        # 格式: https://discord.com/channels/GUILD_ID/CHANNEL_ID
        discord_link = f"https://discord.com/channels/{guild_id}/{channel_id}"
        return f'<a href="{discord_link}" target="_blank" rel="noopener noreferrer" class="discord-channel-link">#{html.escape(channel_name)}</a>'

    return channel_mention_pattern.sub(replace_channel_mention, text)

def fetch_thread_content_and_replies(thread_id, guild_id, fetch_replies=False, reply_limit=5):
    """獲取指定論壇貼文的初始貼文內容、作者資訊、伺服器暱稱、反應及回覆。"""
    # 論壇貼文的 ID 就是其初始貼文的訊息 ID
    message_url = f"https://discord.com/api/v9/channels/{thread_id}/messages/{thread_id}"
    replies = []
    try:
        msg_response = requests.get(message_url, headers=headers, timeout=5)
        msg_response.raise_for_status()
        message = msg_response.json() 
        content = message.get('content', '')
        author = message.get('author', {})
        # reactions = message.get('reactions', []) # 不再直接回傳 reactions，由 calculate_star_rating 處理

        # --- 獲取伺服器暱稱 ---
        author_name_to_display = author.get('username', '未知作者') 
        if 'id' in author and guild_id: 
            member_url = f"https://discord.com/api/v9/guilds/{guild_id}/members/{author['id']}"
            try:
                member_response = requests.get(member_url, headers=headers, timeout=5)
                member_response.raise_for_status()
                member_data = member_response.json()
                
                if member_data.get('nick'):
                    author_name_to_display = member_data['nick']
                elif member_data.get('user', {}).get('global_name'):
                    author_name_to_display = member_data['user']['global_name']
                elif author.get('global_name'):
                    author_name_to_display = author['global_name']

            except requests.exceptions.RequestException as e:
                print(f"警告：獲取用戶 {author.get('id')} 在伺服器 {guild_id} 的成員資訊失敗: {e}")
            time.sleep(0.1) 

        # --- 獲取回覆 ---
        if fetch_replies:
            # 獲取除了初始貼文之外的最新回覆
            # limit + 1 是因為會包含初始貼文
            replies_url = f"https://discord.com/api/v9/channels/{thread_id}/messages?limit={reply_limit + 1}"
            try:
                replies_response = requests.get(replies_url, headers=headers, timeout=5)
                replies_response.raise_for_status()
                all_messages_in_thread = replies_response.json()
                # 過濾掉初始貼文 (因為它的 ID 和 thread_id 相同)
                replies = [msg for msg in all_messages_in_thread if msg['id'] != thread_id][:reply_limit]
                # 將回覆從新到舊排序 (API 預設是最新在前面，但我們可能需要舊到新顯示)
                replies.reverse()

                # 獲取回覆作者的顯示名稱
                for reply in replies:
                    reply_author = reply.get('author', {})
                    reply_author_id = reply_author.get('id')
                    reply_author_name_to_display = reply_author.get('username', '未知作者')
                    if reply_author_id and guild_id:
                        member_url = f"https://discord.com/api/v9/guilds/{guild_id}/members/{reply_author_id}"
                        try:
                            member_response = requests.get(member_url, headers=headers, timeout=5)
                            member_response.raise_for_status()
                            member_data = member_response.json()
                            if member_data.get('nick'):
                                reply_author_name_to_display = member_data['nick']
                            elif member_data.get('user', {}).get('global_name'):
                                reply_author_name_to_display = member_data['user']['global_name']
                            elif reply_author.get('global_name'):
                                reply_author_name_to_display = reply_author['global_name']
                        except requests.exceptions.RequestException:
                            pass # 忽略獲取回覆作者資訊的錯誤
                        time.sleep(0.1) # 每次獲取成員資訊後稍微延遲
                    reply['display_name'] = reply_author_name_to_display
                    reply['avatar_url'] = get_avatar_url(reply_author.get('id'), reply_author.get('avatar'))

            except requests.exceptions.RequestException as e:
                print(f"警告：獲取貼文 {thread_id} 的回覆時發生錯誤: {e}")

        return content, author, author_name_to_display, replies
    except requests.exceptions.RequestException as e:
        print(f"獲取初始貼文 {thread_id} 的訊息時出錯: {e}")
    return None, None, None, [] # Return None for all if failed

def calculate_star_rating(thread_id, guild_id):
    """根據每個用戶的最高星級反應計算平均星級評分，並返回總投票數。"""
    star_emojis = {
        '1️⃣': 1,
        '2️⃣': 2,
        '3️⃣': 3,
        '4️⃣': 4,
        '5️⃣': 5,
    }
    
    user_ratings = {} # {user_id: highest_star_value}

    for emoji_name, star_value in star_emojis.items():
        # 獲取對該表情符號做出反應的用戶列表
        reactions_url = f"https://discord.com/api/v9/channels/{thread_id}/messages/{thread_id}/reactions/{emoji_name}?limit=100" # limit 100 is max
        try:
            reaction_response = requests.get(reactions_url, headers=headers, timeout=5)
            reaction_response.raise_for_status()
            users_reacted = reaction_response.json()
            
            for user in users_reacted:
                user_id = user['id']
                # 如果用戶已經評分過，只保留最高分
                if user_id not in user_ratings or star_value > user_ratings[user_id]:
                    user_ratings[user_id] = star_value
            
            time.sleep(0.5) # 每次獲取反應用戶列表後延遲

        except requests.exceptions.RequestException as e:
            print(f"警告：獲取貼文 {thread_id} 的表情符號 {emoji_name} 反應用戶失敗: {e}")
            # 繼續處理下一個表情符號，不中斷

    total_score = sum(user_ratings.values())
    total_unique_voters = len(user_ratings)
    
    if total_unique_voters > 0:
        return total_score / total_unique_voters, total_unique_voters
    return 0, 0

def render_stars(average_rating, total_unique_voters):
    """將平均分數轉換為 HTML 星級圖案，並顯示具體分數和總投票數。"""
    stars_html = ""
    for i in range(1, 6):
        if average_rating >= i:
            stars_html += '<span class="star filled-star">★</span>'
        elif average_rating > i - 1:
            # 計算部分填滿的百分比
            fill_percentage = (average_rating - (i - 1)) * 100
            stars_html += f'<span class="star partial-star" style="--fill-percentage: {fill_percentage:.1f}%;">★</span>'
        else:
            stars_html += '<span class="star empty-star">☆</span>'
    
    return f"<span class=\"star-rating-wrapper\">賽事社群評分: {stars_html} {average_rating:.1f}/5 ({total_unique_voters} 人評分)</span>"

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

def get_guild_details(guild_id):
    """獲取伺服器名稱和 icon。"""
    url = f"https://discord.com/api/v9/guilds/{guild_id}"
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"獲取伺服器詳細資訊時發生錯誤: {e}")
        return None

def get_threads(channel_id, thread_type="active"):
    """獲取活躍或封存的貼文，支援分頁。"""
    all_threads = []
    last_thread_id = None
    has_more = True
    
    if thread_type == "active":
        url = f"https://discord.com/api/v9/channels/{channel_id}/threads/active"
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json().get('threads', [])
        except requests.exceptions.RequestException as e:
            print(f"獲取活躍貼文時發生錯誤: {e}")
            return []

    elif thread_type == "archived":
        print("正在分頁獲取封存貼文...")
        while has_more:
            url = f"https://discord.com/api/v9/channels/{channel_id}/threads/archived/public?limit=100"
            if last_thread_id:
                url += f"&before={last_thread_id}"

            try:
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                data = response.json()

                threads_batch = data.get('threads', [])
                all_threads.extend(threads_batch)

                has_more = data.get('has_more', False)
                if threads_batch:
                    last_thread_id = threads_batch[-1]['id'] # ID of the last thread in the current batch
                else:
                    has_more = False # No more threads in this batch

                print(f"已獲取 {len(all_threads)} 篇封存貼文，has_more: {has_more}")
                time.sleep(0.5) # Be polite to the API

            except requests.exceptions.RequestException as e:
                print(f"分頁獲取封存貼文時發生錯誤: {e}")
                break # 發生錯誤時停止分頁
        return all_threads
    else:
        return []

def generate_post_html(title, summary, invite_link, author_display_name, author_avatar_url, tags_html, star_rating_html="", replies_html=""):
    """生成單個貼文的 HTML 片段。"""
    html_snippet = f"""
    <div class="post-card">
        <div class="post-header">
            <img src="{author_avatar_url}" alt="{author_display_name}'s avatar" class="author-avatar">
            <span class="author-name">{author_display_name}</span>
            {tags_html} <!-- 標籤移動到這裡 -->
        </div>
        <h3>{title}</h3>
        <p>{summary}</p>
        {star_rating_html} 
        {replies_html} <!-- 新增回覆區塊 -->
    """
    
    if invite_link:
        html_snippet += f'<a href="{invite_link}" target="_blank" rel="noopener noreferrer" class="join-link">點此加入社群參與討論 &raquo;</a>'
        
    html_snippet += "</div>\n"
    return html_snippet

def write_html_file(filename, content, page_title, server_name="", server_icon_url="", last_updated_time=""):
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
    final_html = final_html.replace('<!-- SERVER_NAME -->', html.escape(server_name))
    final_html = final_html.replace('<!-- SERVER_ICON_URL -->', server_icon_url)
    final_html = final_html.replace('<!-- LAST_UPDATED_TIME -->', last_updated_time) # 新增：替換更新時間

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(final_html)

# --- 主執行邏輯 ---

# 1. 獲取論壇頻道詳細資訊以找到 CTF 標籤 ID 和所有標籤映射
forum_details = get_forum_channel_details(CHANNEL_ID)
ctf_tag_id = None
tag_map = {}
forum_guild_id = None
server_name = ""
server_icon_url = ""

if forum_details:
    forum_guild_id = forum_details.get('guild_id')
    if forum_guild_id:
        guild_details = get_guild_details(forum_guild_id)
        if guild_details:
            server_name = guild_details.get('name', '')
            server_icon_url = get_guild_icon_url(forum_guild_id, guild_details.get('icon'))

    if 'available_tags' in forum_details:
        for tag in forum_details['available_tags']:
            tag_map[tag['id']] = tag['name']
            if tag['name'] == CTF_TAG_NAME:
                ctf_tag_id = tag['id']

if ctf_tag_id is None:
    print(f"警告：找不到名為 '{CTF_TAG_NAME}' 的標籤。CTF 評價頁面將不會生成。")

# 2. 獲取所有活躍和封存的貼文
print("正在獲取所有活躍貼文...")
active_threads = get_threads(CHANNEL_ID, "active")
time.sleep(0.5) 
print("正在獲取所有封存貼文...")
archived_threads = get_threads(CHANNEL_ID, "archived") # 獲取所有封存貼文
time.sleep(0.5) 

# 3. 合併並去重所有貼文
all_unique_threads = {}
for thread in active_threads + archived_threads:
    all_unique_threads[thread['id']] = thread

# 4. 根據創建時間排序 (通常 id 越大代表越新)
sorted_threads = sorted(all_unique_threads.values(), key=lambda x: int(x['id']), reverse=True)

# 5. 篩選出最新的貼文和 CTF 貼文
latest_threads = sorted_threads[:MAX_POSTS_TO_FETCH] # 主頁面仍有限制
ctf_threads = [t for t in sorted_threads if ctf_tag_id and 'applied_tags' in t and ctf_tag_id in t['applied_tags']]

# 獲取當前更新時間 (台灣時區)
tz_taiwan = pytz.timezone('Asia/Taipei') # 定義台灣時區
current_utc_time = datetime.datetime.utcnow() # 獲取當前 UTC 時間
current_taiwan_time = current_utc_time.replace(tzinfo=pytz.utc).astimezone(tz_taiwan) # 轉換為台灣時區
formatted_time = current_taiwan_time.strftime('%Y-%m-%d %H:%M %Z%z') # 格式化時間字串，包含時區縮寫和偏移量

# --- 生成主頁面 (index.html) ---
html_content_main = ""
for thread in latest_threads:
    content, author_data, author_display_name, _ = fetch_thread_content_and_replies(thread['id'], forum_guild_id)
    if content is None and author_data is None: 
        continue

    summary_limit = 120
    # 先對原始 content 進行截斷
    truncated_content = content
    if len(content) > summary_limit:
        truncated_content = content[:summary_limit] + '...'

    # 然後再對這個已經截斷的文本進行 HTML 轉換
    processed_content = render_discord_emojis(truncated_content)
    processed_content = resolve_channel_mentions(processed_content, forum_guild_id)
    summary = processed_content.replace('\n', '<br>')
    
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
    time.sleep(0.2) 

# 添加提示訊息
if len(sorted_threads) > MAX_POSTS_TO_FETCH:
    html_content_main += f"""
    <div class="info-card">
        <p>僅顯示最新的 {MAX_POSTS_TO_FETCH} 篇文章。還有更多精彩討論在社群中！</p>
        <a href="{INVITE_LINK}" target="_blank" rel="noopener noreferrer" class="join-link">點此加入社群查看更多 &raquo;</a>
    </div>
    """
elif not html_content_main:
    html_content_main = "<p>目前還沒有任何討論，快來發表第一篇吧！</p>"

write_html_file('index.html', html_content_main, "社群討論精華", server_name, server_icon_url, formatted_time)
print("index.html 已成功根據論壇內容產生！")

# --- 生成 CTF 評價頁面 (ctf_reviews.html) ---
if ctf_tag_id:
    html_content_ctf = ""
    for i, thread in enumerate(ctf_threads):
        # 對於 CTF 評價頁面，獲取所有數據，包括 reactions
        fetch_replies = (i < 5) # 只對前 5 篇獲取回覆
        content, author_data, author_display_name, replies = fetch_thread_content_and_replies(thread['id'], forum_guild_id, fetch_replies=fetch_replies)
        if content is None and author_data is None: 
            continue

        summary_limit = 120
        # 先對原始 content 進行截斷
        truncated_content = content
        if len(content) > summary_limit:
            truncated_content = content[:summary_limit] + '...'

        # 然後再對這個已經截斷的文本進行 HTML 轉換
        processed_content = render_discord_emojis(truncated_content)
        processed_content = resolve_channel_mentions(processed_content, forum_guild_id)
        summary = processed_content.replace('\n', '<br>')
        
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

        # 計算並渲染星級評分 (現在會為每個 CTF 貼文重新獲取反應用戶列表)
        average_rating, total_unique_voters = calculate_star_rating(thread['id'], forum_guild_id) 
        star_rating_html = ""
        if total_unique_voters > 0: 
            star_rating_html = render_stars(average_rating, total_unique_voters) 

        # 渲染回覆
        replies_html = ""
        if replies:
            replies_html = '<div class="replies-container"><h4>最新回覆：</h4>'
            for reply in replies:
                # 先處理 Discord 表情符號，再處理頻道提及，最後進行 HTML 轉義
                processed_reply_content = render_discord_emojis(reply.get('content', '<i>(無內容)</i>'))
                processed_reply_content = resolve_channel_mentions(processed_reply_content, forum_guild_id)
                reply_content = processed_reply_content.replace('\n', '<br>')
                replies_html += f"""
                <div class="reply-item">
                    <img src="{reply.get('avatar_url')}" alt="{reply.get('display_name')}'s avatar" class="reply-avatar">
                    <span class="reply-author">{html.escape(reply.get('display_name', '未知作者'))}</span>: 
                    <span class="reply-content">{reply_content}</span>
                </div>
                """
            replies_html += '</div>'

        html_content_ctf += generate_post_html(
            html.escape(thread['name']),
            summary,
            INVITE_LINK,
            author_display_name,
            author_avatar_url,
            thread_tags_html,
            star_rating_html,
            replies_html # 傳遞回覆 HTML
        )
        time.sleep(0.2) 

    if not html_content_ctf:
        html_content_ctf = "<p>目前還沒有任何 CTF 評價貼文。</p>"

    write_html_file('ctf_reviews.html', html_content_ctf, "CTF 評價", server_name, server_icon_url, formatted_time)
    print("ctf_reviews.html 已成功產生！")

print("所有頁面生成完畢。")