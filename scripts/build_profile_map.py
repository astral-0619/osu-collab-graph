#!/usr/bin/env python3
"""合并全量 profile 维度 → data/profile_map.json（精选分析层，raw 的轻量版）。
来源: ① data/profiles_raw/*.json.gz（BFS 爬主页的完整 user JSON）
      ② 官方 API 批量接口补缺失节点（50/批）。
提取逻辑复用 crawl_collab_lists_v2.extract_profile_from_user。
用法: python3 scripts/build_profile_map.py [--force]
"""
import json, sys, time, urllib.parse, urllib.request, gzip
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from crawl_collab_lists_v2 import extract_profile_from_user  # noqa: E402
from osu_api_lite import get_token, load_creds  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
RAW = BASE / "data" / "profiles_raw"
OUT = BASE / "data" / "profile_map.json"


def load_profiles():
    out = {}
    if RAW.exists():
        for p in RAW.glob("*.json.gz"):
            try:
                with gzip.open(p, "rt", encoding="utf-8") as f:
                    u = json.load(f)
                prof = extract_profile_from_user(u)
                if prof:
                    out[str(u["id"])] = prof
            except Exception:
                pass
    return out


def fetch_batch(uids):
    cid, sec = load_creds()
    tok = get_token(cid, sec)
    got = {}
    for i in range(0, len(uids), 50):
        batch = uids[i:i + 50]
        for attempt in range(3):
            try:
                qs = urllib.parse.urlencode([("ids[]", u) for u in batch])
                req = urllib.request.Request(
                    f"https://osu.ppy.sh/api/v2/users?{qs}",
                    headers={"Authorization": f"Bearer {tok}", "Accept": "application/json",
                             "User-Agent": "osu-collab-graph/1.0"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    users = json.load(r)
                for u in users:
                    p = extract_profile_from_user(u)
                    if p:
                        got[str(u["id"])] = p
                break
            except Exception as e:
                print(f"  batch {i//50+1} attempt {attempt+1} 失败: {e}", flush=True)
                time.sleep(10 * (attempt + 1))
        print(f"  batch {i//50+1}/{ (len(uids)+49)//50 }", flush=True)
    return got


def main():
    force = "--force" in sys.argv
    skip_api = "--skip-api" in sys.argv
    merged = load_profiles()
    if OUT.exists() and not force:
        old = json.loads(OUT.read_text(encoding="utf-8"))
        for k, v in old.items():
            merged.setdefault(k, v)

    graph = json.loads((BASE / "data" / "collab_graph.json").read_text(encoding="utf-8"))
    need = [str(n["uid"]) for n in graph["nodes"] if str(n["uid"]) not in merged]
    print(f"raw/旧 map 已有 {len(merged)}，图节点 {len(graph['nodes'])}，需 API 补 {len(need)}",
          flush=True)
    if need and not skip_api:
        merged.update(fetch_batch(need))
    elif need:
        print(f"跳过 API 兜底（--skip-api），{len(need)} 个节点无 profile", flush=True)

    OUT.write_text(json.dumps(merged, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    have_keys = {k for v in merged.values() for k in v if v.get(k) is not None}
    n_wiki = sum(1 for v in merged.values() if v.get("previous_usernames"))
    n_team = sum(1 for v in merged.values() if v.get("team"))
    n_badges = sum(1 for v in merged.values() if v.get("badges"))
    print(f"profile_map.json 写入 {len(merged)} 人 / 有字段: {sorted(have_keys)}", flush=True)
    print(f"  曾用名 {n_wiki} / 战队 {n_team} / 徽章 {n_badges}", flush=True)


if __name__ == "__main__":
    main()
