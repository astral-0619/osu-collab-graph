#!/usr/bin/env python3
"""v2 限流友好爬虫：3 并发、每请求间隔、429/空页指数退避重试、断点续传。
判定失败 = HTTP 非 200 或页面无 data-initial-data（限流特征）。
--bfs 全量模式：爬图全部节点（主名单+外部），完整 user JSON gzip 落盘
data/profiles_raw/{uid}.json.gz（含小作文 page.raw/html，剥全局 achievements/cover 预设）。"""
import json, re, html as html_mod, subprocess, time, random, gzip, os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
OUT = BASE / "data" / "collab_lists.jsonl"
RAW_DIR = BASE / "data" / "profiles_raw"
MAX_ATTEMPTS = 6

def fetch(uid):
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            r = subprocess.run(
                ["curl", "-s", "-A", UA, "-m", "30", "-w", "\n%{http_code}",
                 f"https://osu.ppy.sh/users/{uid}"],
                capture_output=True, text=True, timeout=40)
            out = r.stdout
            code = out.rsplit("\n", 1)[-1].strip() if out else "000"
            body = out.rsplit("\n", 1)[0] if out else ""
            if code == "200" and 'data-initial-data="' in body:
                return body, code
            if code in ("429", "403", "000"):
                wait = min(60, 10 * (2 ** (attempt - 1))) + random.uniform(0, 3)
                print(f"    uid {uid} attempt {attempt} HTTP {code} 退避 {wait:.0f}s", flush=True)
                time.sleep(wait)
                continue
            # 200 但无 data-initial-data（限流/异常页）
            if code == "200" and len(body) < 20000:
                wait = min(60, 8 * (2 ** (attempt - 1))) + random.uniform(0, 3)
                print(f"    uid {uid} attempt {attempt} 空页退避 {wait:.0f}s", flush=True)
                time.sleep(wait)
                continue
            return body, code
        except Exception:
            time.sleep(5 + attempt * 3)
    return None, "fail"

def extract(html_text):
    m = re.search(r'data-initial-data="([^"]+)"', html_text)
    if not m:
        return [], []
    try:
        data = json.loads(html_mod.unescape(m.group(1)))
    except Exception:
        return [], []
    page = data.get("user", {}).get("page", {}).get("raw", "") or ""
    if not page:
        return [], []
    imgs, urls = [], []
    for m2 in re.finditer(r'([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) (https://osu\.ppy\.sh/users/(\d+))(?: ([^\r\n]+))?', page):
        uid, name = m2.group(6), (m2.group(7) or "").strip()
        if uid.isdigit() and int(uid) > 1000:
            imgs.append([int(uid), name])
    for m2 in re.finditer(r'\[url=https?://osu\.ppy\.sh/users/(\d+)\]([^\]]+)\[/url\]', page):
        uid = m2.group(1)
        if uid.isdigit() and int(uid) > 1000:
            urls.append([int(uid), m2.group(2).strip()])
    return imgs, urls

