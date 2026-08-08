#!/usr/bin/env python3
"""二层 BFS 扩展：把当前图里全部未爬节点的主页爬一遍，补齐互链（不引入新圈子之外的数据源）。"""
import json, re, html as html_mod, subprocess, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
MEMBERS = {18230719, 20865377, 37684093, 35844030, 10681880, 14538142, 2192312, 38737489, 36062235}

def fetch_profile(uid):
    for attempt in range(2):
        try:
            r = subprocess.run(["curl", "-s", "-A", UA, "-m", "25", f"https://osu.ppy.sh/users/{uid}"],
                               capture_output=True, text=True, timeout=30)
            if r.returncode == 0 and r.stdout:
                return r.stdout
        except Exception:
            pass
        time.sleep(1)
    return None

def extract_collabs(html_text):
    m = re.search(r'data-initial-data="([^"]+)"', html_text)
    if not m:
        return []
    try:
        data = json.loads(html_mod.unescape(m.group(1)))
    except Exception:
        return []
    page = data.get("user", {}).get("page", {}).get("raw", "") or ""
    if not page:
        return []
    out = []
    for m2 in re.finditer(r'([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) (https://osu\.ppy\.sh/users/(\d+))(?: ([^\r\n]+))?', page):
        out.append((m2.group(6), (m2.group(7) or "").strip()))
    for m2 in re.finditer(r'\[url=https?://osu\.ppy\.sh/users/(\d+)\]([^\]]+)\[/url\]', page):
        out.append((m2.group(1), m2.group(2).strip()))
    seen, res = set(), []
    for uid, name in out:
        if uid in seen or not uid.isdigit():
            continue
        seen.add(uid)
        res.append((uid, name))
    return res

def main():
    data = json.loads((BASE / "data" / "collab_graph.json").read_text(encoding="utf-8"))
    names = {n["uid"]: n["name"] for n in data["nodes"]}
    edges = {tuple(sorted(e)) for e in data["edges"]}
    # 已爬集合：种子 9 人 + 种子图里 degree>=3 的节点（一层 BFS 的目标）
    old = json.loads((BASE / "data" / "collab_data.json").read_text(encoding="utf-8"))
    odeg = Counter()
    for uname, info in old.items():
        for c_uid, _ in info["collabs"]:
            odeg[info["uid"]] += 1; odeg[int(c_uid)] += 1
    crawled = MEMBERS | {u for u in odeg if u not in MEMBERS and odeg[u] >= 3}
    todo = [u for u in names if u not in crawled]
    print(f"start: {len(names)} nodes / {len(edges)} edges; todo: {len(todo)}")

    results = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(lambda u: (u, extract_collabs(fetch_profile(u)) if fetch_profile(u) else None), u): u for u in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            uid, collabs = fut.result()
            results[uid] = collabs or []
            if i % 50 == 0:
                print(f"  {i}/{len(todo)}")
            time.sleep(0.15)

    for uid, collabs in results.items():
        if collabs is None:
            continue
        for c_uid, c_name in collabs:
            c = int(c_uid)
            if c not in names:
                names[c] = c_name
            if c != uid:
                edges.add(tuple(sorted((uid, c))))
    print(f"final: {len(names)} nodes / {len(edges)} edges")
    (BASE / "data" / "collab_graph.json").write_text(
        json.dumps({"nodes": [{"uid": u, "name": names[u]} for u in names],
                    "edges": [list(e) for e in edges]}, ensure_ascii=False), encoding="utf-8")

if __name__ == "__main__":
    main()
