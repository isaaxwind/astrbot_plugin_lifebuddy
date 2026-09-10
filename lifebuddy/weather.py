from __future__ import annotations

import aiohttp

from astrbot.api.event import AstrMessageEvent

from .identity import sender_qq
from .store import BuddyStore

USAGE_CITY = "/city <城市>  记下你所在的城市\n/city  看当前设置\n/city 清  清掉"
USAGE_WEATHER = "/weather  查自己城市的天气\n/weather <城市>  查指定城市"

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HTTP_UA = "Mozilla/5.0 (compatible; lifebuddy/1.0)"

_WMO = {
    0: "晴",
    1: "晴间多云",
    2: "多云",
    3: "阴",
    45: "雾",
    48: "冻雾",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "大毛毛雨",
    56: "冻毛毛雨",
    57: "冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "小阵雨",
    81: "阵雨",
    82: "强阵雨",
    85: "小阵雪",
    86: "大阵雪",
    95: "雷阵雨",
    96: "雷阵雨带冰雹",
    99: "强雷暴带冰雹",
}

_WIND = ("北", "东北", "东", "东南", "南", "西南", "西", "西北")


def _wind_dir(deg) -> str:
    try:
        value = float(deg)
    except (TypeError, ValueError):
        return ""
    return _WIND[int((value + 22.5) % 360 // 45)]


def _wmo_text(code) -> str:
    try:
        return _WMO.get(int(code), f"天气代码 {code}")
    except (TypeError, ValueError):
        return "未知"


class WeatherClient:
    def __init__(self, proxy: str = ""):
        self.proxy = (proxy or "").strip() or None
        self.session: aiohttp.ClientSession | None = None

    def _session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=12),
                trust_env=True,
            )
        return self.session

    async def close(self) -> None:
        session = self.session
        self.session = None
        if session and not session.closed:
            await session.close()

    async def _get_json(self, url: str, params: dict) -> dict | None:
        try:
            async with self._session().get(
                url,
                params=params,
                headers={"User-Agent": HTTP_UA, "Accept": "application/json"},
                proxy=self.proxy,
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    async def lookup(self, city: str) -> dict | None:
        name = (city or "").strip()
        if not name:
            return None
        data = await self._get_json(
            GEO_URL,
            {"name": name, "count": 1, "language": "zh", "format": "json"},
        )
        results = (data or {}).get("results") or []
        if not results:
            return None
        hit = results[0]
        label = str(hit.get("name") or name).strip() or name
        admin = str(hit.get("admin1") or "").strip()
        country = str(hit.get("country") or "").strip()
        extra = " ".join(x for x in (admin, country) if x and x != label)
        return {
            "name": label,
            "where": f"{label}（{extra}）" if extra else label,
            "lat": float(hit["latitude"]),
            "lon": float(hit["longitude"]),
        }

    async def forecast(self, city: str) -> str:
        place = await self.lookup(city)
        if not place:
            return f"找不到城市「{city}」"
        data = await self._get_json(
            FORECAST_URL,
            {
                "latitude": place["lat"],
                "longitude": place["lon"],
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,wind_direction_10m,apparent_temperature",
                "timezone": "Asia/Shanghai",
                "wind_speed_unit": "kmh",
            },
        )
        current = (data or {}).get("current") or {}
        if not current:
            return f"{place['where']} 天气暂时查不到"
        temp = current.get("temperature_2m")
        feels = current.get("apparent_temperature")
        humid = current.get("relative_humidity_2m")
        wind = current.get("wind_speed_10m")
        sky = _wmo_text(current.get("weather_code"))
        wind_txt = _wind_dir(current.get("wind_direction_10m"))
        bits = [place["where"], sky]
        if temp is not None:
            bits.append(f"{temp}°C")
        lines = [" ".join(str(x) for x in bits)]
        extra = []
        if feels is not None:
            extra.append(f"体感 {feels}°C")
        if humid is not None:
            extra.append(f"湿度 {humid}%")
        if wind is not None:
            extra.append(f"{wind_txt}风 {wind}km/h".strip())
        if extra:
            lines.append("  ".join(extra))
        return "\n".join(lines)


async def handle_city(event: AstrMessageEvent, store: BuddyStore):
    qq = sender_qq(event)
    if not qq:
        yield event.plain_result("认不出你是谁")
        return
    parts = (event.message_str or "").split()
    args = parts[1:] if parts else []
    if not args:
        city = store.get_city(qq)
        if city:
            yield event.plain_result(f"你现在的城市是 {city}")
        else:
            yield event.plain_result(USAGE_CITY)
        return
    token = args[0]
    if token in ("清", "clear", "del", "删除", "取消"):
        if store.clear_city(qq):
            yield event.plain_result("已清掉城市")
        else:
            yield event.plain_result("你还没设过城市")
        return
    city = " ".join(args).strip()
    store.set_city(qq, city)
    yield event.plain_result(f"已记下城市 {city}")


async def handle_weather(event: AstrMessageEvent, store: BuddyStore, client: WeatherClient):
    parts = (event.message_str or "").split()
    args = parts[1:] if parts else []
    city = " ".join(args).strip()
    if not city:
        city = store.get_city(sender_qq(event))
        if not city:
            yield event.plain_result("先 /city 设城市，或 /weather <城市>")
            return
    yield event.plain_result(await client.forecast(city))
