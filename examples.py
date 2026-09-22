# -*- coding: utf-8 -*-
"""例句引擎。

数据来源：Tatoeba 的英汉句对（经 manythings.org 打包，CC-BY 2.0 FR），
共约 3.2 万对。为每个单词挑 1-3 条「短、自然、含该词（或它的常见变形）」的句子，
并记下句子里的实际词形，供前端高亮。

思路
----
先把所有句子按长度升序排好再建索引，这样每个词形对应的候选列表
天然是「从短到长」，取前 N 条就是最好用的那批，不必全量扫描。
"""
from __future__ import annotations

import re

import trad2simp as t2s

# 只保留「短句」，太长的不适合做单词例句
MIN_LEN, MAX_LEN = 15, 130
IDEAL_LEN = 62          # 排序时最想要的句长
SCAN_PER_FORM = 250     # 每个词形最多看多少条候选

_SENT_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")

# 句子与索引（模块级，load 之后填充）
SENTENCES = []
_INDEX = {}


def variants(word: str):
    """受控的词形变化集合。

    只认真正属于这个词的变形，避免 abandon 命中 abandonment 这类噪音。
    """
    w = word.lower().strip()
    out = {w}
    if len(w) < 2:
        return out
    if w.endswith("e"):
        out |= {w[:-1] + "ing", w[:-1] + "ed", w + "d", w + "s"}
    elif w.endswith("y") and len(w) > 2 and w[-2] not in "aeiou":
        out |= {w[:-1] + "ies", w[:-1] + "ied", w + "s", w + "ing"}
    else:
        out |= {w + "s", w + "es", w + "ed", w + "ing", w + "er", w + "est", w + "ly"}
        # 双写辅音：run -> running / stopped
        if len(w) > 2 and w[-1] not in "aeiou" and w[-2] in "aeiou":
            out |= {w + w[-1] + "ing", w + w[-1] + "ed"}
        # 双写词尾还原：stopped 这类在 variants 里已经覆盖，这里补 -er/-est
        if len(w) > 3 and w[-1] == w[-2] and w[-1] not in "aeiou":
            out |= {w[:-1] + "ing", w[:-1] + "ed"}
    return out


def load(path: str) -> int:
    """读取 cmn.txt（英文 TAB 中文 TAB 来源），按句长升序建索引。"""
    global SENTENCES, _INDEX
    pairs = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            en = parts[0].strip()
            # 语料里约 44% 的译文是繁体，统一转成简体再入库
            zh = t2s.to_simplified(parts[1].strip())
            if not en or not zh:
                continue
            if len(en) < MIN_LEN or len(en) > MAX_LEN:
                continue
            if len(en.split()) < 3:
                continue
            pairs.append((en, zh))
    # 短句优先，索引里的候选天然从短到长
    pairs.sort(key=lambda p: len(p[0]))
    SENTENCES = pairs
    idx = {}
    for i, (en, _zh) in enumerate(pairs):
        for t in set(_SENT_RE.findall(en)):
            idx.setdefault(t.lower(), []).append(i)
    _INDEX = idx
    return len(pairs)


def pick(word: str, limit: int = 3):
    """为 word 挑例句 -> [{"en":..., "zh":..., "form":...}]"""
    if not _INDEX:
        return []
    w = word.lower().strip()
    if not w or " " in w:          # 词组暂不处理
        return []
    cands = []
    seen = set()
    for form in variants(w):
        lst = _INDEX.get(form)
        if not lst:
            continue
        for i in lst[:SCAN_PER_FORM]:
            if i in seen:
                continue
            seen.add(i)
            en, zh = SENTENCES[i]
            # 同一句里这个词形出现几次都行，只挑一次
            cands.append((0 if form == w else 1, abs(len(en) - IDEAL_LEN), i, form))
    cands.sort()
    out, used = [], set()
    for _rank, _d, i, form in cands:
        if i in used:
            continue
        used.add(i)
        en, zh = SENTENCES[i]
        out.append({"en": en, "zh": zh, "form": form})
        if len(out) >= limit:
            break
    return out


def build(words, path: str, limit: int = 3):
    """words -> {word: [例句...]}，只返回挑到例句的词。"""
    n = load(path)
    print("例句库载入 %d 条（英汉句对）" % n)
    out = {}
    for w in words:
        got = pick(w, limit)
        if got:
            out[w] = got
    return out
