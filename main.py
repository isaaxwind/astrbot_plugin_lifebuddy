from .api import NeteaseMusicAPI
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.all import *
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Plain, Image
import urllib.parse

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

@register("lifebuddy", "YourName", "生活好基友", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
    
    # 注册指令的装饰器。指令名为 helloworld。注册成功后，发送 `/helloworld` 就会触发这个指令，并回复 `你好, {user_name}!`
    #@filter.command("helloworld")
    #async def helloworld(self, event: AstrMessageEvent):
    #    '''helloworld''' # 这是 handler 的描述，将会被解析方便用户了解插件内容。建议填写。
    #    user_name = event.get_sender_name()
    #    message_str = event.message_str # 用户发的纯文本消息字符串
    #    message_chain = event.get_messages() # 用户所发的消息的消息链 # from astrbot.api.message_components import *
    #    logger.info(message_chain)
    #    yield event.plain_result(f"你发送了{message_str}!") # 发送一条纯文本消息

    @event_message_type(EventMessageType.ALL)
    async def on_all_message(self, event: AstrMessageEvent):
        '''来首'''
        msg_str = event.message_str # 获取消息的纯文本内容
        if msg_str.startswith("来首") and len(msg_str)>2:
            api = NeteaseMusicAPI()
            songname = msg_str[2:]
            songs = await api.fetch_song_data(songname, limit=1, pic=True)
            if not songs or songs==[]:
                yield event.plain_result(f"未找到歌曲{songname}")
                return

            song = songs[0]
            result=f"https://music.163.com/#/song?id={song['id']}"
            result = event.plain_result(result)
            result.use_t2i(False)
            yield result

    async def terminate(self):
        '''可选择实现 terminate 函数，当插件被卸载/停用时会调用。'''


