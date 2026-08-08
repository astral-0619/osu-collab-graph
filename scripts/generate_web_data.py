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
        G.add_node(n["uid"], name=n["name"], alt=n.get("alt"))
    for u, v in data["edges"]:
        G.add_edge(u, v)
    partition = community_louvain.best_partition(G, random_state=42)
    comm_count = len(set(partition.values()))
    comm_color = {c: PALETTE[c % len(PALETTE)] for c in range(comm_count)}
    nodes_out = [{"id": uid, "label": attr["name"] or str(uid), "alt": attr.get("alt"),
                  "value": G.degree(uid), "group": partition[uid],
                  "color": comm_color[partition[uid]], "degree": G.degree(uid)}
                 for uid, attr in G.nodes(data=True)]
    top = sorted([(n, G.degree(n)) for n in G.nodes()], key=lambda x: -x[1])[:50]
    js = {
        "nodes": nodes_out,
        "edges": [{"from": u, "to": v} for u, v in G.edges()],
        "stats": {"nodes": len(nodes_out), "edges": len(G.edges()), "communities": comm_count},
        "topHubs": [{"name": G.nodes[n]["name"] or str(n), "deg": d} for n, d in top],
        "commColors": {str(c): comm_color[c] for c in range(comm_count)},
    }
    out = BASE / "docs" / "graph_data.js"
    out.write_text("window.GRAPH_DATA = " + json.dumps(js, ensure_ascii=False) + ";", encoding="utf-8")
    print(f"generated web/graph_data.js: {len(nodes_out)} nodes / {len(G.edges())} edges / {comm_count} comms")

if __name__ == "__main__":
    main()
