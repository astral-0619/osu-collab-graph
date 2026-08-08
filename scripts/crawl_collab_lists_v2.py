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
    graph = json.loads((BASE / "data" / "collab_graph.json").read_text(encoding="utf-8"))
    all_uids = sorted(n["uid"] for n in graph["nodes"])
    done = set()
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line)["uid"])
            except Exception:
                pass
    todo = [u for u in all_uids if u not in done]
    print(f"total {len(all_uids)} / done {len(done)} / todo {len(todo)}", flush=True)
    if not todo:
        print("all crawled", flush=True)
        return

    def work(uid):
        html_text, code = fetch(uid)
        imgs, urls = extract(html_text) if html_text else ([], [])
        return uid, code, imgs, urls

    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(work, u): u for u in todo}
        with OUT.open("a", encoding="utf-8") as f:
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
