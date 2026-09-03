from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.all import *
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

from .lifebuddy.advice import handle_advice
from .lifebuddy.aliases import AliasStore
from .lifebuddy.ask import handle_ask
from .lifebuddy.dib import handle_dib
from .lifebuddy.fight import handle_fight
from .lifebuddy.help_cmd import handle_help
from .lifebuddy.identity import (
    deny_public_extras,
    handle_nick,
    inject_speaker_prompt,
    inject_vision,
    observe,
    stop_event,
)
from .lifebuddy.image_cache import ImageCache
from .lifebuddy.lists import NumberedCache
from .lifebuddy.netease import NeteaseCloudMusicAPI
from .lifebuddy.rb_cmd import RbRuntime, handle_rb
from .lifebuddy.rbdx import RbdxAPI
from .lifebuddy.rbdx_cmd import handle_rbdx
from .lifebuddy.settings import Settings
from .lifebuddy.song import SongRuntime, handle_natural_song
from .lifebuddy.store import BuddyStore
from .lifebuddy.symmetry import handle_symmetry, ingest_event_image


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
        self.images = ImageCache()
        proxy = self.settings.rbdx_http_proxy or "-"
        if self.settings.rbdx_http_proxy.lower().startswith("socks"):
            logger.warning("rbdx_http_proxy 是 SOCKS，aiohttp 用不了，请改 Clash 的 HTTP/Mixed 端口")
        logger.info(
            "lifebuddy ready, db=%s aliases=%s proxy=%s image_base=%s",
            self.store.path,
            len(self.aliases.entries),
            proxy,
            self.settings.rbdx_image_base,
        )

    @filter.command("help")
    async def help_cmd(self, event: AstrMessageEvent):
        """帮助：/help  /help rbdx"""
        stop_event(event)
        async for result in handle_help(event, self.settings):
            yield result

    def _public_blocked(self, event: AstrMessageEvent) -> bool:
        return deny_public_extras(event, self.settings, self.context)

    @filter.command("ask")
    async def ask(self, event: AstrMessageEvent):
        """ask"""
        observe(event, self.store)
        stop_event(event)
        if self._public_blocked(event):
            return
        async for result in handle_ask(event, self.store):
            yield result

    @filter.command("rb")
    async def rb(self, event: AstrMessageEvent):
        """RBDX 查询 / 绑号"""
        stop_event(event)
        async for result in handle_rb(event, self.rb_runtime):
            yield result

    @filter.command("rbdx")
    async def rbdx_random(self, event: AstrMessageEvent):
        """随机曲，可选 arcade/test 和等级"""
        observe(event, self.store)
        stop_event(event)
        try:
            async for result in handle_rbdx(event, self.rbdx, self.settings):
                yield result
        except Exception as exc:
            logger.warning("rbdx failed: %s", exc)
            yield event.plain_result("自制谱列表暂时连不上")

    @filter.command("nick")
    async def nick(self, event: AstrMessageEvent):
        """QQ 称呼：/nick 上帝  或  /nick set <QQ> 上帝"""
        stop_event(event)
        if self._public_blocked(event):
            return
        async for result in handle_nick(event, self.store, self.context):
            yield result

    @filter.command("dib")
    async def dib(self, event: AstrMessageEvent):
        """口香：/dib 看自己  /dib <曲名>  /dib list"""
        stop_event(event)
        if self._public_blocked(event):
            return
        async for result in handle_dib(event, self.store, self.rbdx, self.context):
            yield result

    @filter.command("advice")
    async def advice(self, event: AstrMessageEvent):
        """审核：/advice  /advice <编号> 1 正文"""
        stop_event(event)
        if self._public_blocked(event):
            return
        async for result in handle_advice(
            event, self.store, self.rbdx, self.settings, self.advice_cache
        ):
            yield result

    @filter.command("fight")
    async def fight(self, event: AstrMessageEvent):
        """打架：/fight  /fight <编号> <展示值>"""
        stop_event(event)
        if self._public_blocked(event):
            return
        async for result in handle_fight(event, self.store, self.rbdx, self.fight_cache):
            yield result

    @filter.command("左对称", alias={"对称左", "对称"})
    async def sym_left(self, event: AstrMessageEvent):
        """左对称：[比例0-100，默认50]"""
        stop_event(event)
        if self._public_blocked(event):
            return
        async for result in handle_symmetry(event, self.images, "left"):
            yield result

    @filter.command("右对称", alias={"对称右"})
    async def sym_right(self, event: AstrMessageEvent):
        """右对称：[比例0-100，默认50]"""
        stop_event(event)
        if self._public_blocked(event):
            return
        async for result in handle_symmetry(event, self.images, "right"):
            yield result

    @filter.command("上对称", alias={"对称上"})
    async def sym_top(self, event: AstrMessageEvent):
        """上对称：[比例0-100，默认50]"""
        stop_event(event)
        if self._public_blocked(event):
            return
        async for result in handle_symmetry(event, self.images, "top"):
            yield result

    @filter.command("下对称", alias={"对称下"})
    async def sym_bottom(self, event: AstrMessageEvent):
        """下对称：[比例0-100，默认50]"""
        stop_event(event)
        if self._public_blocked(event):
            return
        async for result in handle_symmetry(event, self.images, "bottom"):
            yield result

    @filter.command("倒放")
    async def gif_reverse(self, event: AstrMessageEvent):
        """动图倒放"""
        stop_event(event)
        if self._public_blocked(event):
            return
        async for result in handle_symmetry(event, self.images, "reverse"):
            yield result

    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req):
        if self._public_blocked(event):
            stop_event(event)
            return
        inject_speaker_prompt(event, req, self.store)
        try:
            await inject_vision(event, req, self.images)
        except Exception as exc:
            logger.warning("inject vision failed: %s", exc)

    @event_message_type(EventMessageType.ALL)
    async def on_all_message(self, event: AstrMessageEvent):
        """来首 / 是什么歌；顺便存图给对称用"""
        observe(event, self.store)
        msg = event.message_str or ""
        natural_song = (msg.startswith("来首") and len(msg) >= 2) or (
            msg.endswith("是什么歌") and len(msg) >= 4
        )
        if natural_song:
            stop_event(event)
            if self._public_blocked(event):
                return
        try:
            await ingest_event_image(event, self.images)
        except Exception as exc:
            logger.warning("ingest image failed: %s", exc)
        try:
            async for result in handle_natural_song(event, self.song_runtime):
                yield result
        except Exception as exc:
            logger.warning("on_all_message failed: %s", exc)

    async def terminate(self):
        await self.netease.close()
        await self.rbdx.close()
        self.store.close()
