from __future__ import annotations

import aiohttp


class NeteaseCloudMusicAPI:
    def __init__(self):
        self.session: aiohttp.ClientSession | None = None

    def _session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def fetch_song_detail(self, song_id):
        url = f"http://music.163.com/api/song/detail/?id={song_id}&ids=[{song_id}]"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": "https://music.163.com/",
        }
        try:
            async with self._session().get(url, headers=headers, timeout=5) as response:
                if response.status == 200:
                    data = await response.json(content_type=None)
                    songs = data.get("songs", [])
                    if songs:
                        return songs[0].get("al", {}).get("picUrl") or songs[0].get("album", {}).get("picUrl")
        except Exception as e:
            print(f"获取封面详情失败: {e}")
        return None

    async def fetch_song_data(self, keywords, limit=5, pic=True):
        url = "http://music.163.com/api/search/get/web"
        params = {"s": keywords, "type": 1, "offset": 0, "total": "true", "limit": limit}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": "https://music.163.com/",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        try:
            async with self._session().post(url, data=params, headers=headers, timeout=5) as response:
                if response.status == 200:
                    data = await response.json(content_type=None)
                    result = []
                    songs = data.get("result", {}).get("songs", [])

                    for song in songs:
                        song_id = song["id"]
                        pic_url = None
                        if pic:
                            pic_url = await self.fetch_song_detail(song_id)
                        if not pic_url:
                            pic_url = "https://p1.music.126.net/UeTuwE7pvjBpypWLudqukA==/3132508627578625.jpg"

                        result.append(
                            {
                                "id": song_id,
                                "name": song["name"],
                                "artists": [artist["name"] for artist in song.get("artists", [])],
                                "album": song.get("album", {}).get("name", ""),
                                "album_img1v1Url": pic_url,
                            }
                        )
                    return result
        except Exception as e:
            print(f"网易云官方请求异常: {e}")
        return []

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
