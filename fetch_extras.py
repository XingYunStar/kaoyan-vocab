# -*- coding: utf-8 -*-
"""下载「助记解析」与「助记图片」（来自 vxiaozhi/vocabulary-book-by-deepseek）。

用法：
    python fetch_extras.py              # 助记文本 + 图片都下
    python fetch_extras.py --only mnemonic
    python fetch_extras.py --only image
    python fetch_extras.py --workers 12
    python fetch_extras.py --proxy http://127.0.0.1:7890   # 走本地 VPN

产物（都在 data/ 下，已在 .gitignore 里）：
    data/mnemonics/<单词>.json     词义/例句/词根/词缀/文化背景的长文解析
    data/word_imgs/<首字母>/<单词>.jpg   助记插图

设计要点
--------
* 先用 git trees API 拿到远端完整文件清单，再按名单精确下载 —— 不做 404 试探。
* 断点续传：已存在且非空的文件直接跳过，随时可重跑。
* 并发下载，默认 8 路；失败的重试 2 次。
* 通道优先级：本地代理 > ghproxy.net（实测 8 并发约 4 张/秒）。
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
DB = os.path.join(DATA, "vocab.db")
REPO = "vxiaozhi/vocabulary-book-by-deepseek"
BRANCH = "main"
UA = {"User-Agent": "kaoyan-vocab/1.0"}

_lock = threading.Lock()
_stat = {"ok": 0, "skip": 0, "fail": 0, "bytes": 0}


def opener(proxy=None):
    if proxy:
        h = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        return urllib.request.build_opener(h)
    return urllib.request.build_opener()


def fetch(url, timeout=60, proxy=None):
    with opener(proxy).open(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


DIRECT = False   # --direct：直连 GitHub（开了 VPN 时最快）


def mirror(url, proxy=None):
    """把 GitHub 地址包一层镜像。

    通道优先级：--direct 直连 > --proxy 本地代理 > ghproxy.net 镜像。
    实测同一批图：直连 13.8 文件/秒，代理 8.8，镜像 3.1。
    """
    if proxy or DIRECT:
        return url
    return "https://ghproxy.net/" + url


def remote_tree(proxy=None):
    """远端文件清单 -> {路径: 大小}"""
    api = "https://api.github.com/repos/%s/git/trees/%s?recursive=1" % (REPO, BRANCH)
    token = os.environ.get("GH_TOKEN", "")
    hdr = dict(UA)
    if token:
        hdr["Authorization"] = "Bearer " + token
    if proxy:
        url = api
    else:
        url = api  # api.github.com 本身可达，不需要镜像
    req = urllib.request.Request(url, headers=hdr)
    with opener(proxy).open(req, timeout=90) as r:
        j = json.loads(r.read().decode("utf-8"))
    return {t["path"]: (t.get("size") or 0) for t in j["tree"]}


def norm(word):
    return word.lower().replace(" ", "").replace("-", "")


def build_plan(tree):
    """把远端清单整理成 {单词: (json路径, jpg路径)}"""
    import re
    mn, im = {}, {}
    for p, sz in tree.items():
        if p.startswith("result/all/") and p.endswith(".json"):
            n = re.sub(r"\d+$", "", p.rsplit("/", 1)[-1][:-5])
            mn.setdefault(norm(n), (p, sz))
        elif p.startswith("result/word_imgs/") and p.lower().endswith(".jpg"):
            n = re.sub(r"\d+$", "", p.rsplit("/", 1)[-1][:-4])
            im.setdefault(norm(n), (p, sz))
    return mn, im


def download(url, dest, expect=0, retries=2, proxy=None):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        with _lock:
            _stat["skip"] += 1
        return True
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    for attempt in range(retries + 1):
        try:
            data = fetch(url, timeout=90, proxy=proxy)
            if expect and len(data) < expect * 0.5:
                raise ValueError("字节数偏少 %d < %d" % (len(data), expect))
            tmp = dest + ".part"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, dest)
            with _lock:
                _stat["ok"] += 1
                _stat["bytes"] += len(data)
            return True
        except Exception as e:
            if attempt == retries:
                with _lock:
                    _stat["fail"] += 1
                print("    失败 %s: %s" % (os.path.basename(dest), str(e)[:60]))
                return False
            time.sleep(1.5 * (attempt + 1))
    return False


def progress(label, total, t0):
    with _lock:
        done = _stat["ok"] + _stat["skip"] + _stat["fail"]
        rate = done / max(0.001, time.time() - t0)
        eta = (total - done) / rate if rate > 0 else 0
        sys.stdout.write("\r  %s %d/%d  新增%d 跳过%d 失败%d  %.2f文件/秒  剩余%.0f分  %s" % (
            label, done, total, _stat["ok"], _stat["skip"], _stat["fail"],
            rate, eta / 60, "%.0fMB" % (_stat["bytes"] / 1048576)))
        sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["mnemonic", "image"], default=None)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--proxy", default=None)
    ap.add_argument("--direct", action="store_true",
                    help="直连 GitHub，不走镜像（开了 VPN 时最快）")
    args = ap.parse_args()

    global DIRECT
    DIRECT = bool(args.direct)

    if not os.path.exists(DB):
        print("! 找不到 %s，请先建库" % DB)
        return 1
    con = sqlite3.connect(DB)
    words = [r[0] for r in con.execute("SELECT word FROM words")]
    print("词表: %d 个" % len(words))

    proxy = args.proxy or os.environ.get("GIT_PROXY") or None
    if proxy:
        print("通道: 本地代理 %s" % proxy)
    elif DIRECT:
        print("通道: 直连 GitHub")
    else:
        print("通道: ghproxy.net 镜像（VPN 已开可加 --direct，实测快 4 倍）")

    print("拉取远端文件清单 ...")
    tree = remote_tree(proxy)
    print("  远端文件 %d 个" % len(tree))
    mn, im = build_plan(tree)
    print("  远端助记 %d 个 / 图片 %d 张" % (len(mn), len(im)))

    jobs = []
    if args.only in (None, "mnemonic"):
        mdir = os.path.join(DATA, "mnemonics")
        for w in words:
            hit = mn.get(norm(w))
            if hit:
                jobs.append(("助记", w, mirror(
                    "https://raw.githubusercontent.com/%s/%s/%s" % (REPO, BRANCH, hit[0]), proxy),
                    os.path.join(mdir, w + ".json"), hit[1]))
    if args.only in (None, "image"):
        idir = os.path.join(DATA, "word_imgs")
        for w in words:
            hit = im.get(norm(w))
            if hit:
                jobs.append(("图片", w, mirror(
                    "https://raw.githubusercontent.com/%s/%s/%s" % (REPO, BRANCH, hit[0]), proxy),
                    os.path.join(idir, w[0].lower(), w + ".jpg"), hit[1]))

    if not jobs:
        print("没有可下载的条目")
        return 1
    print("待下载 %d 个文件，并发 %d" % (len(jobs), args.workers))

    t0 = time.time()
    by_label = {}
    for lab, _w, _u, _d, _s in jobs:
        by_label.setdefault(lab, 0)
        by_label[lab] += 1

    done_counter = {"n": 0}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(download, u, d, s, 2, proxy): (lab, w) for lab, w, u, d, s in jobs}
        for fut in as_completed(futs):
            done_counter["n"] += 1
            if done_counter["n"] % 25 == 0 or done_counter["n"] == len(jobs):
                progress("下载中", len(jobs), t0)
    print()

    print()
    print("完成: 新增 %d，跳过 %d，失败 %d，共 %.0f MB，用时 %.1f 分钟" % (
        _stat["ok"], _stat["skip"], _stat["fail"], _stat["bytes"] / 1048576,
        (time.time() - t0) / 60))
    if _stat["fail"]:
        print("有失败项，重跑本脚本即可续传（已下载的会跳过）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
