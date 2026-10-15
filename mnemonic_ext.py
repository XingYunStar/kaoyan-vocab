# -*- coding: utf-8 -*-
"""外部助记资源解析。

数据来源：vxiaozhi/vocabulary-book-by-deepseek（Apache-2.0）
每个单词一个 JSON：

    {"word": "...", "analysis": "### 分析词义 ... ### 词根分析 ...",
     "draw_explain": "助记图想表达什么", "draw_prompt": "图像生成提示词"}

analysis 是一篇 markdown 长文，按 "### 标题" 分成若干节。
这里把它拆成结构化的小节，既方便前端渲染，也避免把 3KB 长文整块塞进卡片。
"""
from __future__ import annotations

import json
import os
import re

# 卡片上默认展开的小节（词根/词缀优先）
KEY_SECTIONS = ("词根分析", "词缀分析", "联想", "记忆技巧")

_HEAD = re.compile(r"^#{2,4}\s*(.+?)\s*$", re.M)
_CODE = re.compile("[\x60]{1,3}")                 # markdown 的行内/围栏代码标记
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_BULLET = re.compile(r"^\s*[-*]\s*", re.M)


def parse_sections(md: str):
    """把 markdown 按标题拆成 [{title, body}]，丢掉空节。"""
    if not md:
        return []
    out = []
    marks = list(_HEAD.finditer(md))
    if not marks:
        body = md.strip()
        return [{"title": "解析", "body": body}] if body else []
    for i, m in enumerate(marks):
        title = m.group(1).strip()
        start = m.end()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(md)
        body = md[start:end].strip()
        if body:
            out.append({"title": title, "body": body})
    return out


def load_one(path: str):
    """读取单个助记 JSON -> 结构化记录。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return None
    secs = parse_sections(d.get("analysis") or "")
    de = (d.get("draw_explain") or "").strip()
    if not secs and not de:
        return None
    return {"sections": secs, "draw_explain": de,
            "titles": [s["title"] for s in secs]}


def load_dir(path: str, wanted=None, progress=None):
    """读取整个目录 -> {单词: 记录}。wanted 给定时只保留这些词。"""
    if not os.path.isdir(path):
        return {}
    out = {}
    names = sorted(os.listdir(path))
    for i, fn in enumerate(names):
        if not fn.endswith(".json"):
            continue
        w = fn[:-5]
        if wanted is not None and w not in wanted:
            continue
        rec = load_one(os.path.join(path, fn))
        if rec:
            out[w] = rec
        if progress and (i + 1) % 1000 == 0:
            progress(i + 1, len(names))
    return out


def key_sections(rec, limit=3):
    """挑出卡片上默认展示的小节（词根/词缀优先）。"""
    if not rec:
        return []
    secs = rec.get("sections") or []
    picked = [s for s in secs if s["title"] in KEY_SECTIONS]
    if not picked:
        picked = secs[:1]
    return picked[:limit]


def compact(md: str, max_len: int = 320) -> str:
    """把 markdown 压成单行纯文本，用于卡片上的短说明。"""
    t = _BOLD.sub(r"\1", md or "")
    t = _BULLET.sub("· ", t)
    t = _CODE.sub("", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:max_len] + ("…" if len(t) > max_len else "")
