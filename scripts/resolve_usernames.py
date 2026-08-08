#!/usr/bin/env python3
"""用 osu! API v2 批量解析节点 uid → 当前玩家名，持久化到 data/name_map.json。
节点标签统一用玩家名（collab 图 bbcode 标注名只作为 alt 保留）。
已知坑：API 对正常用户间歇性 404/SSL EOF（缓存抽风）→ 批次重试 3 次；
持续 404 的（封禁号）回退爬网页版 data-initial-data 拿用户名。"""
import json, os, sys, time, urllib.parse, urllib.request, urllib.error, re, html as html_mod
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
NAME_MAP = BASE / "data" / "name_map.json"

def get_token(cid, sec):
    body = urllib.parse.urlencode({"client_id": cid, "client_secret": sec,
                                   "grant_type": "client_credentials", "scope": "public"})
    req = urllib.request.Request("https://osu.ppy.sh/oauth/token", data=body.encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "osu-collab-graph/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)["access_token"]

def fetch_batch(uids, tok):
    qs = urllib.parse.urlencode([("ids[]", u) for u in uids])
    req = urllib.request.Request("https://osu.ppy.sh/api/v2/users?" + qs,
        headers={"Authorization": "Bearer " + tok, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return {u["id"]: u["username"] for u in json.load(r)["users"]}

def fetch_page_username(uid):
    req = urllib.request.Request(f"https://osu.ppy.sh/users/{uid}",
        headers={"User-Agent": "osu-collab-graph/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        body = r.read().decode("utf-8", "ignore")
    m = re.search(r'data-initial-data="([^"]+)"', body)
    if not m:
        return None
    try:
        return json.loads(html_mod.unescape(m.group(1)))["user"]["username"]
    except Exception:
        return None

def main():
    cid, sec = None, None
    env_file = BASE.parent / ".osu_api.env" if False else None
    for f in [env_file, Path("/workspace/.osu_api.env")]:
        if f and f.exists():
            env = {}
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
            cid = cid or env.get("OSU_CLIENT_ID")
            sec = sec or env.get("OSU_CLIENT_SECRET")
    cid = cid or os.environ.get("OSU_CLIENT_ID")
    sec = sec or os.environ.get("OSU_CLIENT_SECRET")
    if not cid or not sec:
        sys.exit("ERROR: no OSU_CLIENT_ID / OSU_CLIENT_SECRET")
    tok = get_token(cid, sec)

    graph = json.loads((BASE / "data" / "collab_graph.json").read_text(encoding="utf-8"))
    uids = sorted({n["uid"] for n in graph["nodes"]})
    old_map = json.loads(NAME_MAP.read_text(encoding="utf-8")) if NAME_MAP.exists() else {}
    todo = [u for u in uids if u not in old_map]
    print(f"共 {len(uids)} 个 uid，已有 {len(uids)-len(todo)} 个缓存，需解析 {len(todo)} 个")

    real = dict(old_map)
    pending = todo
    for attempt in range(3):
        if not pending:
            break
        next_pending = []
        for i in range(0, len(pending), 50):
            batch = pending[i:i+50]
            try:
                real.update(fetch_batch(batch, tok))
                print(f"  批次 {i//50+1}/{len(pending)//50+1} OK ({len(batch)} 个)", flush=True)
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    tok = get_token(cid, sec)
                    next_pending.extend(batch)
                elif e.code == 404:
                    next_pending.extend(batch)  # 可能间歇 404，下一轮重试
                else:
                    print(f"  批次 HTTP {e.code}，加入重试", flush=True)
                    next_pending.extend(batch)
            except Exception as e:
                print(f"  批次异常 {e}，加入重试", flush=True)
                next_pending.extend(batch)
            time.sleep(0.3)
            NAME_MAP.write_text(json.dumps(real, ensure_ascii=False), encoding="utf-8")
        pending = next_pending
        print(f"第 {attempt+1} 轮结束，剩余 {len(pending)} 个", flush=True)
        time.sleep(2)

    # 仍失败的：爬网页版拿用户名（封禁号 API 持续 404 但网页有名字）
    for uid in list(pending):
        try:
            name = fetch_page_username(uid)
            if name:
                real[uid] = name
                pending.remove(uid)
                print(f"  网页回退 {uid} -> {name}", flush=True)
        except Exception as e:
            print(f"  网页回退 {uid} 失败: {e}", flush=True)
        time.sleep(0.8)

    NAME_MAP.write_text(json.dumps(real, ensure_ascii=False), encoding="utf-8")
    print(f"完成: name_map 现有 {len(real)}/{len(uids)}，未解析 {len(pending)}: {pending[:20]}")

if __name__ == "__main__":
    main()
