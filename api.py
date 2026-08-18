import aiohttp

class NeteaseCloudMusicAPI:
    def __init__(self):
        # 彻底抛弃第三方，使用原生 aiohttp 直连官方
        self.session = aiohttp.ClientSession()

    async def fetch_song_data(self, keywords, limit=5, pic=True):
        url = "http://music.163.com/api/search/get/web"
        # 官方原生参数
        params = {'s': keywords, 'type': 1, 'offset': 0, 'total': 'true', 'limit': limit}
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://music.163.com/',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        try:
            # 强制 5 秒超时，拒绝死等
            async with self.session.post(url, data=params, headers=headers, timeout=5) as response:
                if response.status == 200:
                    data = await response.json(content_type=None)
                    result = []
                    # 解析官方返回的嵌套 JSON
                    songs = data.get('result', {}).get('songs', [])
                    
                    for song in songs:
                        # 官方搜索接口有时不带大图，给个网易云黑胶唱片保底，防止 main.py 里的 Image() 报错
                        pic_url = song.get('album', {}).get('picUrl')
                        if not pic_url:
                            pic_url = "https://p1.music.126.net/UeTuwE7pvjBpypWLudqukA==/3132508627578625.jpg"
                            
                        song_info = {
                            'id': song['id'],
                            'name': song['name'],
                            'artists': [artist['name'] for artist in song.get('artists', [])],
                            'album': song.get('album', {}).get('name', ''),
                            'album_img1v1Url': pic_url
                        }
                        result.append(song_info)
                    return result
        except Exception as e:
            print(f"网易云官方请求异常: {e}")
        return []

    async def close(self):
        await self.session.close()
