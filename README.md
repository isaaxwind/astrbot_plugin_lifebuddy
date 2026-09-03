# lifebuddy

AstrBot 插件：生活好基友。给做谱群 / 玩家群用。

| 触发 | 行为 |
|------|------|
| `/help` / `/help rbdx` | 总表 / 某一条用法 |
| `/ask 问题 选项A 选项B …` | 帮你选，不问算法 |
| `/rbdx` / `/rbdx 12` | 随机自制谱，可选指定 B/M/H 等级 |
| `/rbdx arcade ryu` | 管理群：随机一首街机里带 ryu 的谱；街机不显示谱师 |
| `/rbdx test 12` / `/rbdx test_all` | 管理群+内测群：内测 / 全部内测 |
| `/rb song 关键词` | 外面只搜自制；管理群才加街机，内测群再加内测和英国人谱面 |
| `/rb song arcade 关键词` | 管理群才能指定 arcade / test / 英国人 |
| `/rb alias add 鸡犬 500100992` | 加别名（SongID 或图片 URL） |
| `来首XXX` | 搜网易云；带图直接回未找到，原图留在原位置 |
| `YYY是什么歌` | 查群梗；自制谱回夹克，remywiki 先试抓图失败再回链接 |
| `/nick 上帝` | QQ→称呼 |
| `/dib` | 看自己口香了几天 |
| `/dib <曲名或SongID>` | 口香一首，占了不能吐 |
| `/dib list` | 本群口香列表 |
| `/rb bind` | 一对一；管理群可直接绑，外面请私聊并带密码；ID 或用户名都可以 |
| `/rb who` | 看自己绑的号 |
| `/rb recent` / `/rb r` | 先 @ 发消息的人，再封面 + 曲名/作者 + 难度 + score + AR + 评级 |
| `/rb who <昵称/QQ/@>` | 反查 QQ 再看别人绑的号 |
| `/rb unbind` | 管理员解绑 |
| `/advice` | 审核列表（带编号；管理页 `advice_group_ids` 开群） |
| `/advice <编号或SongID> [0\|1] [正文]` | 写评（1/ok 可空，默认 ok.；0/ng 必须写评） |
| `/fight` | 打架谱面列表（按谱面编号，不是按歌） |
| `/fight <编号> <展示值>` | 投票 |

QQ / 称呼 / 口香 / 绑号在 SQLite：`data/plugin_data/lifebuddy/lifebuddy.db`。大肥鱼每轮只看到当前发言者的 `QQ + 称呼`。

`/advice` 默认全关，在 AstrBot 插件管理页把群号填进 `advice_group_ids`。`/rbdx test` 同理，填 `wip_group_ids`。街机和群内绑号只给管理群，填 `admin_group_ids`；不填则回退审核群+内测群。
