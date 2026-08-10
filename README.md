# osu! collab 全球互链图

把 osu! 玩家主页用户页里的 **collab 图**（imagemap：标注玩家、点击跳转对应主页）和文本互链爬下来，构建「谁主页挂了谁」的社交互链网络，提供可交互浏览的网页。

在线示例：<https://astral-0619.github.io/osu-collab-graph/>（GitHub Pages 静态托管）

项目从 9 个群友主页出发做 BFS 扩散，多轮迭代后自然收敛为**全球 osu! 玩家 collab 社交网络**：151 个国家 / 67 个语言圈社区（俄/英/法/中/西/葡/德/印尼/东南亚），华语圈是其中最大的单一语言主导社区。

## 当前规模（2026-08-10 第五轮 BFS）

| 指标 | 值 |
|---|---|
| 节点 | **33853** 个玩家 |
| 边 | **217772** 条（有向去重，权重=互挂次数） |
| 双向互链 | 94306（互相挂 ≥2 的） |
| 社区 | 67（Louvain，固定随机种子可复现） |
| 最大权重 | ×156（5atori ↔ Komeiji Koishi） |
| 真名校验 | 33398/33853（name_map，API v2 按 uid 解析） |
| 战队维度 | 32908 人有战队 |
| 地区维度 | 32905 人有国家码（151 国，97%） |
| raw 主页存档 | 32217 份（BBCode 原文 gzip） |

## 交互说明

- 点击图中任意玩家 → 右侧详情：真实 osu 用户名、互链数、战队、地区、**热度分**、TA 的 collab 玩家完整名单（按互链数排序）
- 点名单里任意一个 → 图自动定位并切换，可一直点下去
- 玩家详情有「打开 osu 主页」按钮；搜索框回车定位；点空白处返回排行榜（Top100）
- 节点大小 = 互链数；颜色 = 社区；支持按战队筛选

## 数据来源

osu! 玩家主页的 raw BBCode（页面 `data-initial-data` JSON）。两种互链：

1. **imagemap 行**：`x y w h https://osu.ppy.sh/users/UID 名字` —— collab 图每个格子对应一个玩家
2. **文本链接**：`[url=https://osu.ppy.sh/users/UID]名字[/url]`

图语义：**A 的主页挂了 B 的链接 → 一条无向边**。互链数 = 主页挂链数（出度），不代表双向互认。

## 制作过程

1. **种子（2026-08-06）**：爬 9 个群友主页 → 171 节点 / 290 边
2. **一层 BFS（2026-08-08）**：互链数 ≥3 的 42 个节点补爬 → 482 / 1882
3. **二层 BFS（2026-08-08）**：图内剩余节点全量补爬 → 973 / 3958
4. **全量重爬（2026-08-08）**：`crawl_collab_lists_v2.py` 限流友好爬虫（3 并发 + 429 退避 + 断点续传），爬 971 页成功 964，7 页 404 → **3732 / 15840**
5. **三轮 BFS（2026-08-09 起）**：`--bfs` 全量模式——每轮把图内新增节点（含外部引用节点）全部补爬，逐轮收敛；第五轮后 **33853 / 217772**
5. **数据清洗**：
   - 脏标签修复：imagemap 缺名行从 URL 解析真实 uid 重新查名
   - 垃圾节点清理：uid 0/5 等解析产物删除
   - **真实用户名校验**：collab 标注名 ≠ 真实用户名（如 `Shu1Ace` 真名 `MyAngelChino`）→ API v2 批量解析（50/请求），节点统一显示真实用户名

## 扩散记录

| 阶段 | 时间 | 节点 | 边 | 社区 | 说明 |
|---|---|---|---|---|---|
| 种子 | 2026-08-06 | 171 | 290 | 7 | 9 群友主页互链 |
| 一层 BFS | 2026-08-08 | 482 | 1882 | 10 | +42 高互链节点 |
| 二层 BFS | 2026-08-08 | 973 | 3958 | 13 | +430 全量补爬 |
| 清洗后 | 2026-08-08 | 971 | 3951 | 14 | 脏标签修复 + 真名校验 |
| 全量重爬 | 2026-08-08 | **3732** | **15840** | 19 | 964/971 页成功，7 个真 404（封禁/删号） |
| 第三轮 BFS | 2026-08-09 | 32967 | 214405 | 60 | 全量补爬，突破国际圈 |
| 第四轮 BFS | 2026-08-10 | 33653 | 216915 | 67 | 外部节点开始入图 |
| 第五轮 BFS | 2026-08-10 | **33853** | **217772** | 67 | 衰减收敛中（+686→+200） |

