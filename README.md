# lifebuddy

AstrBot 插件：生活好基友。给做谱群 / 玩家群用。

| 触发 | 行为 |
|------|------|
| `/help` / `/help rbdx` | 总表 / 某一条用法 |
| `/ask 问题 选项A 选项B …` | 帮你选，不问算法 |
| `/左对称` `/右对称` `/上对称` `/下对称` | 回复图片做对称；单独发就对头像；动图逐帧 |
| `/倒放` | 动图倒放 |
| `/rbdx` / `/rbdx 12` | 随机自制谱，可选指定 B/M/H 等级 |
| `/rbdx arcade ryu` | 随机一首街机里带 ryu 的谱，可再加等级 |
| `/rbdx test 12` / `/rbdx test_all` | 内测 / 全部内测（要填 `wip_group_ids`） |
| `/rb song 关键词` | 自制 / 街机分组；开了内测群再加内测和英国人谱面；只中一首带夹克 |
| `/rb song arcade 关键词` | 只搜某一类（custom / arcade / test / test_all） |
| `/rb alias add 鸡犬 500100992` | 加别名（SongID 或图片 URL） |
| `来首XXX` | 搜网易云，回封面 + 曲名/艺术家/专辑/链接 |
| `YYY是什么歌` | 查群梗夹克 |
| `/nick 上帝` | QQ→称呼 |
| `/dib` | 看自己口香了几天 |
| `/dib <曲名或SongID>` | 口香一首，占了不能吐 |
| `/dib list` | 本群口香列表 |
| `/rb bind <四位数字>` | 绑游戏账号（四位用户ID，须唯一） |
| `/rb who` | 看自己绑的号 |
| `/rb unbind` | 管理员解绑 |
| `/advice` | 审核列表（带编号；管理页 `advice_group_ids` 开群） |
| `/advice <编号或SongID> [0\|1] [正文]` | 写评（1/ok 可空，默认 ok.；0/ng 必须写评） |
| `/fight` | 打架谱面列表（按谱面编号，不是按歌） |
| `/fight <编号> <展示值>` | 投票 |

QQ / 称呼 / 口香 / 绑号在 SQLite：`data/plugin_data/lifebuddy/lifebuddy.db`。大肥鱼每轮只看到当前发言者的 `QQ + 称呼`。

`/advice` 默认全关，在 AstrBot 插件管理页把群号填进 `advice_group_ids`。`/rbdx test` 同理，填 `wip_group_ids`。
