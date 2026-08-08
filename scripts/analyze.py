#!/usr/bin/env python3
"""统一分析模块：一次 import，常用查询全有。
用法示例:
  python3 analyze.py profile 20865377     # 玩家完整档案
  python3 analyze.py heat [top_n]         # 热度分榜（单步份额）
  python3 analyze.py community <uid>      # 社区信息
  python3 analyze.py compare <uid> <uid>  # 两人互链详情
  python3 analyze.py team <name>          # 战队成员列表
"""
import json, sys
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def load():
    g = json.loads((BASE / "data" / "collab_graph.json").read_text(encoding="utf-8"))
    nm = json.loads((BASE / "data" / "name_map.json").read_text(encoding="utf-8"))
    tm = {}
    f = BASE / "data" / "team_map.json"
    if f.exists():
        tm = json.loads(f.read_text(encoding="utf-8"))
    cm = {}
    f = BASE / "data" / "country_map.json"
    if f.exists():
        cm = json.loads(f.read_text(encoding="utf-8"))
    return g, nm, tm, cm


def outbound():
    ob = defaultdict(lambda: defaultdict(int))
    for line in (BASE / "data" / "collab_lists.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r.get("code") != "200":
            continue
        u = r["uid"]
        for c_uid, _ in r["imgs"] + r["urls"]:
            if c_uid != u:
                ob[u][c_uid] += 1
    return ob


def heat():
    """单步份额热度分：挂你的人把 TA 的份额分给你。"""
    g, nm, tm, cm = load()
    ob = outbound()
    out_w = {u: sum(ob[u].values()) for u in ob}
    A = defaultdict(float)
    for p, partners in ob.items():
        if out_w[p] == 0:
            continue
        for u, w in partners.items():
            A[u] += w / out_w[p]
    names = {n["uid"]: n["name"] for n in g["nodes"]}
    return A, names


def profile(uid, topn=8):
    g, nm, tm, cm = load()
    names = {n["uid"]: n["name"] for n in g["nodes"]}
    node = next((n for n in g["nodes"] if n["uid"] == uid), None)
    if not node:
        return {"error": f"uid {uid} 不在图里"}
    out = dict(node)
    out["name"] = nm.get(str(uid)) or out["name"]
    out["team"] = tm.get(str(uid))
    out["country"] = cm.get(str(uid))
    wmap = {}
    for e in g["edges"]:
        a, b, w = e
        if a == uid:
            wmap[b] = w
        elif b == uid:
            wmap[a] = w
    out["top_links"] = [(names.get(u, str(u)), w) for u, w in
                        sorted(wmap.items(), key=lambda x: -x[1])[:topn]]
    A, _ = heat()
    rank = sorted(A, key=lambda u: -A[u])
    out["heat_rank"] = next((i + 1 for i, u in enumerate(rank) if u == uid), None)
    return out


def community(uid):
    g, nm, tm, cm = load()
    try:
        import community as community_louvain
        import networkx as nx
    except ImportError:
        return {"error": "需要 networkx + python-louvain"}
    G = nx.Graph()
    for n in g["nodes"]:
        G.add_node(n["uid"])
    for a, b, w in g["edges"]:
        G.add_edge(a, b, weight=w)
    part = community_louvain.best_partition(G, random_state=42)
    names = {n["uid"]: n["name"] for n in g["nodes"]}
    c = part[uid]
    members = [u for u in G.nodes() if part[u] == c]
    top = sorted(members, key=lambda u: -G.degree(u))[:6]
    return {"community": c, "size": len(members),
            "cores": [names.get(u, str(u)) for u in top],
            "degree": G.degree(uid)}


def team(name):
    g, nm, tm, cm = load()
    names = {n["uid"]: n["name"] for n in g["nodes"]}
    q = name.lower()
    return [{"uid": u, "name": names.get(u, str(u))} for u, t in tm.items()
            if t and q in str(t).lower()]


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "heat"
    if cmd == "profile":
        p = profile(int(sys.argv[2]))
        print(json.dumps(p, ensure_ascii=False, indent=1))
    elif cmd == "heat":
        A, names = heat()
        topn = int(sys.argv[2]) if len(sys.argv) > 2 else 15
        for i, u in enumerate(sorted(A, key=lambda u: -A[u])[:topn], 1):
            print(f"{i:2d}. {names.get(u, u):<24} 热度={A[u]*100:7.2f}")
    elif cmd == "community":
        print(json.dumps(community(int(sys.argv[2])), ensure_ascii=False, indent=1))
    elif cmd == "team":
        for m in team(sys.argv[2]):
            print(m["uid"], m["name"])
