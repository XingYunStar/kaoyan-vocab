# -*- coding: utf-8 -*-
"""建库脚本：把词频 CSV + cmudict 音标导入 SQLite。

用法：  python import_data.py
幂等：重复运行会重建 words 表，但保留 progress / review_log / notes / settings。
"""
from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ecdict as ec
import examples as exm
import mnemonic as mn

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "data", "vocab.db")
# 词表：仓库里自带 data/vocab-source.csv；若没有则回退到开发时放在上一级的导出文件
CSV_PATH = os.path.join(HERE, "data", "vocab-source.csv")
if not os.path.exists(CSV_PATH):
    CSV_PATH = os.path.join(os.path.dirname(HERE), "考研英语真题词频表.csv")
CMU_PATH = os.path.join(HERE, "data", "cmudict.dict")
ECDICT_PATH = os.path.join(HERE, "data", "ecdict.csv")
EXAMPLES_PATH = os.path.join(HERE, "data", "cmn.txt")

# ------------------------------------------------------------------ ARPAbet -> IPA
ARPABET = {
    "AA": "ɑ", "AE": "æ", "AH": ("ə", "ʌ"), "AO": "ɔ", "AW": "aʊ", "AY": "aɪ",
    "EH": "e", "ER": ("ɚ", "ɜː"), "EY": "eɪ", "IH": "ɪ", "IY": "iː",
    "OW": "oʊ", "OY": "ɔɪ", "UH": "ʊ", "UW": "uː",
    "B": "b", "CH": "tʃ", "D": "d", "DH": "ð", "F": "f", "G": "ɡ", "HH": "h",
    "JH": "dʒ", "K": "k", "L": "l", "M": "m", "N": "n", "NG": "ŋ", "P": "p",
    "R": "r", "S": "s", "SH": "ʃ", "T": "t", "TH": "θ", "V": "v", "W": "w",
    "Y": "j", "Z": "z", "ZH": "ʒ",
}
VOWELS = {"AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY", "IH", "IY",
          "OW", "OY", "UH", "UW"}


def arpabet_to_ipa(tokens):
    """带重音的 ARPAbet -> IPA 字符串，例如 AH0 B AE1 N D AH0 N -> əˈbændən"""
    out = []          # 输出符号
    kinds = []        # 每个符号是否为元音
    for tok in tokens:
        m = re.match(r"^([A-Z]+)([0-2]?)$", tok)
        if not m:
            continue
        base, stress = m.group(1), m.group(2)
        if base not in ARPABET:
            continue
        is_vowel = base in VOWELS
        if is_vowel:
            val = ARPABET[base]
            sym = val[0] if stress == "0" else (val[1] if isinstance(val, tuple) else val)
            if stress in ("1", "2"):
                # 重音符号加在本音节的起始辅音之前
                pos = len(out)
                while pos > 0 and not kinds[pos - 1]:
                    pos -= 1
                out.insert(pos, "ˈ" if stress == "1" else "ˌ")
                kinds.insert(pos, False)
                # 重音符号后面的元音才真正落位
            out.append(sym)
            kinds.append(True)
        else:
            out.append(ARPABET[base])
            kinds.append(False)
    return "".join(out)


