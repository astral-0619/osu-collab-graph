#!/usr/bin/env python3
"""从 collab_lists.jsonl 计算边权重（两人互链的 collab 图数量）并合并回图数据。
- 权重 = A 主页指向 B 的 imagemap 条目数 + B 主页指向 A 的条目数（双侧证据求和）
- 仅 [url] 文本互链且无 imagemap 证据的边权重记 1
- 输出 data/edge_weights.json + 更新 data/collab_graph.json（nodes 加 total_links，edges 加 weight）
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

def main():
    graph = json.loads((BASE / "data" / "collab_graph.json").read_text(encoding="utf-8"))
    nodes = {n["uid"]: n for n in graph["nodes"]}
    edges = [tuple(sorted((e[0], e[1]))) for e in graph["edges"]]

    outbound = defaultdict(Counter)   # uid -> {partner_uid: count}（imagemap 条目数）
    url_only = defaultdict(Counter)   # uid -> {partner_uid: count}（[url] 文本链接）
    have_list = set()
    for line in (BASE / "data" / "collab_lists.jsonl").read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        uid = rec["uid"]
        have_list.add(uid)
        for c_uid, _name in rec["imgs"]:
            if c_uid != uid:
                outbound[uid][c_uid] += 1
        for c_uid, _name in rec["urls"]:
            if c_uid != uid:
                url_only[uid][c_uid] += 1

    weight = {}
    evidence = {}
    for a, b in edges:
        w = outbound.get(a, {}).get(b, 0) + outbound.get(b, {}).get(a, 0)
        if w == 0:
            u = url_only.get(a, {}).get(b, 0) + url_only.get(b, {}).get(a, 0)
            w = 1 if u > 0 else 1  # 图中存在的边默认权重 1（至少一侧有链接）
        weight[(a, b)] = w

    # 节点统计：与邻居的 collab 总次数 + 双向合作人数
    for n in graph["nodes"]:
        n["total_links"] = 0
        n["mutual_count"] = 0
    for a, b in edges:
        w = weight[(a, b)]
        nodes[a]["total_links"] += w
        nodes[b]["total_links"] += w
        if w >= 2:
            nodes[a]["mutual_count"] += 1
            nodes[b]["mutual_count"] += 1

    wsum = sum(weight.values())
    maxw = max(weight.values())
    print(f"edges: {len(edges)} / weight sum: {wsum} / max: {maxw} / >=2: {sum(1 for w in weight.values() if w >= 2)}")
    dist = Counter(weight.values())
    print("weight dist:", dict(sorted(dist.items())))
    missing = sorted(u for u in nodes if u not in have_list)
    print("nodes without list:", len(missing), missing[:10])

    (BASE / "data" / "edge_weights.json").write_text(
        json.dumps({f"{a}:{b}": w for (a, b), w in sorted(weight.items())}, ensure_ascii=False, indent=0),
        encoding="utf-8")
    for e, w in zip(graph["edges"], (weight[tuple(sorted((e[0], e[1])))] for e in graph["edges"])):
        e.append(w)
    (BASE / "data" / "collab_graph.json").write_text(
        json.dumps(graph, ensure_ascii=False), encoding="utf-8")
    print("saved edge_weights.json + collab_graph.json (edges now [u, v, weight])")

if __name__ == "__main__":
    main()
