# -*- coding: utf-8 -*-
"""ECDICT 词性释义支持。

数据来源：https://github.com/skywind3000/ECDICT （MIT / CC BY-SA 3.0）
它的 translation 字段天然就是「按词性分行」的中文释义，例如：

    abandon  ->  "n. 放任, 狂热\nvt. 放弃, 遗弃, 抛弃"

本模块只做两件事：
  1. 流式读取 ecdict.csv，只保留词表里需要的单词（不把 66MB 全读进内存）；
  2. 把 translation 解析成 [{pos, pos_zh, senses[]}] 结构。
"""
from __future__ import annotations

import csv
import re

# 词性缩写 -> 中文全称（界面上直接用全称，不写「名」「形」这类缩写）
POS_ZH = {
    "n": "名词", "v": "动词", "vt": "及物动词", "vi": "不及物动词",
    "adj": "形容词", "a": "形容词", "adv": "副词", "ad": "副词",
    "prep": "介词", "conj": "连词", "pron": "代词", "num": "数词",
    "art": "冠词", "int": "感叹词", "interj": "感叹词", "aux": "助动词",
    "abbr": "缩写", "pl": "复数", "u": "不可数名词", "c": "可数名词",
    "suff": "后缀", "pref": "前缀", "phr": "短语", "refl": "反身代词",
    "poss": "物主代词", "dem": "指示代词", "rel": "关系代词",
}

# 词典里的专业领域标记同样是单字缩写，一并展开
DOMAIN_ZH = {
    "计": "计算机", "经": "经济", "机": "机械", "医": "医学", "化": "化学",
    "法": "法律", "哲": "哲学", "政": "政治", "史": "历史", "文": "文学",
    "物": "物理", "数": "数学", "律": "法律", "商": "商业", "农": "农业",
    "军": "军事", "电": "电子", "生": "生物", "天": "天文", "地": "地质",
    "心": "心理", "语": "语言", "音": "音乐", "体": "体育", "宗": "宗教",
    "冶": "冶金", "纺": "纺织", "建": "建筑", "航": "航海", "矿": "矿业",
    "摄": "摄影", "戏": "戏剧", "诗": "诗歌", "修": "修辞", "逻": "逻辑",
    "统": "统计", "会": "会计", "贸": "贸易", "管": "管理", "教": "教育",
}
# 词性在句法上的分量，用于挑「主词性」
POS_WEIGHT = {"n": 5, "vt": 4, "vi": 4, "v": 4, "adj": 3, "adv": 2, "a": 3}

# 每个词性最多保留的义项数（再多对背单词无意义）
MAX_SENSES = 12

_POS_LINE = re.compile(r"^\s*((?:[a-z]{1,6}\.\s*)+)(.+)$")
# [计] [经] [机] 这类是词典的「专业领域」标记，不是词性
_DOMAIN_LINE = re.compile(r"^\s*\[([^\]]+)\]\s*(.+)$")


def _split_pos(tag_blob):
    return [t.strip().rstrip(".") for t in tag_blob.split(".") if t.strip()]


def parse_translation(text: str):
    """解析 ECDICT 的 translation -> [{pos, pos_zh, senses, raw}]"""
    if not text:
        return []
    t = text.replace("\\n", "\n").replace("\r", "")
    groups = []
    for line in t.split("\n"):
        line = line.strip().strip("\\").strip()
        if not line:
            continue
        dm = _DOMAIN_LINE.match(line)
        if dm:
            body = dm.group(2).strip()
            if body:
                dom = dm.group(1).strip()
                groups.append({
                    "pos": "", "pos_zh": "专业", "kind": "domain",
                    "domain": dom, "domain_zh": DOMAIN_ZH.get(dom, dom),
                    "senses": [s.strip() for s in
                               re.split(r"[,;；，]\s*", body) if s.strip()][:MAX_SENSES],
                    "raw": line,
                })
            continue
        m = _POS_LINE.match(line)
        if m:
            tags = _split_pos(m.group(1))
            body = m.group(2).strip()
        else:
            tags, body = [], line
        if not body:
            continue
        senses = [s.strip() for s in re.split(r"[,;；，]\s*", body) if s.strip()]
        primary = tags[0] if tags else ""
        groups.append({
            "pos": ".".join(tags) if tags else "",
            # 少数行没有词性前缀，标成「释义」，不要在界面上出现空标签
            "pos_zh": POS_ZH.get(primary, primary.upper() if primary else "释义"),
            "kind": "pos" if tags else "other",
            # 存全部义项（上限 12，再多对背单词没有意义）。
            # 界面上默认只显示前几个，剩下的靠「展开全部 N 义」点开。
            "senses": senses[:MAX_SENSES],
            "raw": line,
        })
    return groups


def primary_pos(groups, ratio=""):
    """挑出主词性。

    优先用 ECDICT 的 pos 比例（如 "n:67/v:33"）；没有比例时按词典自身的
    排列顺序取第一个词性 —— 这正是词典「先列主要义项」的惯例，
    比按权重猜更可靠（否则 abandon 会被猜成名词）。
    """
    if ratio:
        best, bestv = "", -1
        for part in ratio.replace("；", ";").split(";"):
            if ":" not in part:
                continue
            k, v = part.split(":", 1)
            try:
                v = float(v)
            except ValueError:
                continue
            if v > bestv:
                best, bestv = k.strip(), v
        if best:
            return POS_ZH.get(best, best)
    for g in groups:
        if g.get("kind") == "pos" and g["pos_zh"]:
            return g["pos_zh"]
    return ""



def load_for(path, wanted, progress=None):
    """流式扫描 ecdict.csv，只返回 wanted 里的词条。

    wanted: set of lowercase words
    返回: {word: {"translation": str, "pos": str, "groups": [...]}}
    """
    wanted = {w.lower() for w in wanted}
    found = {}
    with open(path, "r", encoding="utf-8", errors="ignore", newline="") as f:
        rd = csv.DictReader(f)
        for i, row in enumerate(rd):
            w = (row.get("word") or "").strip().lower()
            if not w or w not in wanted or w in found:
                continue
            groups = parse_translation(row.get("translation") or "")
            found[w] = {
                "translation": (row.get("translation") or "").strip(),
                "pos": (row.get("pos") or "").strip(),
                "groups": groups,
                "collins": (row.get("collins") or "").strip(),
                "oxford": (row.get("oxford") or "").strip(),
                "tag": (row.get("tag") or "").strip(),
                "exchange": (row.get("exchange") or "").strip(),
            }
            if progress and len(found) % 500 == 0:
                progress(len(found))
            if len(found) >= len(wanted):
                break
    return found


def form_plain(groups, limit=3):
    """一行紧凑显示：名 放任 | 动 放弃、抛弃（跳过专业领域义项）"""
    parts = []
    for g in groups:
        if g.get("kind") == "domain":
            continue
        body = "、".join(g["senses"][:3])
        parts.append((g["pos_zh"] + " " + body).strip())
        if len(parts) >= limit:
            break
    return " ｜ ".join(parts)
