# Unused leftover from the plugin template (song comments t2i). Kept so it is not lost.
HTML_TMPL = """
<!DOCTYPE html>
<html lang="zh-cn">
<head>
    <meta charset="UTF-8">
    <title>{{ song_name }}</title>
    <style>
        body { font-family: Arial, sans-serif; background-color: #121212; color: #ffffff; margin: 0; padding: 0; display: flex; justify-content: center; align-items: center; height: 100vh; }
        .container { background-color: #1e1e1e; padding: 40px; box-sizing: border-box; display: flex; border-radius: 10px; }
        .song { flex: 1; text-align: center; }
        .song img { max-width: 100%; border-radius: 10px; }
        .song h1 { font-size: 48px; margin: 20px 0; }
        .comments { flex: 2; margin-left: 40px; }
        .comment { margin-bottom: 20px; padding: 20px; border-bottom: 1px solid #333; }
        .comment p { margin: 0; font-size: 28px; }
        .comment strong { color: #ffffff; }
    </style>
</head>
<body>
    <div class="container">
        <div class="song">
            <img src="{{ album_img1v1Url }}" alt="Album Cover">
            <h1>{{ song_name }}</h1>
        </div>
        <div class="comments">
            <h2>热评:</h2>
            {% for comment in comments %}
            <div class="comment">
                <p><strong>{{ comment.user_nickname }}:</strong> {{ comment.content }} (Likes: {{ comment.likedCount }})</p>
            </div>
            {% endfor %}
        </div>
    </div>
</body>
</html>
"""
