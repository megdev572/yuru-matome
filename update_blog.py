import os
import re
import json
import requests

# --- ファイルパス設定 ---
CONFIG_FILE = "config.json"
TEMPLATE_FILE = "template.html"
OUTPUT_FILE = "index.html"

# 設定ファイル（config.json）を読み込む関数
def load_config():
    if not os.path.exists(CONFIG_FILE):
        default_config = {
            "BLUESKY_HANDLE": "your-handle.bsky.social",
            "BLUESKY_APP_PASSWORD": "xxxx-xxxx-xxxx-xxxx",
            "AI_MODEL": "gemma2:2b",
            "OLLAMA_API_URL": "http://localhost:11434/api/chat"
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)
        print(f"⚠️ {CONFIG_FILE} が見つかりませんでした。作成したので設定を書き換えてください。")
        return None
    
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# Blueskyにログインして、複数のキーワードで個別に検索して合体させる
def fetch_bluesky_posts(config):
    print("1. Blueskyにログインしています...")
    
    handle = config.get("BLUESKY_HANDLE")
    app_password = config.get("BLUESKY_APP_PASSWORD")
    
    session_url = "https://bsky.social/xrpc/com.atproto.server.createSession"
    login_data = {
        "identifier": handle,
        "password": app_password
    }
    
    try:
        session_resp = requests.post(session_url, json=login_data, timeout=10)
        if session_resp.status_code != 200:
            print(f"❌ ログインに失敗しました（ステータス: {session_resp.status_code}）")
            print("config.json のハンドル名やアプリパスワードに誤りがないかご確認ください。")
            return []
        
        token = session_resp.json().get("accessJwt")
        print("  🔑 ログインに成功しました！ 検索を開始します。")
        
        keywords = ["お散歩", "ほっこり", "おやすみ"]
        all_posts = []
        
        for kw in keywords:
            print(f"  🔍 「{kw}」で検索中...")
            search_url = "https://bsky.social/xrpc/app.bsky.feed.searchPosts"
            headers = {
                "Authorization": f"Bearer {token}"
            }
            params = {
                "q": kw,
                "limit": 15  # 各キーワード多めに取得します
            }
            
            search_resp = requests.get(search_url, headers=headers, params=params, timeout=10)
            if search_resp.status_code == 200:
                posts = search_resp.json().get("posts", [])
                all_posts.extend(posts)
                print(f"    -> {len(posts)}件見つかりました。")
            else:
                print(f"    ❌ 「{kw}」の検索に失敗しました（ステータス: {search_resp.status_code}）")
                
        return all_posts
            
    except Exception as e:
        print(f"❌ Bluesky接続エラー: {e}")
        
    return []

# 🚫 広告・アダルト・ボットなどのNGワード検出（ノイズを事前除去）
def is_ng_content(post):
    text = post.get("record", {}).get("text", "").lower()
    author = post.get("author", {})
    display_name = author.get("displayName", "").lower()
    handle = author.get("handle", "").lower()
    
    combined = f"{text} {display_name} {handle}"
    
    ng_words = [
        "メンエス", "メンズエステ", "裏アカ", "18禁", "エッチ", "アダル", "エロ",
        "出会い", "bot", "ボット", "割引", "在籍", "本指名", "セラピスト", "求人", "稼げる",
        "相互フォロー", "宣伝", "出勤", "プロフ見て", "副業", "ライン誘導"
    ]
    
    for ng in ng_words:
        if ng in combined:
            return True
            
    return False

# ローカルAIが起動しているかチェック
def is_ollama_running(config):
    ollama_url = config.get("OLLAMA_API_URL")
    try:
        base_url = ollama_url.replace("/api/chat", "")
        response = requests.get(f"{base_url}/api/tags", timeout=2)
        return response.status_code == 200
    except:
        return False

