#!/usr/bin/env python3
"""全量重爬：把图里全部节点的主页 imagemap 原始条目（不去重）追加写入 data/collab_lists.jsonl。
可断点续爬：已存在于 jsonl 的 uid 跳过。"""
import json, re, html as html_mod, subprocess, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
OUT = BASE / "data" / "collab_lists.jsonl"

def fetch_profile(uid):
    for attempt in range(2):
        try:
            r = subprocess.run(["curl", "-s", "-A", UA, "-m", "25", f"https://osu.ppy.sh/users/{uid}"],
                               capture_output=True, text=True, timeout=30)
            if r.returncode == 0 and r.stdout:
                return r.stdout
        except Exception:
            pass
        time.sleep(1)
    return None

def extract_raw_collabs(html_text):
    """提取 imagemap 原始条目（保留重复，含名字），[url] 文本链接不计数但并入列表。"""
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
        if uid.isdigit():
            imgs.append([int(uid), name])
    for m2 in re.finditer(r'\[url=https?://osu\.ppy\.sh/users/(\d+)\]([^\]]+)\[/url\]', page):
        uid = m2.group(1)
        if uid.isdigit():
            urls.append([int(uid), m2.group(2).strip()])
    return imgs, urls

def main():
    graph = json.loads((BASE / "data" / "collab_graph.json").read_text(encoding="utf-8"))
    all_uids = {n["uid"] for n in graph["nodes"]}
    done = set()
    if OUT.exists():
        for line in OUT.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line)["uid"])
            except Exception:
                pass
    todo = sorted(all_uids - done)
    print(f"total {len(all_uids)} / done {len(done)} / todo {len(todo)}")
    if not todo:
        print("all crawled")
        return

    def work(uid):
        html_text = fetch_profile(uid)
        imgs, urls = extract_raw_collabs(html_text) if html_text else ([], [])
        return uid, imgs, urls

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(work, u): u for u in todo}
        with OUT.open("a", encoding="utf-8") as f:
            for i, fut in enumerate(as_completed(futs), 1):
                uid, imgs, urls = fut.result()
                f.write(json.dumps({"uid": uid, "imgs": imgs, "urls": urls}, ensure_ascii=False) + "\n")
                f.flush()
                if i % 50 == 0 or i == len(todo):
                    print(f"  {i}/{len(todo)}", flush=True)
                time.sleep(0.12)
    print("done", flush=True)

if __name__ == "__main__":
    main()
