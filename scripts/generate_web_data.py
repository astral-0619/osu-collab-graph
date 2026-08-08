#!/usr/bin/env python3
"""社区检测 + 生成前端 graph_data.js（web/ 目录，供 vis-network 页面使用）。"""
import json
from pathlib import Path

import community as community_louvain
import networkx as nx

BASE = Path(__file__).resolve().parent.parent
PALETTE = ["#4e79a7","#f28e2b","#e15759","#76b7b2","#59a14f","#edc948","#b07aa1",
           "#ff9da7","#9c755f","#bab0ac","#86bcb6","#d37295","#a0cbe8","#f1ce63",
           "#ffbe7d","#8cd17d","#b6992d","#499894","#86bcb6","#e6ab02","#a6761d"]

def main():
    data = json.loads((BASE / "data" / "collab_graph.json").read_text(encoding="utf-8"))
    G = nx.Graph()
    for n in data["nodes"]:
        G.add_node(n["uid"], name=n["name"], alt=n.get("alt"),
                   total_links=n.get("total_links", 0), mutual_count=n.get("mutual_count", 0))
    for e in data["edges"]:
        u, v = e[0], e[1]
        w = e[2] if len(e) > 2 else 1
        G.add_edge(u, v, weight=w)
    partition = community_louvain.best_partition(G, random_state=42)
    comm_count = len(set(partition.values()))
    comm_color = {c: PALETTE[c % len(PALETTE)] for c in range(comm_count)}
    nodes_out = [{"id": uid, "label": attr["name"] or str(uid), "alt": attr.get("alt"),
                  "value": G.degree(uid), "group": partition[uid],
                  "color": comm_color[partition[uid]], "degree": G.degree(uid),
                  "total_links": attr.get("total_links", 0), "mutual_count": attr.get("mutual_count", 0)}
                 for uid, attr in G.nodes(data=True)]
    # Top50 榜：先按累计 collab 张数降序，再按 collab 玩家数降序
    top = sorted(G.nodes(), key=lambda n: (-G.nodes[n].get("total_links", 0), -G.degree(n)))[:50]
    edge_data = []
    weights = []
    for u, v, a in G.edges(data=True):
        w = a.get("weight", 1)
        weights.append(w)
        edge_data.append({"from": u, "to": v, "w": w})
    js = {
        "nodes": nodes_out,
        "edges": edge_data,
        "stats": {"nodes": len(nodes_out), "edges": len(G.edges()), "communities": comm_count,
                  "maxWeight": max(weights) if weights else 1,
                  "mutualEdges": sum(1 for w in weights if w >= 2)},
        "topHubs": [{"name": G.nodes[n]["name"] or str(n), "deg": G.degree(n),
                     "links": G.nodes[n].get("total_links", 0)} for n in top],
        "commColors": {str(c): comm_color[c] for c in range(comm_count)},
    }
    out = BASE / "docs" / "graph_data.js"
    out.write_text("window.GRAPH_DATA = " + json.dumps(js, ensure_ascii=False) + ";", encoding="utf-8")
    print(f"generated web/graph_data.js: {len(nodes_out)} nodes / {len(G.edges())} edges / {comm_count} comms")

if __name__ == "__main__":
    main()
