# -*- coding: utf-8 -*-
"""下载建库所需的第三方数据（共约 74 MB，只跑一次）。

用法：  python fetch_data.py

下载内容
--------
  data/cmudict.dict   3.6 MB  音标（ARPAbet）        cmusphinx/cmudict
  data/cmn.txt        4.6 MB  英汉句对（例句来源）    Tatoeba / manythings.org
  data/ecdict.csv      66 MB  英汉词典（词性释义）    skywind3000/ECDICT

词表本身（data/vocab-source.csv）已经在仓库里，不需要下载。

全部用标准库，不依赖 requests。已存在的文件默认跳过，加 --force 可强制重下。
"""
from __future__ import annotations

import os
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

CMUDICT = ("https://raw.githubusercontent.com/cmusphinx/cmudict/master/cmudict.dict",
           "cmudict.dict", 3_600_000)
ECDICT = ("https://raw.githubusercontent.com/skywind3000/ECDICT/master/ecdict.csv",
          "ecdict.csv", 66_000_000)
ANKI = ("https://www.manythings.org/anki/cmn-eng.zip", "cmn-eng.zip", 1_400_000)

UA = {"User-Agent": "kaoyan-vocab/1.0 (+https://github.com/XingYunStar/kaoyan-vocab)"}


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return "%.1f %s" % (n, unit)
        n /= 1024.0


def download(url, dest, expect, force=False):
    """带进度输出的下载；已存在且大小合理则跳过。"""
    if os.path.exists(dest) and not force:
        size = os.path.getsize(dest)
        if size >= expect * 0.9:
            print("  跳过（已存在 %s）：%s" % (human(size), os.path.basename(dest)))
            return True
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    print("  下载 %s ..." % os.path.basename(dest))
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            got = 0
            step = 4 << 20
            nxt = step
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if got >= nxt:
                    nxt += step
                    if total:
                        sys.stdout.write("    %s / %s (%d%%)\r" % (human(got), human(total), got * 100 // total))
                    else:
                        sys.stdout.write("    %s\r" % human(got))
                    sys.stdout.flush()
        os.replace(tmp, dest)
        print("    完成 %s            " % human(os.path.getsize(dest)))
        return True
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        print("    失败：%s" % e)
        print("    可稍后重跑；也能手动下载后放到 data/ 目录（见 README）")
        return False


def main():
    force = "--force" in sys.argv
    print("=" * 60)
    print("  下载建库数据 -> %s" % DATA)
    print("=" * 60)
    ok = True

    ok &= download(*CMUDICT, force=force)
    ok &= download(*ECDICT, force=force)

    # 句对是 zip，要解出 cmn.txt
    txt = os.path.join(DATA, "cmn.txt")
    if os.path.exists(txt) and not force:
        print("  跳过（已存在 %s）：cmn.txt" % human(os.path.getsize(txt)))
    else:
        zpath = os.path.join(DATA, "cmn-eng.zip")
        if download(*ANKI, force=force):
            try:
                with zipfile.ZipFile(zpath) as z:
                    z.extractall(DATA)
                print("    解压出 cmn.txt")
                os.remove(zpath)
                for junk in ("_about.txt",):
                    p = os.path.join(DATA, junk)
                    if os.path.exists(p):
                        os.remove(p)
            except Exception as e:
                print("    解压失败：%s" % e)
                ok = False

    print()
    if os.path.exists(os.path.join(DATA, "vocab-source.csv")):
        print("  词表 data/vocab-source.csv 已在仓库里，无需下载")
    else:
        print("  ! 缺少 data/vocab-source.csv（词频表），建库会失败")
        ok = False

    print()
    if ok:
        print("  数据就绪。下一步： python import_data.py  然后 python app.py")
    else:
        print("  有项目下载失败，处理后可重跑本脚本（已成功的会自动跳过）")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
