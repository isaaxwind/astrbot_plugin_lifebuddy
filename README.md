# lifebuddy

AstrBot 插件：生活好基友。给做谱群 / 玩家群用。

| 触发 | 行为 |
|------|------|
| `/ask 问题 选项A 选项B …` | CRC32 伪随机百分比建议 |
| `/rbdx` / `/rbdx 12` | 随机自制谱，可选指定 B/M/H 等级 |
| `/rbdx arcade` / `/rbdx test 12` | 随机街机谱 / 内测谱（test 走 `test_inner`，要填 `wip_group_ids`） |
| `/rbdx test_all` | 全部内测谱（`type=test`，含 Mendes） |
| `/rb song 关键词` | 按自制 / 街机 / 内测分组列出（含谱师；内测要填 `wip_group_ids`） |
| `来首XXX` | 搜网易云，回封面 + 曲名/艺术家/专辑/链接 |
| `YYY是什么歌` | 查群梗夹克 |
| `/nick 上帝` | QQ→称呼 |
| `/dib <曲名或SongID>` | 占坑，占了不能弃 |
| `/rb bind <四位数字>` | 绑游戏账号（四位用户ID，须唯一） |
| `/rb who` | 看自己绑的号 |
| `/rb unbind` | 管理员解绑 |
| `/advice` | 审核列表（带编号；管理页 `advice_group_ids` 开群） |
| `/advice <编号或SongID> [0\|1] 正文` | 看评 / 写评（1过 0要改，也认 ok/ng） |
| `/fight` | 打架谱面列表（按谱面编号，不是按歌） |
| `/fight <编号> <展示值>` | 投票 |

QQ / 称呼 / 占坑 / 绑号在 SQLite：`data/plugin_data/lifebuddy/lifebuddy.db`。大肥鱼每轮只看到当前发言者的 `QQ + 称呼`。

`/advice` 默认全关，在 AstrBot 插件管理页把群号填进 `advice_group_ids`。`/rbdx test` 同理，填 `wip_group_ids`。
