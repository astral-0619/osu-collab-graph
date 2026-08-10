#!/usr/bin/env python3
"""全量重建图：以 collab_lists.jsonl（code=200）为唯一权威来源。
- 边 = 任一方向被列表引用（imagemap + [url]），权重 = 双方 imagemap 条目数之和；纯 [url] 记 1
- 节点 = 所有出现在列表里的 uid + 9 个种子（种子即使 0 度也保留）
- 旧图里未被新列表支持的边/节点丢弃（新爬虫完整覆盖，旧边无支持视为过时或噪声）
- 过滤占位 uid（<=1000）
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SEEDS = {18230719, 20865377, 37684093, 35844030, 10681880, 14538142, 2192312, 38737489, 36062235}

def main():
    old = json.loads((BASE / "data" / "collab_graph.json").read_text(encoding="utf-8"))
    old_names = {n["uid"]: n["name"] for n in old["nodes"]}
    old_alts = {n["uid"]: n.get("alt") for n in old["nodes"] if n.get("alt")}
    # uid → 当前玩家名（API 解析的权威标签）。规则（oines 2026-08-08 钦定）：
    # 节点标签必须用 osu 玩家名，bbcode 标注名不作任何参考（连 alt 都不留）。
    name_map = {}
    nf = BASE / "data" / "name_map.json"
    if nf.exists():
        name_map = json.loads(nf.read_text(encoding="utf-8"))
    # 维度注册表：data/<field>_map.json 自动附加为节点属性（name_map 除外，它是标签）
    dims = {}
    for mf in (BASE / "data").glob("*_map.json"):
        field = mf.name[: -len("_map.json")]
        if field == "name":
            continue
        dims[field] = json.loads(mf.read_text(encoding="utf-8"))

    outbound = defaultdict(Counter)   # imagemap 计数
    url_only = defaultdict(Counter)   # [url] 文本链接
    names_seen = {}
    codes = Counter()
    recs200 = {}
    for line in (BASE / "data" / "collab_lists.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        codes[rec.get("code")] += 1
        if rec.get("code") == "200":
            # 同一 uid 多次爬取：保留最新一条（页面内容可能更新），避免边权重翻倍
            recs200[rec["uid"]] = rec
    for u, rec in recs200.items():
        for c_uid, c_name in rec["imgs"]:
            if c_uid != u:
                outbound[u][c_uid] += 1
                names_seen.setdefault(c_uid, "")
                if c_name and not names_seen[c_uid]:
                    names_seen[c_uid] = c_name
        for c_uid, c_name in rec["urls"]:
            if c_uid != u:
                url_only[u][c_uid] += 1
                names_seen.setdefault(c_uid, "")
                if c_name and not names_seen[c_uid]:
                    names_seen[c_uid] = c_name

    # 边 + 权重
    weight = {}
    for u, partners in outbound.items():
        for p in partners:
            w = outbound[u][p] + outbound.get(p, {}).get(u, 0)
            if w == 0:
                w = 1 if (url_only[u][p] + url_only.get(p, {}).get(u, 0)) > 0 else 1
            weight[tuple(sorted((u, p)))] = w
    for u, partners in url_only.items():
        for p in partners:
            key = tuple(sorted((u, p)))
            weight.setdefault(key, 1)

    # 节点：列表成员 + 种子
    uids = set(names_seen) | set(outbound) | set(url_only) | SEEDS
    nodes = {}
    for u in uids:
        real = name_map.get(str(u)) or ""
        nd = {
            "uid": u,
            "name": real or str(u),  # 只有玩家名；解析不到的显示 uid（不用标注名）
            "total_links": 0,
            "mutual_count": 0,
        }
        for field, m in dims.items():
            v = m.get(str(u))
            if v:
                nd[field] = v
        nodes[u] = nd

    for a, b in weight:
        w = weight[(a, b)]
        nodes[a]["total_links"] += w
        nodes[b]["total_links"] += w
        if w >= 2:
            nodes[a]["mutual_count"] += 1
            nodes[b]["mutual_count"] += 1

    graph = {"nodes": [nodes[u] for u in sorted(nodes)],
             "edges": [list(e) + [weight[e]] for e in sorted(weight)]}
    (BASE / "data" / "collab_graph.json").write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")

    dist = Counter(weight.values())
    print(f"codes: {dict(codes)}")
    print(f"nodes: {len(nodes)} (旧 {len(old['nodes'])}) / edges: {len(weight)} (旧 {len(old['edges'])})")
    print(f"双向(>=2): {sum(1 for w in weight.values() if w >= 2)} / max: {max(weight.values())}")
    print(f"weight dist: {dict(sorted(dist.items()))}")
    print("saved collab_graph.json")

if __name__ == "__main__":
    main()
