#!/usr/bin/env python3
"""轻量 osu API 凭据/token（fetch_dimension 用，避免依赖 skill 目录）。"""
import json, os, sys, time, urllib.parse, urllib.request

ENV_FILE = "/workspace/.osu_api.env"
TOKEN_CACHE = "/tmp/osu_token_cache.json"


def load_creds():
    env = {}
    if os.path.exists(ENV_FILE):
        for line in open(ENV_FILE):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    cid = env.get("OSU_CLIENT_ID") or os.environ.get("OSU_CLIENT_ID")
    sec = env.get("OSU_CLIENT_SECRET") or os.environ.get("OSU_CLIENT_SECRET")
    if not cid or not sec:
        sys.exit("ERROR: no OSU_CLIENT_ID / OSU_CLIENT_SECRET")
    return cid, sec


def get_token(cid, sec):
    # token 24h 有效，缓存复用避免限流窗口内再打 token 接口
    if os.path.exists(TOKEN_CACHE):
        try:
            c = json.load(open(TOKEN_CACHE))
            if c.get("expires", 0) > time.time() + 300:
                return c["token"]
        except Exception:
            pass
    body = urllib.parse.urlencode({"client_id": cid, "client_secret": sec,
                                   "grant_type": "client_credentials", "scope": "public"})
    req = urllib.request.Request("https://osu.ppy.sh/oauth/token", data=body.encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "osu-collab-graph/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                tok = json.load(r)["access_token"]
                json.dump({"token": tok, "expires": time.time() + 24 * 3600},
                          open(TOKEN_CACHE, "w"))
                return tok
        except urllib.error.HTTPError as e:
            if attempt == 2:
                raise
            time.sleep(15 * (attempt + 1))
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))
