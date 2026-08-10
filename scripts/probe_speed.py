#!/usr/bin/env python3
"""限流参数扫描：测不同 (并发×间隔) 下的 429 率与有效吞吐，找最优爬取参数。
每组跑 TEST_SECS 秒，组间冷却 COOL_SECS。只发请求不写盘（不污染数据）。
用法: python3 scripts/probe_speed.py
"""
import json, random, subprocess, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
TEST_SECS = 60
COOL_SECS = 60

# 候选参数：并发 × 间隔
CANDIDATES = [
    (2, 1.2),   # 稳基线
    (3, 1.0),
    (3, 0.5),   # 老基线（429 7.5%）
    (4, 0.8),
    (4, 0.5),
    (5, 0.4),
    (6, 0.3),
]


def main():
    graph = json.loads((BASE / "data" / "collab_graph.json").read_text(encoding="utf-8"))
    pool = [n["uid"] for n in graph["nodes"]][:2000]
    random.seed(7)

    print(f"扫描 {len(CANDIDATES)} 组参数，每组 {TEST_SECS}s，组间冷却 {COOL_SECS}s", flush=True)
    results = []
    for ci, (workers, gap) in enumerate(CANDIDATES):
        idx = 0
        stop = time.time() + TEST_SECS
        stats = {"total": 0, "ok": 0, "429": 0, "other": 0, "bytes": 0, "times": []}

        def one(_):
            nonlocal idx
            uid = pool[idx % len(pool)]
            idx += 1
            t0 = time.time()
            r = subprocess.run(
                ["curl", "-s", "-A", UA, "-m", "25", "-o", "/dev/null",
                 "-w", "%{http_code} %{size_download}", f"https://osu.ppy.sh/users/{uid}"],
                capture_output=True, text=True, timeout=30)
            el = time.time() - t0
            try:
                code, size = r.stdout.strip().rsplit(" ", 1)
            except Exception:
                code, size = "000", "0"
            return code, int(size), el

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = []
            while time.time() < stop:
                futs.append(ex.submit(one, None))
                time.sleep(gap)
            for f in as_completed(futs):
                code, size, el = f.result()
                stats["total"] += 1
                stats["times"].append(el)
                if code == "200":
                    stats["ok"] += 1
                    stats["bytes"] += size
                elif code == "429":
                    stats["429"] += 1
                else:
                    stats["other"] += 1
        rate = stats["ok"] / TEST_SECS
        p429 = stats["429"] / stats["total"] * 100 if stats["total"] else 0
        avg_t = sum(stats["times"]) / len(stats["times"]) if stats["times"] else 0
        results.append((workers, gap, rate, p429, stats["total"], avg_t))
        print(f"  并发{workers}×间隔{gap}s: 请求 {stats['total']} / 200={stats['ok']} "
              f"429={stats['429']} 其他={stats['other']} | 有效速率 {rate:.2f}/s | "
              f"429率 {p429:.1f}% | 均耗 {avg_t:.2f}s", flush=True)
        if ci < len(CANDIDATES) - 1:
            time.sleep(COOL_SECS)

    print("\n=== 排名（有效速率降序，429率<5% 才算可用）===", flush=True)
    for workers, gap, rate, p429, total, avg_t in sorted(results, key=lambda x: -x[2]):
        flag = "✓" if p429 < 5 else "✗"
        print(f"  {flag} 并发{workers}×间隔{gap}s → {rate:.2f}/s (429率 {p429:.1f}%)", flush=True)


if __name__ == "__main__":
    main()
