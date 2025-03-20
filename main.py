from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

@register("lifebuddy", "YourName", "生活好基友", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
    
    # 注册指令的装饰器。指令名为 helloworld。注册成功后，发送 `/helloworld` 就会触发这个指令，并回复 `你好, {user_name}!`
    #@filter.command("来首")
    #async def helloworld(self, event: AstrMessageEvent):
    #    '''来首''' # 这是 handler 的描述，将会被解析方便用户了解插件内容。建议填写。
    #    user_name = event.get_sender_name()
    #    message_str = event.message_str # 用户发的纯文本消息字符串
    #    message_chain = event.get_messages() # 用户所发的消息的消息链 # from astrbot.api.message_components import *
    #    logger.info(message_chain)
    #    yield event.plain_result(f"未找到歌曲{message_str}!") # 发送一条纯文本消息

    @event_message_type(EventMessageType.ALL)
    async def on_all_message(self, event: AstrMessageEvent):
        message_str = event.message_str # 获取消息的纯文本内容
        if message_str.startswith("来首")
            message_musicname=message_str[3:]
            yield event.plain_result(f"未找到歌曲{message_musicname}")
        else
            yield event.plain_result(f"{message_musicname}")

    async def terminate(self):
        '''可选择实现 terminate 函数，当插件被卸载/停用时会调用。'''
