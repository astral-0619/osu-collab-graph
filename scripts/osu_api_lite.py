#!/usr/bin/env python3
"""轻量 osu API 凭据/token（fetch_dimension 用，避免依赖 skill 目录）。"""
import json, os, sys, time, urllib.parse, urllib.request

ENV_FILE = "/workspace/.osu_api.env"


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
    body = urllib.parse.urlencode({"client_id": cid, "client_secret": sec,
                                   "grant_type": "client_credentials", "scope": "public"})
    req = urllib.request.Request("https://osu.ppy.sh/oauth/token", data=body.encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "osu-collab-graph/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)["access_token"]