def load_cmudict():
    table = {}
    if not os.path.exists(CMU_PATH):
        print("! 未找到 cmudict.dict，跳过音标（可稍后用 --enrich 在线补齐）")
        return table
    with open(CMU_PATH, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(";;;"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            w = parts[0].lower()
            if w.endswith(")") and "(" in w:      # 舍弃 abandon(2) 这类异读
                continue
            if w in table:
                continue
            ipa = arpabet_to_ipa(parts[1:])
            if ipa:
                table[w] = ipa
    return table


# ------------------------------------------------------------------ 建库
SCHEMA = """
CREATE TABLE IF NOT EXISTS words (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    rank        INTEGER,
    word        TEXT UNIQUE NOT NULL,
    freq        INTEGER DEFAULT 0,
    tier        TEXT,
    meaning     TEXT,
    category    TEXT,
    subcategory TEXT,
    collocation TEXT,
    alt         TEXT,
    remark      TEXT,
    phonetic_us TEXT,
    phonetic_uk TEXT,
    audio_us    TEXT,
    audio_uk    TEXT,
    example_en  TEXT,
    example_zh  TEXT,
    root        TEXT,
    base        TEXT,
    basic       INTEGER DEFAULT 0,
    enriched    INTEGER DEFAULT 0,
    pos_primary TEXT,
    pos_ratio   TEXT,
    pos_json    TEXT,
    examples    TEXT
);
CREATE INDEX IF NOT EXISTS idx_words_base ON words(base);
CREATE INDEX IF NOT EXISTS idx_words_tier ON words(tier);

CREATE TABLE IF NOT EXISTS progress (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    word_id     INTEGER NOT NULL,
    round       INTEGER NOT NULL,
    state       TEXT    DEFAULT 'new',
    ease        REAL    DEFAULT 2.5,
    interval    REAL    DEFAULT 0,
    due         TEXT,
    reps        INTEGER DEFAULT 0,
    correct     INTEGER DEFAULT 0,
    wrong       INTEGER DEFAULT 0,
    lapses      INTEGER DEFAULT 0,
    last_rating TEXT,
    last_review TEXT,
    total_ms    INTEGER DEFAULT 0,
    UNIQUE(word_id, round)
);
CREATE INDEX IF NOT EXISTS idx_prog_due ON progress(due, state);
CREATE INDEX IF NOT EXISTS idx_prog_word ON progress(word_id);

CREATE TABLE IF NOT EXISTS review_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    word_id       INTEGER NOT NULL,
    round         INTEGER NOT NULL,
    rating        TEXT,
    prev_interval REAL,
    new_interval  REAL,
    ease          REAL,
    ms            INTEGER DEFAULT 0,
    created_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_log_time ON review_log(created_at);

CREATE TABLE IF NOT EXISTS notes (
    word_id    INTEGER PRIMARY KEY,
    text       TEXT DEFAULT '',
    starred    INTEGER DEFAULT 0,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS daily (
    date         TEXT PRIMARY KEY,
    new_count    INTEGER DEFAULT 0,
    review_count INTEGER DEFAULT 0,
    correct      INTEGER DEFAULT 0,
    wrong        INTEGER DEFAULT 0,
    ms           INTEGER DEFAULT 0
);
"""

# 基础功能词：冠词/代词/介词/连词/助动词/限定词。对考研考生属于已知词，
# 默认不进入新词队列（可在设置里关掉这个过滤）。
BASIC_WORDS = set("""
a an the i me my mine myself we us our ours ourselves you your yours yourself yourselves
he him his himself she her hers herself it its itself they them their theirs themselves
this that these those who whom whose which what whatever whoever one ones someone anyone
everyone nobody somebody anybody everybody something anything everything nothing
of to in for on with at by from into about as up out over after before between under
above below during through against among within without across behind beyond toward
towards upon onto off down along around near since until till per via
and or but nor so yet if because although though while whereas unless whether than when
where why how both either neither
be am is are was were been being have has had having do does did done doing
will would shall should can could may might must ought need dare used
all any each every few many much no none some such more most other another same own
several enough less least little
not only also too very just even still already always never often sometimes usually
here there now then thus hence however therefore moreover furthermore nevertheless
otherwise instead rather quite perhaps maybe indeed else
""".split())


DEFAULT_SETTINGS = {
    "exam_date": "2026-12-19",       # 2027 考研初试（预计），可在设置里改
    "exam_name": "2027 考研初试",
    "rounds": "3",                    # 每个单词要过几轮
    "daily_new": "0",                 # 0 = 自动按倒计时摊派
    "tiers": json.dumps(["核心高频", "高频"], ensure_ascii=False),
    "skip_basic": "1",
    "show_pos": "1",
    "batch_size": "20",
    "theme": "auto",
    "accent": "#c0392b",
    "speech_rate": "0.85",
    "speech_lang": "en-US",
    "auto_play": "1",
    "graduation": json.dumps([3, 7, 21]),   # 每一轮的毕业间隔（天）
    "created_at": "",
}


def main():
    os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
    fresh = not os.path.exists(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    # 旧库迁移
    cols = [r[1] for r in conn.execute("PRAGMA table_info(words)")]
    if "basic" not in cols:
        conn.execute("ALTER TABLE words ADD COLUMN basic INTEGER DEFAULT 0")
        conn.commit()
    for col in ("pos_primary", "pos_ratio", "pos_json", "examples"):
        if col not in cols:
            conn.execute("ALTER TABLE words ADD COLUMN %s TEXT" % col)
            conn.commit()
    conn.execute("CREATE INDEX IF NOT EXISTS idx_words_basic ON words(basic)")
    conn.commit()

    # ---------- 读取 CSV ----------
    if not os.path.exists(CSV_PATH):
        print("! 找不到词表 CSV：" + CSV_PATH)
        return 1
    with open(CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
        raw = list(csv.DictReader(f))
    print("CSV 读入 %d 行" % len(raw))

    # ---------- 音标 ----------
    cmu = load_cmudict()
    print("cmudict 载入 %d 条" % len(cmu))

    def ipa_for(word):
        w = word.lower().strip()
        if w in cmu:
            return cmu[w]
        # 多词短语 / 连字符：逐个拼
        bits = re.split(r"[\s\-]+", w)
        if len(bits) > 1:
            got = [cmu.get(b) for b in bits if b]
            if got and all(got):
                return " ".join(got)
        # 去掉词尾变化再试
        for suf in ("s", "es", "ed", "d", "ing", "ly", "er", "est"):
            if w.endswith(suf) and w[: -len(suf)] in cmu:
                return cmu[w[: -len(suf)]]
        return None

    # ---------- 词性释义（ECDICT）----------
    words_all = [(r.get("单词") or "").strip() for r in raw]
    words_all = [w for w in words_all if w]
    ed = {}
    if os.path.exists(ECDICT_PATH):
        print("读取 ECDICT（流式扫描，只保留需要的 %d 词）..." % len(words_all))
        ed = ec.load_for(ECDICT_PATH, set(words_all))
        print("ECDICT 命中 %d / %d" % (len(ed), len(words_all)))
    else:
        print("! 未找到 data/ecdict.csv，跳过词性释义（可重新下载后重跑本脚本）")

    # ---------- 例句（Tatoeba 英汉句对，已转简体）----------
    exs = {}
    if os.path.exists(EXAMPLES_PATH):
        exs = exm.build(words_all, EXAMPLES_PATH, limit=3)
        print("例句命中 %d / %d" % (len(exs), len(words_all)))
    else:
        print("! 未找到 data/cmn.txt，跳过例句（下载后重跑本脚本即可）")

    rows = []
    hit = 0
    pos_hit = 0
    for r in raw:
        word = (r.get("单词") or "").strip()
        if not word:
            continue
        ipa = ipa_for(word)
        if ipa:
            hit += 1
        tier = (r.get("梯队") or "").strip()
        e = ed.get(word.lower())
        groups, pos_primary, pos_ratio = [], "", ""
        if e and e["groups"]:
            groups = e["groups"]
            pos_primary = ec.primary_pos(groups, e["pos"])
            pos_ratio = e["pos"]
            pos_hit += 1
        rows.append((
            int(r["排名"]) if (r.get("排名") or "").strip().isdigit() else None,
            word,
            int(r.get("词频") or 0),
            tier,
            (r.get("释义") or "").strip(),
            (r.get("分类") or "").strip(),
            (r.get("子分类") or "").strip(),
            (r.get("真题搭配") or "").strip(),
            (r.get("其他拼写") or "").strip(),
            (r.get("备注") or "").strip(),
            ipa,
            mn.base_form(word),
            mn.analyze(word)["root"],
            1 if word.lower() in BASIC_WORDS else 0,
            pos_primary,
            pos_ratio,
            json.dumps(groups, ensure_ascii=False) if groups else None,
            json.dumps(exs[word], ensure_ascii=False) if word in exs else None,
        ))
    print("音标命中 %d / %d，词性释义命中 %d / %d" % (hit, len(rows), pos_hit, len(rows)))

    conn.executemany(
        """INSERT INTO words (rank,word,freq,tier,meaning,category,subcategory,
                              collocation,alt,remark,phonetic_us,base,root,basic,
                              pos_primary,pos_ratio,pos_json,examples)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(word) DO UPDATE SET
             rank=excluded.rank, freq=excluded.freq, tier=excluded.tier,
             meaning=excluded.meaning, category=excluded.category,
             subcategory=excluded.subcategory, collocation=excluded.collocation,
             alt=excluded.alt, remark=excluded.remark,
             phonetic_us=COALESCE(excluded.phonetic_us, words.phonetic_us),
             base=excluded.base, root=excluded.root, basic=excluded.basic,
             pos_primary=excluded.pos_primary, pos_ratio=excluded.pos_ratio,
             pos_json=COALESCE(excluded.pos_json, words.pos_json),
             examples=COALESCE(excluded.examples, words.examples)""",
        rows,
    )
    conn.commit()

    # ---------- 默认设置 ----------
    import datetime
    for k, v in DEFAULT_SETTINGS.items():
        v = datetime.date.today().isoformat() if k == "created_at" and not v else v
        conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)", (k, v))
    conn.commit()

    n = conn.execute("SELECT COUNT(*) FROM words").fetchone()[0]
    b = conn.execute("SELECT COUNT(*) FROM words WHERE basic=1").fetchone()[0]
    p = conn.execute("SELECT COUNT(*) FROM words WHERE pos_json IS NOT NULL").fetchone()[0]
    e = conn.execute("SELECT COUNT(*) FROM words WHERE examples IS NOT NULL").fetchone()[0]
    print("words 表共 %d 词（基础功能词 %d 个；词性释义 %d 个；例句 %d 个）" % (n, b, p, e))
    for t, c in conn.execute(
            "SELECT tier, COUNT(*) FROM words GROUP BY tier ORDER BY COUNT(*) DESC"):
        print("   %-16s %d" % (t, c))
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
