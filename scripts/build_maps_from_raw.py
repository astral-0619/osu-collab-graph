#!/usr/bin/env python3
"""从 data/profiles_raw/*.json.gz（主页完整 user JSON）重建/扩展维度 map。
覆盖: name_map / country_map / team_map / stats_map（4 模式）+ 打印缺失统计。
raw 数据优先覆盖旧值；raw 没有的保留旧值。之后跑 fetch_dimension.py 只补缺失（断点续传）。
用法: python3 scripts/build_maps_from_raw.py
"""
import json, gzip
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
RAW = BASE / "data" / "profiles_raw"


def load(fn):
    p = BASE / "data" / fn
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def main():
    name_map, country_map, team_map, stats_map = load("name_map.json"), load("country_map.json"), load("team_map.json"), load("stats_map.json")
    missing = Counter()
    n = 0
    for p in sorted(RAW.glob("*.json.gz")):
        uid = p.stem.split(".")[0]
        try:
            with gzip.open(p, "rt", encoding="utf-8") as f:
                u = json.load(f)
        except Exception:
            missing["坏文件"] += 1
            continue
        n += 1
        if u.get("username"):
            name_map[uid] = u["username"]
        else:
            missing["无 username"] += 1
        cc = u.get("country_code")
        if cc:
            country_map[uid] = cc
        t = u.get("team")
        if isinstance(t, dict):
            team_map[uid] = t.get("name") or t.get("short_name")
        elif t is None:
            team_map.pop(uid, None)
        s = u.get("statistics") or {}
        rs = u.get("statistics_rulesets") or {}
        modes = {}
        for mode in ("osu", "taiko", "fruits", "mania"):
            m = rs.get(mode)
            if not isinstance(m, dict):
                missing[f"无 {mode} ruleset"] += 1
                continue
            modes[mode] = {
                "pp": m.get("pp"), "play_time": m.get("play_time"),
                "play_count": m.get("play_count"), "global_rank": m.get("global_rank"),
                "accuracy": m.get("hit_accuracy"), "country_rank": m.get("country_rank"),
            }
        if modes or u.get("join_date"):
            stats_map[uid] = {"modes": modes, "join_date": u.get("join_date")}
        elif not stats_map.get(uid):
            missing["无 stats"] += 1
    # 写回
    for fn, m in (("name_map.json", name_map), ("country_map.json", country_map),
                  ("team_map.json", team_map), ("stats_map.json", stats_map)):
        (BASE / "data" / fn).write_text(
            json.dumps(m, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"处理 {n} 个 raw 文件", flush=True)
    print("缺失: " + str(dict(missing) if missing else "无"), flush=True)
    print(f"name_map {len(name_map)} / country_map {len(country_map)} / team_map {len(team_map)} / stats_map {len(stats_map)}", flush=True)


if __name__ == "__main__":
    main()
