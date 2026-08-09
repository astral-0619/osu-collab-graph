#!/usr/bin/env python3
"""v2 限流友好爬虫：3 并发、每请求间隔、429/空页指数退避重试、断点续传。
判定失败 = HTTP 非 200 或页面无 data-initial-data（限流特征）。"""
import json, re, html as html_mod, subprocess, time, random
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
OUT = BASE / "data" / "collab_lists.jsonl"
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

def main():
    import sys as _sys
    if "--help" in _sys.argv or "-h" in _sys.argv:
        print("用法: python3 crawl_collab_lists_v2.py [--fresh] [--bfs] [--shard-i=N --shard-n=M]")
        print("  --fresh      删除断点文件，强制全量重爬（默认增量续爬）")
        print("  --bfs        扩散模式：爬图里所有未爬节点（外部引用），append 到现有列表")
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
    if bfs:
        # BFS 扩散模式：爬图里所有还没爬过的节点（外部引用），append 到现有列表
        all_uids = sorted({n["uid"] for n in graph["nodes"]} | SEEDS)
        print(f"--bfs: 扩散模式，目标 = 图全部 {len(all_uids)} 节点（含外部引用）", flush=True)
    if not all_uids - SEEDS:
        # 首次无基线：退回图节点（种子展开）
        all_uids = {n["uid"] for n in graph["nodes"]} | SEEDS
    all_uids = sorted(all_uids)
    done = set()
    if OUT.exists() and not fresh:
        for line in OUT.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line)["uid"])
            except Exception:
                pass
    todo = [u for u in all_uids if u not in done]
    if shard_n > 1:
        todo = [u for i, u in enumerate(todo) if i % shard_n == shard_i]
    print(f"total {len(all_uids)} / done {len(done)} / todo(本片) {len(todo)}", flush=True)
    if not todo:
        print("all crawled", flush=True)
        return

    def work(uid):
        html_text, code = fetch(uid)
        imgs, urls = extract(html_text) if html_text else ([], [])
        return uid, code, imgs, urls

    out_file = OUT
    if shard_n > 1:
        out_file = OUT.with_name(f"collab_lists.shard{shard_i}.jsonl")
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(work, u): u for u in todo}
        with out_file.open("a" if bfs else ("w" if fresh else "a"), encoding="utf-8") as f:
            for i, fut in enumerate(as_completed(futs), 1):
                uid, code, imgs, urls = fut.result()
                f.write(json.dumps({"uid": uid, "code": code, "imgs": imgs, "urls": urls}, ensure_ascii=False) + "\n")
                f.flush()
                if i % 25 == 0 or i == len(todo):
                    print(f"  {i}/{len(todo)}", flush=True)
                time.sleep(0.5)
    print("done", flush=True)

if __name__ == "__main__":
    main()