def extract_profile_from_user(u):
    """从 user JSON 对象提取精选 profile 维度（个人资料/履历/实力细节）。
    注意: 完整原始 JSON 落盘另有 save_raw；本函数供 build_profile_map 用。"""
    if not u.get("id"):
        return None
    stats = u.get("statistics") or {}
    rulesets = u.get("statistics_rulesets") or {}
    rs = {}
    for mode, s in rulesets.items():
        if isinstance(s, dict):
            rs[mode] = {
                "pp": s.get("pp"), "rank": s.get("global_rank"),
                "country_rank": s.get("country_rank"), "acc": s.get("hit_accuracy"),
                "play_count": s.get("play_count"), "play_time": s.get("play_time"),
            }
    badges = []
    for b in u.get("badges") or []:
        badges.append({"name": b.get("description"), "at": b.get("awarded_at"),
                       "url": b.get("url"), "img": b.get("image_url")})
    groups = []
    for g in u.get("groups") or []:
        groups.append({"name": g.get("name"), "short": g.get("short_name"),
                       "colour": g.get("colour")})
    team = u.get("team")
    if isinstance(team, dict):
        team = {"name": team.get("name"), "short": team.get("short_name"),
                "id": team.get("id"), "flag": team.get("flag_url")}
    rh = u.get("rank_history") or u.get("rankHistory")
    if isinstance(rh, dict):
        # data: [{date, rank, pp}...] 90 点，降采样保留全部但压短（日期+pp+rank 三列）
        rh = {"mode": rh.get("mode"),
              "data": [[d.get("date"), d.get("pp"), d.get("rank")] for d in (rh.get("data") or [])]}
    highest = u.get("rank_highest")
    if isinstance(highest, dict):
        highest = {"rank": highest.get("rank"), "at": highest.get("updated_at")}
    ach = u.get("user_achievements") or []
    mm = u.get("matchmaking_stats") or []
    mm_out = []
    for x in mm:
        if isinstance(x, dict):
            mm_out.append({"rating": x.get("rating"), "rank": x.get("rank"),
                           "plays": x.get("plays"), "wins": x.get("first_placements"),
                           "pool": (x.get("pool") or {}).get("name")})
    kudosu = u.get("kudosu")
    if isinstance(kudosu, dict):
        kudosu = {"total": kudosu.get("total"), "available": kudosu.get("available")}
    return {
        "username": u.get("username"),
        "country_code": u.get("country_code"),
        "join_date": u.get("join_date"),
        "playmode": u.get("playmode"),
        "is_active": u.get("is_active"),
        "is_supporter": bool(u.get("is_supporter")),
        "support_level": u.get("support_level"),
        "title": u.get("title"), "title_url": u.get("title_url"),
        "twitter": u.get("twitter"), "website": u.get("website"),
        "discord": u.get("discord"), "location": u.get("location"),
        "occupation": u.get("occupation"), "interests": u.get("interests"),
        "kudosu": kudosu,
        "post_count": u.get("post_count"), "comments_count": u.get("comments_count"),
        "follower_count": u.get("follower_count"),
        "mapping_follower_count": u.get("mapping_follower_count"),
        "previous_usernames": u.get("previous_usernames") or [],
        "badges": badges, "groups": groups, "team": team,
        "rank_highest": highest, "rank_history": rh,
        "user_achievements": [a.get("achievement_id") for a in ach],
        "achievements_count": len(ach),
        "matchmaking_stats": mm_out,
        "daily_challenge": u.get("daily_challenge_user_stats"),
        "statistics": {
            "pp": stats.get("pp"), "rank": stats.get("global_rank"),
            "country_rank": stats.get("country_rank"),
            "acc": stats.get("hit_accuracy"), "play_count": stats.get("play_count"),
            "play_time": stats.get("play_time"),
            "ranked_score": stats.get("ranked_score"), "total_score": stats.get("total_score"),
            "total_hits": stats.get("total_hits"), "max_combo": stats.get("maximum_combo"),
            "replays_watched": stats.get("replays_watched_by_others"),
            "level": (stats.get("level") or {}).get("current"),
            "grades": stats.get("grade_counts"),
        },
        "statistics_rulesets": rs,
    }

def extract_profile(html_text):
    """从主页 data-initial-data 提取精选 profile 维度。"""
    m = re.search(r'data-initial-data="([^"]+)"', html_text)
    if not m:
        return None
    try:
        u = json.loads(html_mod.unescape(m.group(1))).get("user") or {}
    except Exception:
        return None
    return extract_profile_from_user(u)

def save_raw(uid, data):
    """完整 user JSON gzip 落盘（剥每页重复的全局数据: 成就定义表/封面预设）。"""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"{uid}.json.gz"
    if out.exists():
        return False
    u = data.get("user") or {}
    # 仅存 user 对象本身（含 page.raw/page.html 小作文全量）
    tmp = out.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(u, f, ensure_ascii=False)
    os.replace(tmp, out)
    return True