> BFS 收敛逻辑：每轮新暴露的外部节点（被挂但未爬主页）成为下一轮 todo，增量逐轮衰减（+2069→+686→+200），预计再两轮收敛在 ~3.45 万节点。

## 数据维度

节点维度全部注册在 `data/*_map.json`，merge 时自动挂载，加新维度 = 注册表一行：

| 维度 | 文件 | 覆盖 | 来源 |
|---|---|---|---|
| 真实用户名 | `name_map.json` | 33398/33853 | API v2 批量解析（50/请求） |
| 战队 | `team_map.json` | 32908/33853 | API v2 用户详情 |
| 地区 | `country_map.json` | 32905/33853 | API v2 用户详情 |
| 成绩 | `stats_map.json` | 4 模式全量 | API v2（批量 rulesets + 单用户补注册/地区排名） |
| 热度分 | `web/graph_data.js` 内联 | 3729 | 单步份额分（见下） |

**成绩维度**（`--field=stats`）：每节点 4 模式（std/taiko/ctb/mania）的 pp、游戏时间、游戏次数、全球排名、地区排名，外加注册时间。批量接口直接返回 `statistics_rulesets`（4 模式核心字段），`join_date`/`country_rank` 走单用户接口补（3 并发 + 每 100 人落盘）。

**热度分**：标准 PageRank 在大强连通块上会塌陷成均匀分布，故改用单步份额分——把挂你的人的份额分给你，被精选挂 = 高分。「一挂成名」现象：挂的人少但被大枢纽挂，热度反超张数多的人。

## 工程化（2026-08-08）

- **`fetch_dimension.py`**：通用维度抓取器。`FIELD_EXTRACT` 注册表加一行即可抓新字段，带批量 + 断点续传 + 重试。例：`python3 scripts/fetch_dimension.py --field=country`
- **`analyze.py`**：一站式分析。子命令 `profile <uid|name>`（完整档案+最铁+热度排名）、`heat [n]`（热度榜）、`community <uid>`（社区信息）、`team <名字>`（战队成员）、**`eval '<表达式>'`**（数据预载好的一行查询：`g` 图 / `names` / `tm` / `cm` / `heat` / `community` / `outbound`，随便怎么奇怪地分析）
- **`selfcheck.py`**：数据自检（命名覆盖率/孤立点/重复边/自环/新旧 diff），跑完报问题清单
- **`merge_lists_into_graph.py`**：重建管线，自动挂载所有 `*_map.json` 维度

## 运行

```bash
# 1. 重新爬取（可选，已有数据在 data/ 下）
python3 scripts/crawl_collab.py            # 种子
python3 scripts/crawl_collab_depth2.py     # 二层 BFS
python3 scripts/crawl_collab_lists_v2.py   # 全量重爬（限流友好）

# 2. 刷维度（需要 osu! API v2 凭据，见 .osu_api.env 模板）
python3 scripts/resolve_usernames.py       # 真名
python3 scripts/fetch_dimension.py --field=team      # 战队
python3 scripts/fetch_dimension.py --field=country   # 地区

# 3. 重建 + 出数据 + 自检
python3 scripts/merge_lists_into_graph.py
python3 scripts/generate_web_data.py
python3 scripts/selfcheck.py

# 4. 起服务
cd web && python3 -m http.server 8000
```

依赖：`python3`、`networkx`、`python-louvain`、`curl`；前端为自包含静态页（vis-network 已 vendored，无 CDN 依赖）。

## 局限

- 互链数 = 主页挂链数（出度），非双向互认
- **画了但没挂链接的同框人不可见**：collab 图是 imagemap，只统计挂了链接的人；图是「互链可证」的 collab 子集，真实圈子只大不小
- 爬虫会撞 osu.ppy.sh 限流（429）：v2 爬虫带退避重试 + 断点续传，失败记录保留 code 字段；合并只采用 code=200
- 46 个 restricted/删号账号 API 解析不到（网页也 404），节点显示 uid 本身
- 边按无向处理；权重 = 双方主页 imagemap 条目数之和，只有 [url] 文本互链时记 1；占位 uid（<=1000）已过滤

## License

MIT

## 数据契约（oines 钦定 2026-08-08）

- 节点标签 = osu 玩家名（API v2 按 uid 解析，持久化于 `data/name_map.json`）
- bbcode collab 标注名不作任何参考：不显示、不进 alt、不参与节点命名（仅作为边的证据来源）
- 解析不到的 uid 显示 uid 本身（绝不用标注名兜底）
- 重建管线：resolve_usernames.py（刷 name_map）→ merge_lists_into_graph.py（重建）→ generate_web_data.py（出网页数据）
