#!/usr/bin/env python3
"""种子爬取：抓群友 osu 主页用户页的 collab 互链（imagemap + [url] 链接）。"""
import json, re, html as html_mod, subprocess, time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

# 种子节点：uid -> (osu 名, 备注)。换成你自己的圈子即可。
MEMBERS = {
    18230719: ("ZnCookie", "群主"), 20865377: ("oines", "oines"),
    37684093: ("Sakuraba Ruri", "LadyEvil"), 35844030: ("faweidao", "乏味道"),
    10681880: ("Kaffu-", "Kaffu-"), 14538142: ("ScarletRemilia-", "suzuri"),
    2192312: ("Shimakaze", "Shimakaze"), 38737489: ("XiaFeng", "XiaFeng"),
    36062235: ("21awa12", "21awa12"),
}

def fetch_profile(uid):
    url = f"https://osu.ppy.sh/users/{uid}"
    for attempt in range(3):
        try:
            r = subprocess.run(["curl", "-s", "-A", UA, "-m", "30", url],
                               capture_output=True, text=True, timeout=40)
            if r.returncode == 0 and r.stdout:
                return r.stdout
        except Exception:
            pass
        time.sleep(2 + attempt * 2)
    return None

def extract_collabs(html_text):
    """从 profile 页 data-initial-data 的 raw bbcode 里提取互链。
    imagemap 行格式: "x y w h https://osu.ppy.sh/users/UID 名字(可缺)"
    另有 [url=https://osu.ppy.sh/users/UID]名字[/url] 文本链接。"""
    m = re.search(r'data-initial-data="([^"]+)"', html_text)
    if not m:
        return []
    raw = html_mod.unescape(m.group(1))
    try:
        data = json.loads(raw)
    except Exception:
        return []
    page = data.get("user", {}).get("page", {}).get("raw", "") or ""
    if not page:
        return []
    out = []
    for m2 in re.finditer(r'([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) (https://osu\.ppy\.sh/users/(\d+))(?: ([^\r\n]+))?', page):
        uid, name = m2.group(6), (m2.group(7) or "").strip()
        out.append((uid, name))
    for m2 in re.finditer(r'\[url=https?://osu\.ppy\.sh/users/(\d+)\]([^\]]+)\[/url\]', page):
        out.append((m2.group(1), m2.group(2).strip()))
    seen, res = set(), []
    for uid, name in out:
        if uid in seen or not uid.isdigit():
            continue
        seen.add(uid)
        res.append((uid, name))
    return res

def main():
    result = {}
    for uid, (uname, qqname) in MEMBERS.items():
        print(f"=== {uname} ({uid}) ===")
        page = fetch_profile(uid)
        collabs = extract_collabs(page) if page else []
        result[uname] = {"qq": qqname, "uid": uid, "collabs": collabs}
        print(f"  collabs: {len(collabs)}")
        time.sleep(1.5)
    (BASE / "data" / "collab_data.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved data/collab_data.json")

if __name__ == "__main__":
    main()