def main():
    import sys as _sys
    if "--help" in _sys.argv or "-h" in _sys.argv:
        print("用法: python3 crawl_collab_lists_v2.py [--fresh] [--bfs] [--shard-i=N --shard-n=M]")
        print("  --fresh      删除断点文件，强制全量重爬（默认增量续爬）")
        print("  --bfs        全量模式：爬图全部节点（主名单+外部），collab/raw 任一缺失即爬")
        print("  --shard-i=N  只爬 todo 中索引 % shard_n == N 的部分（配合 Actions 分片）")
        print("  --shard-n=M  分片总数（默认 1）")
        return
    shard_i, shard_n = 0, 1
    _a = _sys.argv
    for _x in _a:
        if _x.startswith("--shard-i="): shard_i = int(_x.split("=", 1)[1])
        elif _x == "--shard-i": shard_i = int(_a[_a.index(_x) + 1])
        if _x.startswith("--shard-n="): shard_n = int(_x.split("=", 1)[1])
        elif _x == "--shard-n": shard_n = int(_a[_a.index(_x) + 1])
    fresh = "--fresh" in _a
    bfs = "--bfs" in _a
    if fresh:
        print("--fresh: 强制全量重爬（保留主名单基线）", flush=True)
    SEEDS = {18230719, 20865377, 37684093, 35844030, 10681880, 14538142, 2192312, 38737489, 36062235}
    all_uids = set(SEEDS)
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            try:
                all_uids.add(json.loads(line)["uid"])
            except Exception:
                pass
    graph = json.loads((BASE / "data" / "collab_graph.json").read_text(encoding="utf-8"))
    graph_uids = sorted({n["uid"] for n in graph["nodes"]} | SEEDS)
    if bfs:
        # BFS 全量模式：爬图全部节点（主名单+外部引用），collab 或 raw 任一缺失即爬
        all_uids = graph_uids
        print(f"--bfs: 全量模式，目标 = 图全部 {len(all_uids)} 节点", flush=True)
    elif not all_uids - SEEDS:
        # 首次无基线：退回图节点（种子展开）
        all_uids = graph_uids
    all_uids = sorted(all_uids)
    done_collab = set()
    done_raw = set()
    if OUT.exists() and not fresh:
        for line in OUT.read_text(encoding="utf-8").splitlines():
            try:
                done_collab.add(json.loads(line)["uid"])
            except Exception:
                pass
    if RAW_DIR.exists():
        for p in RAW_DIR.glob("*.json.gz"):
            done_raw.add(int(p.stem.split(".")[0]))
    if bfs:
        # 全量模式：collab 或 raw 任一缺失就爬
        todo = [u for u in all_uids if u not in done_collab or u not in done_raw]
    else:
        todo = [u for u in all_uids if u not in done_collab]
    if shard_n > 1:
        todo = [u for i, u in enumerate(todo) if i % shard_n == shard_i]
    print(f"total {len(all_uids)} / collab_done {len(done_collab)} / raw_done {len(done_raw)} / todo(本片) {len(todo)}", flush=True)
    if not todo:
        print("all crawled", flush=True)
        return

    def work(uid):
        html_text, code = fetch(uid)
        imgs, urls = extract(html_text) if html_text else ([], [])
        raw_ok = False
        if html_text:
            m = re.search(r'data-initial-data="([^"]+)"', html_text)
            if m:
                try:
                    data = json.loads(html_mod.unescape(m.group(1)))
                    raw_ok = save_raw(uid, data)
                except Exception:
                    pass
        return uid, code, imgs, urls, raw_ok

    out_file = OUT
    if shard_n > 1:
        out_file = OUT.with_name(f"collab_lists.shard{shard_i}.jsonl")
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(work, u): u for u in todo}
        with out_file.open("a" if bfs else ("w" if fresh else "a"), encoding="utf-8") as f:
            for i, fut in enumerate(as_completed(futs), 1):
                uid, code, imgs, urls, raw_ok = fut.result()
                f.write(json.dumps({"uid": uid, "code": code, "imgs": imgs, "urls": urls}, ensure_ascii=False) + "\n")
                f.flush()
                if i % 25 == 0 or i == len(todo):
                    print(f"  {i}/{len(todo)}", flush=True)
                time.sleep(0.5)
    print("done", flush=True)

if __name__ == "__main__":
    main()