# ローカルAIに「癒やし判定」を依頼する
def analyze_with_local_ai(text, config):
    ollama_url = config.get("OLLAMA_API_URL")
    ai_model = config.get("AI_MODEL")
    
    prompt = f"""
    あなたは非常に心の優しいAIアシスタントです。提供された「日本語のつぶやき内容」が、読んだ人を穏やかな気持ちにさせる「癒やし・ほっこり・心が休まる内容」かどうかを判定してください。
    カテゴリ（osampo, ocha, oyasumi のいずれか）

    ※もし、つぶやきに広告、求人、メンズエステ、アダルト、愚痴、機械的なボット投稿、その他荒みを感じる内容が含まれている場合は、無条件で is_healing を false にしてください。

    つぶやき内容:
    「{text}」

    出力は、必ず以下の「JSONフォーマット」のみで行い、余計な説明や挨拶は一切含めないでください。

    {{
      "is_healing": trueまたはfalse,
      "category": "osampo" または "ocha" または "oyasumi" または ""
    }}
    """
    payload = {
        "model": ai_model,
        "messages": [{"role": "user", "content": prompt}],
        "format": "json",
        "stream": False
    }
    
    try:
        response = requests.post(ollama_url, json=payload, timeout=25)
        if response.status_code == 200:
            content = response.json().get("message", {}).get("content", "")
            data = json.loads(content)
            return data
    except Exception as e:
        pass
    
    # 簡易ルール判定（AI未起動時など）
    lower_text = text.lower()
    if "散歩" in lower_text or "空" in lower_text or "風" in lower_text or "花" in lower_text:
        return {"is_healing": True, "category": "osampo"}
    elif "お茶" in lower_text or "ココア" in lower_text or "美味しい" in lower_text or "だらだら" in lower_text or "休憩" in lower_text:
        return {"is_healing": True, "category": "ocha"}
    elif "おやすみ" in lower_text or "布団" in lower_text or "リラックス" in lower_text or "お疲れ様" in lower_text:
        return {"is_healing": True, "category": "oyasumi"}
    
    return {"is_healing": False, "category": ""}

# 大まとめカードの内側に並べる「個々のつぶやき」HTMLを生成する
def build_mini_tweet_html(post):
    author = post.get("author", {})
    display_name = author.get("displayName", "ななしさん")
    handle = author.get("handle", "unknown")
    avatar_url = author.get("avatar", "")
    text = post.get("record", {}).get("text", "")
    created_at = post.get("record", {}).get("createdAt", "")
    
    date_str = created_at[:10] if len(created_at) >= 10 else "最近"
    
    # パーマリンク作成
    uri = post.get("uri", "")
    permalink = "https://bsky.app"
    if uri and handle:
        post_id = uri.split("/")[-1]
        permalink = f"https://bsky.app/profile/{handle}/post/{post_id}"
    
    # 画像の抽出
    images_html = ""
    embed = post.get("embed", {})
    if embed.get("$type") == "app.bsky.embed.images#view":
        images = embed.get("images", [])
        if images:
            images_html += '<div class="tweet-images">'
            for img in images:
                thumb_url = img.get("thumb")
                alt_text = img.get("alt", "image")
                if thumb_url:
                    images_html += f'<img src="{thumb_url}" alt="{alt_text}" class="tweet-media-img">'
            images_html += '</div>'
            
    avatar_html = f'<img src="{avatar_url}" class="tweet-avatar" alt="avatar">' if avatar_url else '<span class="tweet-avatar">🧸</span>'

    safe_text = html_escape(text)
    url_pattern = r'(https?://[^\s]+)'
    linked_text = re.sub(url_pattern, r'<a href="\1" target="_blank">\1</a>', safe_text)

    # 1つのつぶやきを小さな枠（mini-tweet）として表現
    html = f"""
                <div class="mini-tweet" style="background-color: var(--tweet-bg); border: 1px solid var(--tweet-border); border-radius: 16px; padding: 18px; box-shadow: 0 2px 8px var(--card-shadow); margin-bottom: 4px;">
                    <div class="tweet-user-info">
                        <div class="user-profile">
                            {avatar_html}
                            <div class="user-names">
                                <span class="display-name">{display_name}</span>
                                <span class="username">@{handle}</span>
                            </div>
                        </div>
                        <span class="tweet-date">{date_str}</span>
                    </div>
                    <p class="tweet-content" style="font-size: 0.9rem; margin-bottom: 10px;">{linked_text}</p>
                    {images_html}
                    <div style="display: flex; justify-content: flex-end; margin-top: 8px;">
                        <a href="{permalink}" target="_blank" class="origin-link" style="font-size: 0.75rem;">元の投稿 🔗</a>
                    </div>
                </div>"""
    return html

def html_escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#x27;")

