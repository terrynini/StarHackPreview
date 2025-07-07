import os
import discord
import asyncio
import html

# 從 GitHub Secrets 讀取環境變數
TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID')) # 頻道 ID 需要是整數
INVITE_LINK = os.getenv('DISCORD_INVITE_LINK')

# 設定要抓取的最大貼文數量
MAX_POSTS_TO_FETCH = 15 # 例如，抓取最新的 15 篇貼文

# 設定 CTF 評價標籤的名稱
CTF_TAG_NAME = "CTF評價"

# 檢查 Secrets 是否成功載入
if not TOKEN or not CHANNEL_ID:
    print("錯誤：請在 GitHub Repository 的 Settings -> Secrets 中設定 DISCORD_TOKEN 和 DISCORD_CHANNEL_ID")
    exit(1)

# 定義 Bot 需要的權限 (Intents)
intents = discord.Intents.default()
intents.message_content = True # 允許讀取訊息內容
intents.guilds = True # 允許讀取伺服器資訊

client = discord.Client(intents=intents)

async def fetch_discord_content():
    await client.wait_until_ready()
    print(f"Logged in as {client.user}")

    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        print(f"錯誤：找不到頻道 ID {CHANNEL_ID}。請確認 ID 是否正確，且 Bot 有權限檢視該頻道。")
        await client.close()
        exit(1)

    if not isinstance(channel, discord.ForumChannel):
        print(f"錯誤：頻道 {channel.name} (ID: {CHANNEL_ID}) 不是一個論壇頻道。")
        await client.close()
        exit(1)

    # --- 獲取 CTF 評價標籤 ID ---
    ctf_tag_id = None
    for tag in channel.available_tags:
        if tag.name == CTF_TAG_NAME:
            ctf_tag_id = tag.id
            break
    
    if ctf_tag_id is None:
        print(f"警告：找不到名為 '{CTF_TAG_NAME}' 的標籤。CTF 評價頁面將不會生成。")

    all_threads = []
    ctf_threads = []

    # --- 優先抓取活躍貼文 ---
    print("正在抓取活躍中的貼文...")
    async for thread in channel.active_threads():
        all_threads.append(thread)
        if ctf_tag_id and ctf_tag_id in thread.applied_tags:
            ctf_threads.append(thread)
        if len(all_threads) >= MAX_POSTS_TO_FETCH:
            break

    # --- 如果活躍貼文不足，再補充封存貼文 ---
    if len(all_threads) < MAX_POSTS_TO_FETCH:
        print(f"活躍貼文不足 {MAX_POSTS_TO_FETCH} 篇，正在補充封存貼文...")
        async for thread in channel.archived_threads(limit=MAX_POSTS_TO_FETCH - len(all_threads)):
            all_threads.append(thread)
            if ctf_tag_id and ctf_tag_id in thread.applied_tags:
                ctf_threads.append(thread)
            if len(all_threads) >= MAX_POSTS_TO_FETCH:
                break

    # --- 處理主頁面 (index.html) 內容 ---
    html_content_main = ""
    for thread in all_threads:
        html_content_main += await process_thread(thread, INVITE_LINK)

    if not html_content_main:
        html_content_main = "<p>目前還沒有任何討論，快來發表第一篇吧！</p>"

    await write_html_file('index.html', html_content_main, "社群討論精華")
    print("index.html 已成功根據論壇內容產生！")

    # --- 處理 CTF 評價頁面 (ctf_reviews.html) 內容 ---
    if ctf_tag_id:
        html_content_ctf = ""
        for thread in ctf_threads:
            html_content_ctf += await process_thread(thread, INVITE_LINK)
        
        if not html_content_ctf:
            html_content_ctf = "<p>目前還沒有任何 CTF 評價貼文。</p>"

        await write_html_file('ctf_reviews.html', html_content_ctf, "CTF 評價")
        print("ctf_reviews.html 已成功產生！")
    
    await client.close()

async def process_thread(thread, invite_link):
    """處理單個貼文並返回其 HTML 片段"""
    title = html.escape(thread.name)
    
    first_message_content = ""
    try:
        async for message in thread.history(limit=1):
            first_message_content = message.content
            break
    except discord.Forbidden:
        print(f"警告：Bot 無權限讀取貼文 {thread.name} (ID: {thread.id}) 的訊息。")
    except Exception as e:
        print(f"獲取貼文 {thread.name} (ID: {thread.id}) 的訊息時發生錯誤: {e}")

    summary_limit = 120
    if first_message_content:
        if len(first_message_content) > summary_limit:
            summary = html.escape(first_message_content[:summary_limit]).replace('\n', '<br>') + '...'
        else:
            summary = html.escape(first_message_content).replace('\n', '<br>')
    else:
        summary = "<i>(此貼文無內文)</i>"

    html_snippet = f"""
    <div class="post">
        <h3>{title}</h3>
        <p>{summary}</p>
    """
    
    if invite_link:
        html_snippet += f'<a href="{invite_link}" target="_blank" rel="noopener noreferrer">點此加入社群參與討論 &raquo;</a>'
        
    html_snippet += "</div>\n"
    return html_snippet

async def write_html_file(filename, content, page_title):
    """將內容寫入 HTML 檔案"""
    try:
        with open('template.html', 'r', encoding='utf-8') as f:
            template = f.read()
    except FileNotFoundError:
        print("錯誤：找不到 template.html 檔案。")
        await client.close()
        exit(1)

    # 替換標題和內容
    final_html = template.replace('<!-- PAGE_TITLE -->', page_title)
    final_html = final_html.replace('<!-- DISCORD_MESSAGES -->', content)

    with open(filename, 'w', encoding='utf-8') as f:
        f.write(final_html)

# 啟動 Bot
client.event(fetch_discord_content)
client.run(TOKEN)