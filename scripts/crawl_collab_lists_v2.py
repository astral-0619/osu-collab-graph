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

# 全局 429 熔断：连续 429/403 达到阈值即全体冷却，避免在 CF 惩罚窗口里反复打
_circuit = {"consecutive_429": 0}
_CIRCUIT_BREAK_AT = 6          # 连续 6 次 429/403 触发熔断
_CIRCUIT_COOL_DOWN = 300       # 熔断冷却 5 分钟
_circuit_lock = __import__("threading").Lock()

def _circuit_wait_until_clear():
    """熔断检查：触发则打印并全体 sleep 冷却，随后清零计数。"""
    while True:
        with _circuit_lock:
            if _circuit["consecutive_429"] < _CIRCUIT_BREAK_AT:
                return
        print(f"  !!! 连续 {_CIRCUIT_BREAK_AT}+ 次 429/403，触发全局熔断，冷却 {_CIRCUIT_COOL_DOWN}s", flush=True)
        time.sleep(_CIRCUIT_COOL_DOWN)
        with _circuit_lock:
            _circuit["consecutive_429"] = 0
        print("  --- 熔断结束，恢复爬取", flush=True)

def _mark_http(code):
    with _circuit_lock:
        if code in ("429", "403"):
            _circuit["consecutive_429"] += 1
        else:
            _circuit["consecutive_429"] = 0

def fetch(uid):
    for attempt in range(1, MAX_ATTEMPTS + 1):
        _circuit_wait_until_clear()
        try:
            hdr_tmp = f"/tmp/crawl_hdr_{os.getpid()}.txt"
            body_tmp = f"/tmp/crawl_body_{os.getpid()}.html"
            r = subprocess.run(
                ["curl", "-s", "-A", UA, "-m", "30",
                 "-D", hdr_tmp, "-o", body_tmp,
                 "-w", "%{http_code}",
                 f"https://osu.ppy.sh/users/{uid}"],
                capture_output=True, text=True, timeout=40)
            meta = (r.stdout or "").strip()
            try:
                body = open(body_tmp, errors="ignore").read()
            except Exception:
                body = ""
            finally:
                try:
                    os.remove(body_tmp)
                except Exception:
                    pass
            code = meta if meta else "000"
            retry_after = None
            try:
                for line in open(hdr_tmp, errors="ignore"):
                    if line.lower().startswith("retry-after:"):
                        retry_after = min(60, float(line.split(":", 1)[1].strip()))
                        break
            except Exception:
                pass
            finally:
                try:
                    os.remove(hdr_tmp)
                except Exception:
                    pass
            if code == "200" and 'data-initial-data="' in body:
                _mark_http(code)
                return body, code
            if code in ("429", "403", "502", "503", "000"):
                _mark_http(code)
                if retry_after:
                    wait = min(120, retry_after)
                elif code == "000":
                    wait = 3 + attempt * 2  # curl 层断连，重试快
                elif code in ("502", "503"):
                    wait = 5 + attempt * 3  # 服务器过载，中速重试
                else:
                    wait = min(120, 10 * (2 ** (attempt - 1))) + random.uniform(0, 2)
                print(f"    uid {uid} attempt {attempt} HTTP {code} 退避 {wait:.0f}s", flush=True)
                time.sleep(wait)
                continue
            # 200 但无 data-initial-data（限流/异常页）
            if code == "200" and len(body) < 20000:
                _mark_http("429")
                wait = (retry_after if retry_after else min(120, 10 * (2 ** (attempt - 1)))) + random.uniform(0, 2)
                print(f"    uid {uid} attempt {attempt} 空页退避 {wait:.0f}s", flush=True)
                time.sleep(wait)
                continue
            _mark_http(code)
            return body, code
        except Exception:
            time.sleep(5 + attempt * 3)
    _mark_http("000")
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
        d = rh.get("data") or []
        if d and isinstance(d[0], dict):
            # data: [{date, rank, pp}...] 对象数组
            rh = {"mode": rh.get("mode"),
                  "data": [[x.get("date"), x.get("pp"), x.get("rank")] for x in d]}
        else:
            # data: 90 个纯 rank 数字（主页 data-initial-data 的扁平结构）
            rh = {"mode": rh.get("mode"), "data": d}
    elif isinstance(rh, list):
        rh = {"mode": None, "data": rh}
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
    skip404 = set()      # 已确认 404 的幽灵 uid：raw 永远缺，不再重爬
    fail_count = {}
    if OUT.exists() and not fresh:
        for line in OUT.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
                done_collab.add(rec["uid"])
                if rec.get("code") == "404":
                    skip404.add(rec["uid"])
                elif rec.get("code") == "fail":
                    fail_count[rec["uid"]] = fail_count.get(rec["uid"], 0) + 1
            except Exception:
                pass
    if RAW_DIR.exists():
        for p in RAW_DIR.glob("*.json.gz"):
            done_raw.add(int(p.stem.split(".")[0]))
    if bfs:
        # 全量模式：collab 或 raw 任一缺失就爬
        todo = [u for u in all_uids
                if (u not in done_collab or u not in done_raw)
                and u not in skip404]
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
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = {ex.submit(work, u): u for u in todo}
        with out_file.open("a" if bfs else ("w" if fresh else "a"), encoding="utf-8") as f:
            this_run_fail = []
            for i, fut in enumerate(as_completed(futs), 1):
                uid, code, imgs, urls, raw_ok = fut.result()
                if code == "fail":
                    this_run_fail.append(uid)
                f.write(json.dumps({"uid": uid, "code": code, "imgs": imgs, "urls": urls}, ensure_ascii=False) + "\n")
                f.flush()
                if i % 25 == 0 or i == len(todo):
                    print(f"  {i}/{len(todo)}", flush=True)
                time.sleep(1.2)
    # 收敛判定：本轮 fail 全部是历史老 fail（运行开始前已有 fail 记录）→ 尽力而为完成
    new_fail = [u for u in this_run_fail if fail_count.get(u, 0) == 0]
    if this_run_fail and not new_fail:
        print(f"all crawled (fail 收敛: {len(this_run_fail)} 个反复失败已尽力, 404 跳过 {len(skip404)})", flush=True)
    else:
        print("done", flush=True)

if __name__ == "__main__":
    main()
