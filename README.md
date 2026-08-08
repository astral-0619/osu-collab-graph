# osu! collab 互链图

把 osu! 玩家主页用户页里的 **collab 图**（标注玩家 ID、点击可跳转到对应玩家主页的图片，imagemap）和文本互链爬下来，构建「谁主页挂了谁」的社交互链网络，并提供一个可交互浏览的网页。

在线示例：<https://astral-0619.github.io/osu-collab-graph/>（GitHub Pages 静态托管）

## 交互说明

- 点击图中任意玩家 → 右侧显示该玩家详情：真实 osu 用户名、互链数、TA 的 collab 玩家完整名单（按互链数排序）
- 点名单里任意一个 → 图自动定位并切换到该玩家，可以一直点下去互相换着看
- 玩家详情里有「打开 osu 主页」按钮
- 搜索框回车定位玩家；点空白处返回排行榜（全图枢纽 Top50）
- 节点大小 = 互链数；颜色 = 社区（Louvain 聚类）

## 数据来源

osu! 玩家主页用户页（profile page 的 raw BBCode，藏在页面 `data-initial-data` JSON 里）。两种互链：

1. **imagemap 行**：`x y w h https://osu.ppy.sh/users/UID 名字` —— collab 图上每个格子对应一个玩家
2. **文本链接**：`[url=https://osu.ppy.sh/users/UID]名字[/url]`

图语义：**A 的主页挂了 B 的链接 → 一条无向边**。互链数 = 主页挂链数（出度），不代表双向互认。

## 制作过程

1. **种子（2026-08-06）**：爬 9 个群友主页的互链 → 171 节点 / 290 边（`data/collab_data.json`）。9 个种子账号：
   - `18230719` ZnCookie（群主）
   - `20865377` oines
   - `37684093` Sakuraba Ruri（LadyEvil）
   - `35844030` faweidao（乏味道）
   - `10681880` Kaffu-
   - `14538142` ScarletRemilia-（suzuri）
   - `2192312` Shimakaze
   - `38737489` XiaFeng
   - `36062235` 21awa12
2. **一层 BFS（2026-08-08）**：从种子图挑互链数 ≥3 的 42 个节点，爬它们的主页补链接 → 482 节点 / 1882 边
3. **二层 BFS（2026-08-08）**：把图里剩余 430 个未爬节点全部爬一遍（6 并发，0 失败），补齐互链 → 973 节点 / 3958 边
4. **数据清洗**：
   - 脏标签修复：个别页面 imagemap 行缺名字，正则会把坐标+URL 抓成名字 → 从 URL 解析真实 uid 重新查名
   - 垃圾节点清理：uid 0/5 等解析产物删除 → 971 节点 / 3951 边 / 14 社区
   - **真实用户名校验**：collab 图标注名 ≠ osu 真实用户名的情况有 213 处（如 `Shu1Ace` 真名 `MyAngelChino`、`Mizuha` 实为 `ScarletRemilia-`）→ 用 osu! API v2 批量解析（50/请求），节点统一显示真实用户名，原标注名保留为 `alt` 字段在详情页展示

## 扩散记录

| 阶段 | 时间 | 节点 | 边 | 社区 | 说明 |
|---|---|---|---|---|---|
| 种子 | 2026-08-06 | 171 | 290 | 7 | 9 群友主页互链 |
| 一层 BFS | 2026-08-08 | 482 | 1882 | 10 | +42 个高互链节点 |
| 二层 BFS | 2026-08-08 | 973 | 3958 | 13 | +430 全量补爬，0 失败 |
| 清洗后 | 2026-08-08 | 971 | 3951 | 14 | 脏标签修复 + 垃圾节点清理 + 真名校验 |

> 为什么停在二层：再扩一层会把大量海外玩家卷进来，图从「国内映射圈」变成「国际 osu 社交网」，失去聚焦意义。

## 运行

```bash
# 1. 重新爬取（可选，已有数据在 data/ 下）
python3 scripts/crawl_collab.py          # 种子
python3 scripts/crawl_collab_depth2.py   # 二层 BFS

# 2. 真名校验（需要 osu! API v2 凭据）
export OSU_CLIENT_ID=xxx OSU_CLIENT_SECRET=xxx
python3 scripts/resolve_usernames.py

# 3. 生成前端数据
python3 scripts/generate_web_data.py

# 4. 起服务
cd web && python3 -m http.server 8000
```

依赖：`python3`、`networkx`、`python-louvain`（社区检测）、`curl`；前端为自包含静态页（vis-network 已 vendored，无 CDN 依赖）。

## 局限

- 互链数 = 主页挂链数（出度），非双向互认
- 9 个 restricted/删号账号无法通过 API 解析，保留 collab 图标注名
- 边按无向处理；collab 图上标注名可能与真名不一致（已尽力用 API 校验）

## License

MIT
