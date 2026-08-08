#!/usr/bin/env python3
"""用 osu! API v2 批量校验全部节点为真实用户名（collab 图标注名可能与真名不同）。
需要环境变量 OSU_CLIENT_ID / OSU_CLIENT_SECRET（osu! 官网申请 client_credentials）。"""
import json, os, sys, time, urllib.parse, urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

def get_token(cid, sec):
    body = urllib.parse.urlencode({"client_id": cid, "client_secret": sec,
                                   "grant_type": "client_credentials", "scope": "public"})
    req = urllib.request.Request("https://osu.ppy.sh/oauth/token", data=body.encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "osu-collab-graph/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["access_token"]

def main():
    cid = os.environ["OSU_CLIENT_ID"]
    sec = os.environ["OSU_CLIENT_SECRET"]
    tok = get_token(cid, sec)
    path = BASE / "data" / "collab_graph.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    uids = [n["uid"] for n in data["nodes"]]
    real = {}
    for i in range(0, len(uids), 50):
        qs = urllib.parse.urlencode([("ids[]", u) for u in uids[i:i+50]])
        req = urllib.request.Request("https://osu.ppy.sh/api/v2/users?" + qs,
            headers={"Authorization": "Bearer " + tok, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                for u in json.load(r)["users"]:
                    real[u["id"]] = u["username"]
        except Exception:
            pass
        time.sleep(0.2)
    diff = 0
    for n in data["nodes"]:
        r = real.get(n["uid"])
        if r and r != n["name"]:
            diff += 1
            n["alt"] = n.get("alt") or n["name"]  # 保留 collab 图标注
            n["name"] = r
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"resolved {len(real)}/{len(uids)}, {diff} labels corrected")

if __name__ == "__main__":
    main()
