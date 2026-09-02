from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.all import *
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

from .lifebuddy.advice import handle_advice
from .lifebuddy.aliases import AliasStore
from .lifebuddy.ask import handle_ask
from .lifebuddy.dib import handle_dib
from .lifebuddy.fight import handle_fight
from .lifebuddy.identity import handle_nick, inject_speaker_prompt, observe
from .lifebuddy.lists import NumberedCache
from .lifebuddy.netease import NeteaseCloudMusicAPI
from .lifebuddy.rb_cmd import RbRuntime, handle_rb
from .lifebuddy.rbdx import RbdxAPI
from .lifebuddy.rbdx_cmd import handle_rbdx
from .lifebuddy.settings import Settings
from .lifebuddy.song import SongRuntime, handle_natural_song
from .lifebuddy.store import BuddyStore


@register("lifebuddy", "Isaax", "生活好基友", "1.0.0")
class LifeBuddy(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config = config
        self.settings = Settings.from_config(config)
        self.store = BuddyStore()
        self.aliases = AliasStore.load()
        self.netease = NeteaseCloudMusicAPI()
        self.rbdx = RbdxAPI(self.settings)
        self.advice_cache = NumberedCache()
        self.fight_cache = NumberedCache()
        self.song_runtime = SongRuntime(self.aliases, self.netease, self.rbdx, self.settings)
        self.rb_runtime = RbRuntime(self.aliases, self.rbdx, self.settings, self.store, self.context)
        logger.info("lifebuddy ready, db=%s aliases=%s", self.store.path, len(self.aliases.entries))

    @filter.command("ask")
    async def ask(self, event: AstrMessageEvent):
        """ask"""
        observe(event, self.store)
        async for result in handle_ask(event):
            yield result

    @filter.command("rb")
    async def rb(self, event: AstrMessageEvent):
        """RBDX 查询 / 绑号"""
        async for result in handle_rb(event, self.rb_runtime):
            yield result

    @filter.command("rbdx")
    async def rbdx_random(self, event: AstrMessageEvent):
        """随机自制谱，可选等级"""
        observe(event, self.store)
        async for result in handle_rbdx(event, self.rbdx):
            yield result

    @filter.command("nick")
    async def nick(self, event: AstrMessageEvent):
        """QQ 称呼：/nick 上帝  或  /nick set <QQ> 上帝"""
        async for result in handle_nick(event, self.store, self.context):
            yield result

    @filter.command("dib")
    async def dib(self, event: AstrMessageEvent):
        """占坑：/dib <曲名或SongID>"""
        async for result in handle_dib(event, self.store, self.rbdx, self.context):
            yield result

    @filter.command("advice")
    async def advice(self, event: AstrMessageEvent):
        """审核：/advice  /advice <编号> 1 正文"""
        async for result in handle_advice(
            event, self.store, self.rbdx, self.settings, self.advice_cache
        ):
            yield result

    @filter.command("fight")
    async def fight(self, event: AstrMessageEvent):
        """打架：/fight  /fight <编号> <展示值>"""
        async for result in handle_fight(event, self.store, self.rbdx, self.fight_cache):
            yield result

    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req):
        inject_speaker_prompt(event, req, self.store)

    @event_message_type(EventMessageType.ALL)
    async def on_all_message(self, event: AstrMessageEvent):
        """来首 / 是什么歌"""
        observe(event, self.store)
        try:
            async for result in handle_natural_song(event, self.song_runtime):
                yield result
        except Exception as exc:
            logger.warning("on_all_message failed: %s", exc)

    async def terminate(self):
        await self.netease.close()
        await self.rbdx.close()
        self.store.close()
