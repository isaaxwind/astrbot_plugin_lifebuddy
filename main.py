from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.all import *
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Plain, Image
import urllib.parse
import random
import binascii
from .api import NeteaseCloudMusicAPI

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
    @filter.command("ask")
    async def ask(self, event: AstrMessageEvent):
        '''ask''' # 这是 handler 的描述，将会被解析方便用户了解插件内容。建议填写。
        user_name = event.get_sender_name()
        message_str = event.message_str # 用户发的纯文本消息字符串
        args=message_str.split( )
        if len(args)<4:
            yield event.plain_result("选项太少！")
        else:
            summary=0
            chance={}
            for i in range(2,len(args)):
                crcName=binascii.crc32(user_name.encode())%1000
                crcQuestion=binascii.crc32(args[1].encode())%1000
                crcChoice=binascii.crc32(args[i].encode())%1000
                random.seed(crcName*crcQuestion*crcChoice)
                a=random.randint(0,10000)
                if args[i] not in chance:
                    chance[args[i]]=a
                    summary+=a
            if len(chance)<2:
                yield event.plain_result("选项太少！")
            else:
                result=f"{user_name} 的 {args[1]} 选择建议如下："
                result_pair=sorted(chance.items(),key=lambda d:d[1], reverse=True)
                for key, value in result_pair:
                    result_chance=f"\n{key} ({value/summary*100:.2f}%)"
                    result+=result_chance
    #    message_chain = event.get_messages() # 用户所发的消息的消息链 # from astrbot.api.message_components import *
    #    logger.info(message_chain)
                yield event.plain_result(result) # 发送一条纯文本消息

    @event_message_type(EventMessageType.ALL)
    async def on_all_message(self, event: AstrMessageEvent):
        '''来首'''
        alias={
            "鸡犬":"https://chilundui.com/data/rbdx/image/song/500100992.png",
            "傻逼":"https://chilundui.com/data/rbdx/image/song/120000706.png",
            "盎司老头":"https://chilundui.com/data/rbdx/image/song/600400052.png",
            "跪舔":"https://chilundui.com/data/rbdx/image/song/100000840.png",
            "七人行":"https://chilundui.com/data/rbdx/image/song/500101434.png",
            "六人行":"https://chilundui.com/data/rbdx/image/song/600500061.png",
            "热播":"https://remywiki.com/images/thumb/2/24/Rebellio.png/300px-Rebellio.png",
            "灾舞":"https://remywiki.com/images/thumb/a/a6/Catastrophic_Dance.png/300px-Catastrophic_Dance.png",
            "吃辣":"https://chilundui.com/data/rbdx/image/song/100000799.png",
            "异端":"https://chilundui.com/data/rbdx/image/song/120000532.png",
            "雪崩":"https://chilundui.com/data/rbdx/image/song/120000640.png",
            "石玄玄":"https://chilundui.com/data/rbdx/image/song/500101271.png",
            "坏疯子":"https://remywiki.com/images/thumb/e/ef/Bad_Maniacs.png/300px-Bad_Maniacs.png",
            "bmsp":"https://remywiki.com/images/thumb/e/ef/Bad_Maniacs.png/300px-Bad_Maniacs.png",
            "坏加密":"https://chilundui.com/data/rbdx/image/song/500101437.png",
            "官恩俊霸":"https://chilundui.com/data/rbdx/image/song/500101246.png",
            "父进入母逼":"https://chilundui.com/data/rbdx/image/song/500100035.png",
            "楼":"https://remywiki.com/images/thumb/f/f4/Sakura.png/300px-Sakura.png",
            "生孩子":"https://chilundui.com/data/rbdx/image/song/500100035.png",
            "辣翅":"https://chilundui.com/data/rbdx/image/song/500100302.png",
            "旋转木马":"https://chilundui.com/data/rbdx/image/song/500101390.png",
            "樱刘谦":"https://remywiki.com/images/thumb/7/74/Sakura_Mirage.png/300px-Sakura_Mirage.png",
            "纯白":"https://remywiki.com/images/thumb/1/11/Couleur%3DBlanche.png/300px-Couleur%3DBlanche.png",
            "惊刘谦":"https://chilundui.com/data/rbdx/image/song/500100214.png",
            "刘谦魔术":"https://remywiki.com/images/thumb/f/fb/Mirage.png/300px-Mirage.png",
            "看菲修理鹅":"https://chilundui.com/data/rbdx/image/song/500100749.png",
            "四川火娃":"https://chilundui.com/data/rbdx/image/song/500100752.png",
            "四川火娃弱智齿轮队":"https://remywiki.com/images/thumb/f/fe/SCHWARZSCHILD_FIELD.png/300px-SCHWARZSCHILD_FIELD.png",
            "队歌":"https://remywiki.com/images/thumb/f/fe/SCHWARZSCHILD_FIELD.png/300px-SCHWARZSCHILD_FIELD.png",
            "挠屁股":"https://remywiki.com/images/thumb/6/63/GLITTER.png/300px-GLITTER.png"}
        msg_str = event.message_str # 获取消息的纯文本内容
        if msg_str.startswith("来首") and len(msg_str)>=2:
            for item in event.message_obj.message:
                if isinstance(item, Image):
                    yield event.plain_result(f"图片可来不了，另请高明吧")
                    return

            if len(msg_str)<=2:
                return

            songname = msg_str[2:]
            api = NeteaseCloudMusicAPI()
            songs = await api.fetch_song_data(songname, limit=1, pic=True)
            if not songs or songs==[]:
                yield event.plain_result(f"未找到歌曲{songname}")
                return

            song = songs[0]
            song_id = song['id']
            song_artist=', '.join(song['artists'])
            album_img1v1Url = song['album_img1v1Url']
            song_name = song['name']
            song_link=f"https://music.163.com/#/song?id={song_id}" 
            result=event.make_result();
            result.chain = [Image(file=album_img1v1Url) ,
                Plain(f"{song_name}\n{song_artist}\n{song_link}")]
            result.use_t2i(False)
            yield result

        # 别名
        elif msg_str.endswith("是什么歌") and len(msg_str)>=4:
            for item in event.message_obj.message:
                if isinstance(item, Image):
                    yield event.plain_result(f"图片可判断不了，另请高明吧")
                    return

            if len(msg_str)<=4:
                return

            songname = msg_str.split("是什么歌")[0]
            have=False
            try:
                for i in alias:
                    if i.lower() in songname.lower():
                        result=event.make_result();
                        result.chain = [Plain(f"您要找的是不是："),
                            Image(file=alias[i])]
                        result.use_t2i(False)
                        yield result
                        have=True
                        
                if not have:
                    yield event.plain_result(f"未找到别名为“{songname}”的歌")
            except Exception as e:
                yield event.plain_result(f"出错了，傻逼！")
                yield event.plain_result(f"{e}")

    async def terminate(self):
        '''可选择实现 terminate 函数，当插件被卸载/停用时会调用。'''