def main():
    if not os.path.exists(TEMPLATE_FILE):
        print(f"エラー: {TEMPLATE_FILE} が見つかりません。")
        return

    # 1. 設定のロード
    config = load_config()
    if not config:
        return

    # 2. Blueskyからデータ取得
    posts = fetch_bluesky_posts(config)
    if not posts:
        print("投稿が取得できませんでした。処理を中断します。")
        return

    # AI判定が可能か確認
    ai_available = is_ollama_running(config)
    if ai_available:
        print(f"2. ローカルAI ({config.get('AI_MODEL')}) を使って仕分けをします...")
    else:
        print("2. ※Ollama未起動のため、簡易ルール判定を行います。")

    # つぶやきをカテゴリごとに仕分けるための辞書
    grouped_posts = {
        "osampo": [],
        "ocha": [],
        "oyasumi": []
    }
    
    # 📌 重複を管理するためのセット(Set)を用意します
    seen_texts = set()  # すでに取得したつぶやきの本文を記録
    seen_users = {      # カテゴリごとに一度追加したユーザー名を記録
        "osampo": set(),
        "ocha": set(),
        "oyasumi": set()
    }
    
    for i, post in enumerate(posts):
        text = post.get("record", {}).get("text", "")
        if not text or text.startswith("RT "):
            continue
            
        if is_ng_content(post):
            continue
            
        # 🧪 【対策1：テキストの完全重複チェック】
        # 前後の余計な空白を削って比較します
        normalized_text = text.strip()
        if normalized_text in seen_texts:
            # 完全に同じつぶやきは処理をスキップします
            continue
            
        result = analyze_with_local_ai(text, config)
        
        if result.get("is_healing") and result.get("category") in ["osampo", "ocha", "oyasumi"]:
            category = result["category"]
            
            # 🧪 【対策2：同一カテゴリ内でのユーザー重複チェック】
            author_handle = post.get("author", {}).get("handle", "")
            if author_handle in seen_users[category]:
                # すでにこのまとめに同じ人がいる場合はスキップして別の人を探します
                continue
            
            print(f"  [{i+1}/{len(posts)}] 💮 合格! カテゴリ: {category} -> {text[:15]}...")
            
            # 各セットに記録を保存
            grouped_posts[category].append(post)
            seen_texts.add(normalized_text)
            seen_users[category].add(author_handle)

    # 各まとめ記事（大カード）の設定情報
    category_infos = {
        "osampo": {
            "title": "今日のお散歩あつめ ⛅",
            "tag": "お散歩",
            "tag_class": "tag-blue",
            "color_class": "card-blue",
            "comment": "お天気の良い日は、すこし外を歩くだけで気持ちがスッと軽くなりますね🐾"
        },
        "ocha": {
            "title": "今日のお茶の時間あつめ 🍵",
            "tag": "お茶の時間",
            "tag_class": "tag-pink",
            "color_class": "card-pink",
            "comment": "美味しいお茶や温かいおやつを用意して、自分を甘やかす時間を作りましょうね🍵"
        },
        "oyasumi": {
            "title": "今日のおやすみ前あつめ 🌙",
            "tag": "おやすみ前",
            "tag_class": "tag-yellow",
            "color_class": "card-yellow",
            "comment": "今日もお疲れ様でした。お布団に入ったら、楽しかったことだけ思い出して眠りましょう🧸"
        }
    }

    selected_tweets_html = []
    
    # 3. 仕分けたデータを元に、テーマ別の「大カード」を組み立てる
    for category, posts_list in grouped_posts.items():
        if not posts_list:
            continue
            
        info = category_infos[category]
        
        tweets_inner_html = ""
        # 1つのまとめに最大4件並べる
        for post in posts_list[:4]: 
            tweets_inner_html += build_mini_tweet_html(post)
            
        # 大まとめ記事をビルド
        summary_card_html = f"""
        <!-- 【まとめ記事枠】 -->
        <article class="tweet-card {info['color_class']} {category}">
            <div class="article-header" style="margin-bottom: 20px;">
                <span class="category-tag {info['tag_class']}">{info['tag']}</span>
                <h2 class="article-title" style="font-size: 1.35rem; margin-top: 8px; color: var(--title-color);">{info['title']}</h2>
            </div>
            
            <!-- この中に複数のつぶやき（ミニ枠）を並べる -->
            <div class="article-tweets-list" style="display: flex; flex-direction: column; gap: 12px;">
                {tweets_inner_html}
            </div>
            
            <!-- グループの最後に管理人コメントを追加 -->
            <div class="admin-comment">
                <div class="admin-comment-title">🐾 管理人コメント</div>
                <p>{info['comment']}</p>
            </div>
            
            <!-- まとめ単位での「ほっこりした」ボタン -->
            <div class="tweet-actions">
                <button class="hokkori-btn" onclick="addHokkori(this)">
                    <span class="hokkori-icon">🍵</span> このまとめにほっこりした <span class="count">0</span>
                </button>
            </div>
        </article>"""
        
        selected_tweets_html.append(summary_card_html)

    if not selected_tweets_html:
        print("表示できるつぶやきが見つかりませんでした。")
        return

    print(f"\n3. 確定したまとめ記事を {OUTPUT_FILE} に書き込んでいます...")
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
        html_content = f.read()

    combined_html = "\n".join(selected_tweets_html)
    new_html_content = html_content.replace("<!-- TIMELINE_PLACEHOLDER -->", combined_html)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(new_html_content)

    print("🎉 すべて完了しました！ index.html を開いてみてください。")

if __name__ == "__main__":
    main()