#!/usr/bin/env python3
"""数据自检：命名覆盖率 / 孤立点 / 重复 / 新旧图 diff / 标注名-玩家名差异。"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def main():
    g = json.loads((BASE / "data" / "collab_graph.json").read_text(encoding="utf-8"))
    nm = json.loads((BASE / "data" / "name_map.json").read_text(encoding="utf-8"))
    problems = []

    # 1. 命名覆盖率
    missing = [n for n in g["nodes"] if str(n["uid"]) not in nm]
    print(f"[命名] name_map 覆盖率 {len(nm)}/{len(g['nodes'])}，缺失 {len(missing)}")
    if missing:
        problems.append(f"name_map 缺 {len(missing)} 个 uid")

    # 2. 数字名节点（允许：真数字用户名）
    nums = [n for n in g["nodes"] if n["name"].isdigit()]
    real_nums = [n for n in nums if str(n["uid"]) in nm]
    fake_nums = [n for n in nums if str(n["uid"]) not in nm]
    print(f"[命名] 纯数字名 {len(nums)}（真数字用户名 {len(real_nums)}，未解析 {len(fake_nums)}）")

    # 3. 孤立点（degree 0，种子除外）
    SEEDS = {18230719, 20865377, 37684093, 35844030, 10681880, 14538142, 2192312, 38737489, 36062235}
    deg = {n["uid"]: 0 for n in g["nodes"]}
    for a, b, _ in g["edges"]:
        deg[a] += 1
        deg[b] += 1
    orphans = [u for u, d in deg.items() if d == 0 and u not in SEEDS]
    print(f"[结构] 孤立点 {len(orphans)} 个: {orphans[:10]}")

    # 4. 重复边/自环
    seen = set()
    dups = 0
    loops = 0
    for a, b, _ in g["edges"]:
        key = tuple(sorted((a, b)))
        if a == b:
            loops += 1
        if key in seen:
            dups += 1
        seen.add(key)
    print(f"[结构] 重复边 {dups}，自环 {loops}")
    if dups or loops:
        problems.append("存在重复边/自环")

    # 5. 基础统计
    print(f"[规模] 节点 {len(g['nodes'])} / 边 {len(g['edges'])} / "
          f"双向 {sum(1 for e in g['edges'] if e[2] >= 2)} / 最大权重 {max(e[2] for e in g['edges'])}")

    # 6. 旧图 diff（如果有 git）
    import subprocess
    r = subprocess.run(["git", "show", "HEAD:data/collab_graph.json"], capture_output=True,
                       text=True, cwd=BASE)
    if r.returncode == 0:
        old = json.loads(r.stdout)
        old_names = {n["uid"]: n["name"] for n in old["nodes"]}
        new_names = {n["uid"]: n["name"] for n in g["nodes"]}
        changed = [(u, old_names[u], new_names.get(u)) for u in old_names
                   if old_names[u] != new_names.get(u)]
        print(f"[diff] vs HEAD: 节点 {len(old['nodes'])}→{len(g['nodes'])}, "
              f"边 {len(old['edges'])}→{len(g['edges'])}, 改名 {len(changed)}")
        for u, a, b in changed[:5]:
            print(f"    {a} → {b}")

    print()
    print("⚠ 问题:" if problems else "✓ 全部通过")
    for p in problems:
        print("  -", p)


if __name__ == "__main__":
    main()
