#!/usr/bin/env python3
"""通用维度抓取器：批量 API 拉任意用户字段，落盘 data/<field>_map.json。
用法: python3 fetch_dimension.py --field=team|country|name|...
字段提取规则在 FIELD_EXTRACT 里注册，加新维度 = 加一行。
特性: 50 uid/请求、3 轮重试、断点续传（已有缓存跳过）、静默省略兜底（网页回退可选）。"""
import argparse, json, re, sys, time, urllib.request, urllib.parse, html as html_mod
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from osu_api_lite import get_token, load_creds  # noqa: E402

BASE = Path(__file__).resolve().parent.parent

# 字段提取注册表：加新维度 = 加一行
FIELD_EXTRACT = {
    "name": lambda u: u.get("username"),
    "team": lambda u: (u.get("team") or {}).get("name") or (u.get("team") or {}).get("short_name"),
    "country": lambda u: u.get("country_code"),
}

MODE_KEYS = {"osu": "osu", "taiko": "taiko", "fruits": "fruits", "mania": "mania"}


def fetch_stats():
    """全 4 模式成绩维度：pp / 游戏时间 / 游戏次数 / 全球排名 / 地区排名 + 注册时间。
    批量接口给 statistics_rulesets（4 模式核心字段），单用户接口补 join_date + country_rank。"""
    cid, sec = load_creds()
    tok = get_token(cid, sec)
    graph = json.loads((BASE / "data" / "collab_graph.json").read_text(encoding="utf-8"))
    uids = sorted(n["uid"] for n in graph["nodes"])
    out_file = BASE / "data" / "stats_map.json"
    old = json.loads(out_file.read_text(encoding="utf-8")) if out_file.exists() else {}
    todo = [u for u in uids if str(u) not in old
            or "modes" not in old[str(u)] or "join_date" not in old[str(u)]]
    print(f"共 {len(uids)}，已有完整缓存 {len(uids) - len(todo)}，需拉 {len(todo)}", flush=True)
    if not todo:
        print("all done", flush=True)
        return

    # 阶段 A：批量接口 → 4 模式核心统计
    real = dict(old)
    pending = todo
    for attempt in range(5):
        if not pending:
            break
        nxt = []
        for i in range(0, len(pending), 20):
            batch = pending[i:i + 20]
            try:
                qs = urllib.parse.urlencode([("ids[]", u) for u in batch])
                req = urllib.request.Request("https://osu.ppy.sh/api/v2/users?" + qs,
                    headers={"Authorization": "Bearer " + tok, "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    for u in json.load(r)["users"]:
                        sr = u.get("statistics_rulesets") or {}
                        entry = real.setdefault(str(u["id"]), {})
                        entry["modes"] = {}
                        for mk, label in MODE_KEYS.items():
                            st = (sr.get(label) or {})
                            entry["modes"][mk] = {
                                "pp": st.get("pp"),
                                "play_time": st.get("play_time"),
                                "play_count": st.get("play_count"),
                                "global_rank": st.get("global_rank"),
                                "accuracy": st.get("hit_accuracy"),
                            }
                print(f"  A 批次 {i//50+1}/{len(pending)//50+1} OK", flush=True)
            except urllib.error.HTTPError as e:
                print(f"  A 批次 HTTPError {e.code}，留待重试", flush=True)
                if e.code == 429:
                    time.sleep(30)
                nxt.extend(batch)
            except Exception as e:
                print(f"  A 批次失败({type(e).__name__})，留待重试", flush=True)
                nxt.extend(batch)
        pending = nxt
    if pending:
        print(f"⚠ 仍有 {len(pending)} 个用户 5 轮未成功，跳过", flush=True)
    json.dump(real, out_file.open("w", encoding="utf-8"), ensure_ascii=False)
    print(f"阶段 A 完成: {len(real)} 用户 4 模式核心统计已落盘", flush=True)

    # 阶段 B：单用户接口 ×4 模式 → join_date + country_rank（3 并发，100 个落盘一次）
    def has_all_ranks(entry):
        return all("country_rank" in entry.get("modes", {}).get(mk, {})
                   for mk in MODE_KEYS)

    need = [u for u in uids
            if "join_date" not in real.get(str(u), {})
            or not has_all_ranks(real.get(str(u), {}))]
    print(f"阶段 B: 需补 join_date/country_rank {len(need)} 人 × 4 模式", flush=True)
    import concurrent.futures as cf

    def api_json(url, tok, attempts=4):
        for a in range(attempts):
            try:
                req = urllib.request.Request(url,
                    headers={"Authorization": "Bearer " + tok, "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.load(r)
            except Exception:
                if a == attempts - 1:
                    return None
                time.sleep(2 + a * 2)
        return None

    def fetch_one(uid):
        out = {}
        u = api_json(f"https://osu.ppy.sh/api/v2/users/{uid}", tok)
        if u:
            out["join_date"] = u.get("join_date")
            out["osu_rank"] = (u.get("statistics") or {}).get("country_rank")
        for mode, label in [("taiko", "taiko"), ("fruits", "fruits"), ("mania", "mania")]:
            u2 = api_json(f"https://osu.ppy.sh/api/v2/users/{uid}/{label}", tok)
            if u2:
                out[mode + "_rank"] = (u2.get("statistics") or {}).get("country_rank")
        return uid, out

    done = 0
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        for uid, res in ex.map(fetch_one, need):
            entry = real.setdefault(str(uid), {})
            entry.setdefault("modes", {})
            if res.get("join_date"):
                entry["join_date"] = res["join_date"]
            for k, v in res.items():
                if k != "join_date" and v is not None:
                    entry["modes"].setdefault(k.replace("_rank", ""), {})["country_rank"] = v
            done += 1
            if done % 100 == 0 or done == len(need):
                json.dump(real, out_file.open("w", encoding="utf-8"), ensure_ascii=False)
                print(f"  B {done}/{len(need)}", flush=True)
    json.dump(real, out_file.open("w", encoding="utf-8"), ensure_ascii=False)
    print(f"stats 完成: {len(real)} 用户", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--field", required=True, help="维度名（name/team/country/...）")
    ap.add_argument("--web-fallback", action="store_true", help="API 拿不到的用网页回退")
    ap.add_argument("--refresh", action="store_true",
                    help="忽略已有缓存强制全量重拉（默认增量：只拉新增/缺失）")
    args = ap.parse_args()
    field = args.field
    if field == "stats":
        fetch_stats()
        return
    if field not in FIELD_EXTRACT:
        sys.exit(f"未知维度 {field}，可用: {list(FIELD_EXTRACT) + ['stats']}")
    extract = FIELD_EXTRACT[field]

    cid, sec = load_creds()
    tok = get_token(cid, sec)
    graph = json.loads((BASE / "data" / "collab_graph.json").read_text(encoding="utf-8"))
    uids = sorted(n["uid"] for n in graph["nodes"])

    out_file = BASE / "data" / f"{field}_map.json"
    old = {} if args.refresh else (
        json.loads(out_file.read_text(encoding="utf-8")) if out_file.exists() else {})
    todo = [u for u in uids if str(u) not in old]
    print(f"共 {len(uids)}，已有 {len(uids)-len(todo)} 缓存，需拉 {len(todo)}", flush=True)

    real = dict(old)
    pending = todo
    for attempt in range(3):
        if not pending:
            break
        nxt = []
        for i in range(0, len(pending), 50):
            batch = pending[i:i+50]
            try:
                qs = urllib.parse.urlencode([("ids[]", u) for u in batch])
                req = urllib.request.Request("https://osu.ppy.sh/api/v2/users?" + qs,
                    headers={"Authorization": "Bearer " + tok, "Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    for u in json.load(r)["users"]:
                        v = extract(u)
                        if v:
                            real[str(u["id"])] = v
                print(f"  批次 {i//50+1}/{len(pending)//50+1} OK", flush=True)
            except Exception:
                nxt.extend(batch)
            time.sleep(0.3)
            out_file.write_text(json.dumps(real, ensure_ascii=False), encoding="utf-8")
        pending = nxt
        print(f"第 {attempt+1} 轮结束，剩 {len(pending)}", flush=True)
        time.sleep(2)

    if args.web_fallback:
        for uid in list(pending):
            try:
                req = urllib.request.Request(f"https://osu.ppy.sh/users/{uid}",
                    headers={"User-Agent": "osu-collab-graph/1.0"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    body = r.read().decode("utf-8", "ignore")
                m = re.search(r'data-initial-data="([^"]+)"', body)
                if m:
                    u = json.loads(html_mod.unescape(m.group(1)))["user"]
                    v = extract(u)
                    if v:
                        real[str(uid)] = v
                        pending.remove(uid)
            except Exception as e:
                print(f"  网页回退 {uid} 失败: {e}", flush=True)
            time.sleep(0.8)

    out_file.write_text(json.dumps(real, ensure_ascii=False), encoding="utf-8")
    print(f"完成: {field}_map 现有 {len(real)}/{len(uids)}，未拿到 {len(pending)}")


if __name__ == "__main__":
    main()
