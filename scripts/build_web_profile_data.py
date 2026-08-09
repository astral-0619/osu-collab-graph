#!/usr/bin/env python3
"""生成前端详情数据 docs/profile_data.js（懒加载，点击玩家时展示新维度）。
从 profiles_raw 提取精选：曾用名/称号/徽章/社交/粉丝/最高排名/pp 曲线(降采样)/小作文摘要。
用法: python3 scripts/build_web_profile_data.py
"""
import json, gzip
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
RAW = BASE / "data" / "profiles_raw"
OUT = BASE / "docs" / "profile_data.js"


def main():
    data = {}
    for p in sorted(RAW.glob("*.json.gz")):
        uid = p.stem.split(".")[0]
        try:
            with gzip.open(p, "rt", encoding="utf-8") as f:
                u = json.load(f)
        except Exception:
            continue
        s = u.get("statistics") or {}
        rh = u.get("rank_history") or u.get("rankHistory")
        curve = []
        if isinstance(rh, dict):
            pts = rh.get("data") or []
            # data = 每日全球 rank 序列（近 90 天，索引=天数），降采样 1/3
            for i in range(0, len(pts), 3):
                v = pts[i]
                if isinstance(v, (int, float)):
                    curve.append([i, v])
                elif isinstance(v, dict):
                    curve.append([i, v.get("rank")])
        page = (u.get("page") or {}).get("raw") or ""
        badges = [{"n": b.get("description"), "at": (b.get("awarded_at") or "")[:10],
                   "u": b.get("url")} for b in (u.get("badges") or [])]
        teams = u.get("team")
        team = {"n": teams.get("name"), "s": teams.get("short_name")} if isinstance(teams, dict) else None
        data[uid] = {
            "u": u.get("username"),
            "pn": u.get("previous_usernames") or [],
            "t": u.get("title"),
            "b": badges,
            "g": [{"n": g.get("name"), "s": g.get("short_name"), "c": g.get("colour")}
                  for g in (u.get("groups") or [])],
            "team": team,
            "tw": u.get("twitter"), "w": u.get("website"), "d": u.get("discord"),
            "loc": u.get("location"), "occ": u.get("occupation"), "int": u.get("interests"),
            "f": u.get("follower_count"), "mf": u.get("mapping_follower_count"),
            "kudosu": (u.get("kudosu") or {}).get("total"),
            "sup": u.get("support_level"),
            "rh": (u.get("rank_highest") or {}).get("rank"),
            "rhat": (u.get("rank_highest") or {}).get("updated_at", "")[:10] or None,
            "curve": curve,
            "ach": len(u.get("user_achievements") or []),
            "essay": page[:800],
        }
    body = "window.PROFILE_DATA = " + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n"
    OUT.write_text(body, encoding="utf-8")
    print(f"docs/profile_data.js 写入 {len(data)} 人 / {len(body)/1024/1024:.1f} MB", flush=True)


if __name__ == "__main__":
    main()
