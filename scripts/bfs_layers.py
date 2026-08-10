#!/usr/bin/env python3
"""从最终数据反推 BFS 每层扩散集合（不依赖 git 历史）。
用法: python3 scripts/bfs_layers.py [--json]
输入: data/collab_lists.jsonl（全量出链）+ 种子 uid（crawl_collab.py 的 MEMBERS）
输出: 每层 {层号: 源数, 新节点数, 累计}；--json 输出完整分层 JSON 到 stdout
"""
import json, sys
from collections import defaultdict

BASE = __import__("pathlib").Path(__file__).resolve().parent.parent
SEEDS = {
    18230719, 20865377, 37684093, 35844030,
    10681880, 14538142, 2192312, 38737489, 36062235,
}

def load_outbound():
    out = defaultdict(set)
    for line in open(BASE / "data" / "collab_lists.jsonl"):
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("code") != "200":
            continue
        src = rec["uid"]
        for c_uid, _ in rec.get("imgs", []) + rec.get("urls", []):
            out[src].add(c_uid)
    return out

def layers(out, seeds):
    known = set(seeds)
    result = []
    frontier = set(seeds)
    for depth in range(1, 20):
        new = set()
        for s in frontier:
            new |= out.get(s, set())
        new -= known
        result.append({"layer": depth, "frontier": len(frontier),
                       "new_nodes": len(new), "cumulative": len(known | new)})
        if not new:
            break
        known |= new
        frontier = new
    return result

if __name__ == "__main__":
    out = load_outbound()
    ls = layers(out, SEEDS)
    if "--json" in sys.argv:
        print(json.dumps({"seeds": sorted(SEEDS), "layers": ls}, indent=1))
    else:
        print(f"种子 {len(SEEDS)} 个 / 总源 {len(out)}")
        for l in ls:
            print(f"层{l['layer']}: 源 {l['frontier']} -> 新节点 {l['new_nodes']} (累计 {l['cumulative']})")
