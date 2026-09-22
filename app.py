# -*- coding: utf-8 -*-
"""考研单词背诵系统 —— 后端。

启动：  python app.py          （默认 http://127.0.0.1:5178）

HTTP 层用项目自带的 liteweb（纯标准库），不依赖 Flask —— 详见 liteweb.py。
"""
from __future__ import annotations

import datetime
import json
import os
import sqlite3
import sys
import urllib.parse
import urllib.request

# 用标准库实现的 liteweb 代替 Flask：整个项目 0 第三方依赖，
# 任意 Python 3.9+ 直接可跑，不必先 pip install。
from liteweb import Flask, g, jsonify, request, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mnemonic as mn
import srs

DB_PATH = os.path.join(HERE, "data", "vocab.db")
STATIC = os.path.join(HERE, "static")

app = Flask(__name__, static_folder=None)
app.json.ensure_ascii = False


# ----------------------------------------------------------------- 数据库
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    d = g.pop("db", None)
    if d is not None:
        d.close()


def get_settings():
    s = {}
    for r in db().execute("SELECT key,value FROM settings"):
        s[r["key"]] = r["value"]
    for k in ("rounds", "batch_size", "speech_rate"):
        try:
            s[k] = int(float(s.get(k, 0))) if k != "speech_rate" else float(s.get(k, 0.85))
        except Exception:
            pass
    for k in ("auto_play", "skip_basic", "show_pos"):
        s[k] = str(s.get(k, "1")) in ("1", "true", "True")
    for k in ("tiers", "graduation"):
        try:
            s[k] = json.loads(s.get(k) or "[]")
        except Exception:
            s[k] = []
    return s


def save_settings(patch):
    for k, v in patch.items():
        if isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False)
        elif isinstance(v, bool):
            v = "1" if v else "0"
        db().execute("INSERT INTO settings(key,value) VALUES (?,?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))
    db().commit()


def graduation_list(s=None):
    s = s or get_settings()
    gl = s.get("graduation") or [3, 7, 21]
    rounds = int(s.get("rounds", 3))
    while len(gl) < rounds:
        gl.append(gl[-1] * 3)
    return [float(x) for x in gl[:rounds]]


def today_str():
    return datetime.date.today().isoformat()


DAILY_FIELDS = {"new_count", "review_count", "correct", "wrong", "ms"}


def bump_daily(**fields):
    """bump_daily(new_count=1, ms=3200) —— 累加今天的统计。"""
    fields = {k: v for k, v in fields.items() if k in DAILY_FIELDS}
    if not fields:
        return
    d = today_str()
    db().execute("INSERT OR IGNORE INTO daily(date) VALUES (?)", (d,))
    sets = ", ".join("%s = %s + ?" % (k, k) for k in fields)
    db().execute("UPDATE daily SET %s WHERE date = ?" % sets,
                 list(fields.values()) + [d])
    db().commit()


# ----------------------------------------------------------------- 进度
def ensure_round(word_id, rnd):
    row = db().execute("SELECT * FROM progress WHERE word_id=? AND round=?",
                       (word_id, rnd)).fetchone()
    if row:
        return row
    db().execute("INSERT INTO progress(word_id,round,state,due) VALUES (?,?,'new',?)",
                 (word_id, rnd, srs.iso(srs.now())))
    db().commit()
    return db().execute("SELECT * FROM progress WHERE word_id=? AND round=?",
                        (word_id, rnd)).fetchone()


def word_progress(word_id, rounds):
    """返回该词每一轮的状态，并判断总体状态。"""
    rows = {r["round"]: dict(r) for r in
            db().execute("SELECT * FROM progress WHERE word_id=?", (word_id,))}
    out = []
    for r in range(1, rounds + 1):
        out.append(rows.get(r))
    return out


def progress_map(word_ids, rounds):
    if not word_ids:
        return {}
    q = ",".join("?" * len(word_ids))
    m = {}
    for r in db().execute("SELECT * FROM progress WHERE word_id IN (%s)" % q, word_ids):
        m.setdefault(r["word_id"], {})[r["round"]] = dict(r)
    return m


def unlocked_round(rounds_map, rounds):
    """当前该学第几轮：最低的「已解锁且未毕业」的那一轮。"""
    if not rounds_map:
        return 1
    for r in range(1, rounds + 1):
        st = rounds_map.get(r)
        if st is None or st["state"] != "graduated":
            return r
    return rounds


# ----------------------------------------------------------------- 卡片
def row_to_card(w, prog=None):
    d = dict(w)
    d.pop("enriched", None)
    # pos_json 是 ECDICT 解析出的「按词性分组的释义」，转成结构化数组下发
    raw = d.pop("pos_json", None)
    try:
        d["pos"] = json.loads(raw) if raw else []
    except Exception:
        d["pos"] = []
    raw_ex = d.pop("examples", None)
    try:
        d["examples"] = json.loads(raw_ex) if raw_ex else []
    except Exception:
        d["examples"] = []
    if prog:
        d["round"] = prog["round"]
        d["state"] = prog["state"]
        d["interval"] = prog["interval"]
        d["ease"] = prog["ease"]
        d["reps"] = prog["reps"]
        d["due"] = prog["due"]
    return d


def fetch_words(ids):
    if not ids:
        return {}
    q = ",".join("?" * len(ids))
    return {r["id"]: r for r in db().execute("SELECT * FROM words WHERE id IN (%s)" % q, ids)}


def note_of(word_id):
    r = db().execute("SELECT text,starred FROM notes WHERE word_id=?", (word_id,)).fetchone()
    return (r["text"], r["starred"]) if r else ("", 0)


# ----------------------------------------------------------------- 路由：页面
@app.route("/")
def index():
    return no_cache(send_from_directory(STATIC, "index.html"))


@app.route("/<path:path>")
def static_files(path):
    return no_cache(send_from_directory(STATIC, path))


def no_cache(resp):
    """本地开发用：禁用静态资源缓存，改完 CSS/JS 刷新就能看到。"""
    resp.headers["Cache-Control"] = "no-store, must-revalidate"
    return resp


# ----------------------------------------------------------------- 路由：基础
@app.get("/api/bootstrap")
def api_bootstrap():
    s = get_settings()
    rounds = int(s.get("rounds", 3))
    gl = graduation_list(s)
    total = db().execute("SELECT COUNT(*) c FROM words").fetchone()["c"]
    tiers = [dict(r) for r in db().execute(
        "SELECT tier, COUNT(*) c FROM words GROUP BY tier ORDER BY c DESC")]

    sel = s.get("tiers") or []
    where, wargs = "", []
    if sel:
        where += " AND tier IN (%s)" % ",".join("?" * len(sel))
        wargs += sel
    if s.get("skip_basic"):
        where += " AND basic = 0"
    sel_total = db().execute(
        "SELECT COUNT(*) c FROM words WHERE 1=1" + where, wargs).fetchone()["c"]
    basic_n = db().execute("SELECT COUNT(*) c FROM words WHERE basic=1").fetchone()["c"]

    # 已开始学的词（轮 1 存在进度）
    learned = db().execute(
        "SELECT COUNT(DISTINCT word_id) c FROM progress WHERE round=1 "
        "AND state != 'new'").fetchone()["c"]
    graduated = db().execute(
        "SELECT COUNT(*) c FROM progress WHERE round=? AND state='graduated'",
        (rounds,)).fetchone()["c"]

    now = srs.iso(srs.now())
    due = db().execute(
        "SELECT COUNT(*) c FROM progress WHERE state IN ('learning','review','graduated') "
        "AND due <= ?", (now,)).fetchone()["c"]

    # 未毕业的轮次总数（用于倒计时摊派）
    pending_rounds = db().execute(
        "SELECT COUNT(*) c FROM progress WHERE state != 'graduated'").fetchone()["c"]
    pending_rounds += max(0, sel_total - db().execute(
        "SELECT COUNT(DISTINCT word_id) c FROM progress").fetchone()["c"]) * rounds

    days = srs.days_left(s.get("exam_date"))
    plan = srs.daily_plan(sel_total, learned, due, days, rounds, pending_rounds)

    return jsonify({
        "settings": s, "rounds": rounds, "graduation": gl,
        "exam_date": s.get("exam_date"), "exam_name": s.get("exam_name"),
        "counts": {"total": total, "selected": sel_total, "learned": learned,
                   "graduated": graduated, "due": due, "basic": basic_n,
                   "new_left": max(0, sel_total - learned)},
        "tiers": tiers, "plan": plan,
        "today": dict(db().execute("SELECT * FROM daily WHERE date=?", (today_str(),)).fetchone()
                      or {"date": today_str(), "new_count": 0, "review_count": 0,
                          "correct": 0, "wrong": 0, "ms": 0}),
    })


@app.get("/api/session")
def api_session():
    """取一批待学卡片。mode = mix | new | review"""
    s = get_settings()
    rounds = int(s.get("rounds", 3))
    gl = graduation_list(s)
    mode = request.args.get("mode", "mix")
    limit = int(request.args.get("limit") or s.get("batch_size") or 20)
    tiers = request.args.get("tiers")
    tiers = tiers.split(",") if tiers else (s.get("tiers") or [])

    now = srs.iso(srs.now())
    cards, seen = [], set()

    # ---- 1) 到期复习（含刚解锁的下一轮） ----
    # 只有「当前轮」参与复习：已毕业的轮次冻结，不重复推送。
    # 新解锁的下一轮 state='new' 且 due=now，会立刻进入队列。
    if mode in ("mix", "review"):
        sql = ("SELECT p.* FROM progress p JOIN words w ON w.id=p.word_id "
               "WHERE p.due <= ? AND p.state != 'graduated'")
        args = [now]
        if tiers:
            sql += " AND w.tier IN (%s)" % ",".join("?" * len(tiers))
            args += tiers
        sql += " ORDER BY p.round ASC, p.due ASC LIMIT ?"
        args.append(limit)
        for p in db().execute(sql, args):
            cards.append(p)
            seen.add(p["word_id"])

    # ---- 2) 新词 ----
    if mode in ("mix", "new") and len(cards) < limit:
        need = limit - len(cards)
        sql = ("SELECT w.id FROM words w WHERE NOT EXISTS "
               "(SELECT 1 FROM progress p WHERE p.word_id=w.id) ")
        args = []
        if tiers:
            sql += " AND w.tier IN (%s)" % ",".join("?" * len(tiers))
            args += tiers
        if s.get("skip_basic"):
            sql += " AND w.basic = 0"
        order = request.args.get("order", "freq")
        sql += " ORDER BY " + ("w.freq DESC" if order == "freq" else "w.rank ASC, w.freq DESC")
        sql += " LIMIT ?"
        args.append(need)
        # 不预先建进度行：用户中途离开时这些词仍是「未学」，
        # 下次还能被推送出来，不会变成孤儿卡片。
        for r in db().execute(sql, args):
            if r["id"] in seen:
                continue
            cards.append({"word_id": r["id"], "round": 1, "state": "new",
                          "interval": 0.0, "ease": 2.5, "reps": 0, "due": None})

    words = fetch_words([c["word_id"] for c in cards])
    out = []
    for c in cards:
        w = words.get(c["word_id"])
        if not w:
            continue
        card = row_to_card(w, c)
        card["note_text"], card["starred"] = note_of(w["id"])
        card["total_rounds"] = rounds
        # 助记随卡片一起下发，学习时无需再发一次请求
        fam, similar = family_and_similar(w)
        card["mnemonic"] = mn.split_mnemonic(w["word"], w["meaning"], w["collocation"],
                                             w["category"], fam, similar)
        card["family"] = fam
        out.append(card)

    return jsonify({"cards": out, "mode": mode, "rounds": rounds, "graduation": gl,
                    "server_time": srs.iso(srs.now())})


@app.post("/api/answer")
def api_answer():
    data = request.get_json(force=True) or {}
    word_id = int(data["word_id"])
    rnd = int(data.get("round") or 1)
    rating = data.get("rating", "good")
    ms = int(data.get("ms") or 0)

    p = ensure_round(word_id, rnd)
    res = srs.schedule(p["ease"], p["interval"], p["reps"], rating, rnd)

    gl = graduation_list()
    grad = gl[rnd - 1] if rnd <= len(gl) else gl[-1]
    state = "graduated" if (not res["lapsed"] and res["interval"] >= grad) else (
        "new" if res["lapsed"] and p["reps"] == 0 else "review")

    db().execute(
        """UPDATE progress SET state=?, ease=?, interval=?, due=?, reps=?,
               correct=correct+?, wrong=wrong+?, lapses=lapses+?,
               last_rating=?, last_review=?, total_ms=total_ms+?
           WHERE word_id=? AND round=?""",
        (state, res["ease"], res["interval"], res["due"], res["reps"],
         1 if rating != "again" else 0, 1 if rating == "again" else 0,
         1 if res["lapsed"] else 0, rating, srs.iso(srs.now()), ms,
         word_id, rnd))
    db().execute(
        "INSERT INTO review_log(word_id,round,rating,prev_interval,new_interval,ease,ms,created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (word_id, rnd, rating, p["interval"], res["interval"], res["ease"], ms,
         srs.iso(srs.now())))
    db().commit()

    # 毕业 -> 立刻解锁下一轮
    unlocked = None
    total_rounds = int(get_settings().get("rounds", 3))
    if state == "graduated" and rnd < total_rounds:
        nxt = db().execute("SELECT * FROM progress WHERE word_id=? AND round=?",
                           (word_id, rnd + 1)).fetchone()
        if not nxt:
            db().execute("INSERT INTO progress(word_id,round,state,due) VALUES (?,?,'new',?)",
                         (word_id, rnd + 1, srs.iso(srs.now())))
            db().commit()
            unlocked = rnd + 1

    is_fresh = (p["state"] == "new" and p["reps"] == 0)
    bump_daily(**({"new_count": 1} if is_fresh else {"review_count": 1}),
               ms=ms, **({"correct": 1} if rating != "again" else {"wrong": 1}))

    return jsonify({"ok": True, "state": state, "due": res["due"],
                    "interval": res["interval"], "ease": res["ease"],
                    "reps": res["reps"], "lapsed": res["lapsed"],
                    "graduated": state == "graduated", "unlocked_round": unlocked})


@app.get("/api/word/<int:wid>")
def api_word(wid):
    w = db().execute("SELECT * FROM words WHERE id=?", (wid,)).fetchone()
    if not w:
        return jsonify({"error": "not found"}), 404
    w = dict(w)
    raw = w.pop("pos_json", None)
    try:
        w["pos"] = json.loads(raw) if raw else []
    except Exception:
        w["pos"] = []
    raw_ex = w.pop("examples", None)
    try:
        w["examples"] = json.loads(raw_ex) if raw_ex else []
    except Exception:
        w["examples"] = []

    fam, similar = family_and_similar(w)
    mem = mn.split_mnemonic(w["word"], w["meaning"], w["collocation"],
                            w["category"], fam, similar)
    note_text, starred = note_of(wid)
    rounds_total = int(get_settings().get("rounds", 3))
    rounds_map = {r["round"]: dict(r) for r in
                  db().execute("SELECT * FROM progress WHERE word_id=?", (wid,))}
    return jsonify({"word": w, "family": fam, "similar": similar,
                    "mnemonic": mem, "note": note_text, "starred": bool(starred),
                    "progress": [rounds_map.get(r) for r in range(1, rounds_total + 1)],
                    "score": _score(rounds_map)})


def family_and_similar(w):
    """取同根词族与形近词。形近词先用「首字母相同 + 长度接近」粗筛，
    再做编辑距离精筛，避免每张卡都全表扫描。"""
    fam = [r["word"] for r in db().execute(
        "SELECT word FROM words WHERE base=? AND word != ? ORDER BY freq DESC LIMIT 10",
        (w["base"], w["word"]))]
    tw = w["word"].lower()
    if not tw:
        return fam, []
    similar = []
    for r in db().execute(
            "SELECT word FROM words WHERE LOWER(SUBSTR(word,1,1)) = ? "
            "AND ABS(LENGTH(word) - ?) <= 2 AND word != ?",
            (tw[0], len(tw), w["word"])):
        o = r["word"].lower()
        if _lev(tw, o) <= 2:
            similar.append(r["word"])
            if len(similar) >= 8:
                break
    return fam, similar


def _lev(a, b):
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if abs(la - lb) > 2:
        return 99
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1,
                         prev[j - 1] + (a[i - 1] != b[j - 1]))
        prev = cur
    return prev[lb]


def _score(rounds_map):
    """0-100 的记忆强度：每轮按当前保留率加权。"""
    if not rounds_map:
        return 0
    tot = 0.0
    for r, st in rounds_map.items():
        if st["state"] == "graduated":
            tot += 100.0 / max(1, r)
        elif st["state"] in ("learning", "review"):
            try:
                last = datetime.datetime.fromisoformat(st["last_review"])
                elapsed = (srs.now() - last).total_seconds() / 86400.0
            except Exception:
                elapsed = 0
            tot += srs.retrievability(elapsed, st["interval"]) * 100.0 / max(1, r)
    return round(min(100.0, tot), 1)


@app.post("/api/note")
def api_note():
    d = request.get_json(force=True) or {}
    wid = int(d["word_id"])
    cur = db().execute("SELECT text,starred FROM notes WHERE word_id=?", (wid,)).fetchone()
    text = d["text"] if "text" in d else (cur["text"] if cur else "")
    starred = (1 if d["starred"] else 0) if "starred" in d else (cur["starred"] if cur else 0)
    db().execute(
        "INSERT INTO notes(word_id,text,starred,updated_at) VALUES (?,?,?,?) "
        "ON CONFLICT(word_id) DO UPDATE SET text=excluded.text, "
        "starred=excluded.starred, updated_at=excluded.updated_at",
        (wid, text or "", starred or 0, srs.iso(srs.now())))
    db().commit()
    return jsonify({"ok": True})


@app.get("/api/dashboard")
def api_dashboard():
    s = get_settings()
    rounds = int(s.get("rounds", 3))
    gl = graduation_list(s)
    total = db().execute("SELECT COUNT(*) c FROM words").fetchone()["c"]
    learned = db().execute("SELECT COUNT(DISTINCT word_id) c FROM progress").fetchone()["c"]
    grad_all = db().execute(
        "SELECT COUNT(*) c FROM progress WHERE round=? AND state='graduated'",
        (rounds,)).fetchone()["c"]

    # 各轮次分布
    rnd_dist = [dict(r) for r in db().execute(
        "SELECT round, state, COUNT(*) c FROM progress GROUP BY round, state")]

    # 各梯队进度
    tiers = [dict(r) for r in db().execute(
        """SELECT w.tier,
                  COUNT(*) total,
                  SUM(CASE WHEN EXISTS(SELECT 1 FROM progress p WHERE p.word_id=w.id) THEN 1 ELSE 0 END) started,
                  SUM(CASE WHEN EXISTS(SELECT 1 FROM progress p WHERE p.word_id=w.id AND p.round=? AND p.state='graduated') THEN 1 ELSE 0 END) done
           FROM words w GROUP BY w.tier ORDER BY total DESC""", (rounds,))]

    # 近 90 天热力图 + 连续打卡
    days = []
    for r in db().execute("SELECT * FROM daily ORDER BY date"):
        days.append(dict(r))
    streak = 0
    d = datetime.date.today()
    have = {x["date"]: x for x in days}
    while True:
        x = have.get(d.isoformat())
        if x and (x["new_count"] + x["review_count"]) > 0:
            streak += 1
            d -= datetime.timedelta(days=1)
        else:
            break

    # 未来 30 天到期预测
    forecast = []
    for i in range(30):
        day = (datetime.date.today() + datetime.timedelta(days=i))
        lo = srs.iso(datetime.datetime.combine(day, datetime.time.min))
        hi = srs.iso(datetime.datetime.combine(day, datetime.time.max))
        c = db().execute("SELECT COUNT(*) c FROM progress WHERE due >= ? AND due <= ? "
                         "AND state != 'new'", (lo, hi)).fetchone()["c"]
        forecast.append({"date": day.isoformat(), "due": c})

    # 最难的词
    hard = [dict(r) for r in db().execute(
        """SELECT w.id, w.word, w.meaning, SUM(p.lapses) lapses, SUM(p.wrong) wrong
           FROM progress p JOIN words w ON w.id=p.word_id
           GROUP BY p.word_id HAVING lapses > 0
           ORDER BY lapses DESC, wrong DESC LIMIT 15""")]

    # 遗忘曲线样本
    curve = []
    for rnd in range(1, rounds + 1):
        row = db().execute("SELECT AVG(interval) a FROM progress WHERE round=? AND interval>0",
                           (rnd,)).fetchone()
        S = row["a"] or 1.0
        pts = [{"t": t / 10.0, "r": round(srs.retrievability(t / 10.0, S), 4)}
               for t in range(0, 211, 2)]
        curve.append({"round": rnd, "stability": round(S, 2), "points": pts})

    # 近 14 天正确率
    acc = [dict(r) for r in db().execute(
        "SELECT date, correct, wrong, new_count, review_count, ms FROM daily "
        "ORDER BY date DESC LIMIT 14")][::-1]

    return jsonify({"totals": {"total": total, "learned": learned, "graduated": grad_all},
                    "rounds": rounds, "graduation": gl, "round_dist": rnd_dist,
                    "tiers": tiers, "days": days, "streak": streak,
                    "forecast": forecast, "hard": hard, "curve": curve, "accuracy": acc})


@app.get("/api/browse")
def api_browse():
    q = (request.args.get("q") or "").strip()
    tier = request.args.get("tier") or ""
    status = request.args.get("status") or ""
    page = max(1, int(request.args.get("page") or 1))
    size = min(200, int(request.args.get("size") or 50))
    rounds = int(get_settings().get("rounds", 3))

    # 显式列出字段：pos_json 体积大，列表页用不到，不要跟着返回
    sql = ("SELECT w.id,w.rank,w.word,w.freq,w.tier,w.meaning,w.category,"
           "w.subcategory,w.collocation,w.alt,w.remark,w.phonetic_us,w.phonetic_uk,"
           "w.root,w.base,w.basic,w.pos_primary, "
           "(SELECT state FROM progress p WHERE p.word_id=w.id AND p.round=1) r1, "
           "(SELECT state FROM progress p WHERE p.word_id=w.id AND p.round=?) rn, "
           "(SELECT text FROM notes n WHERE n.word_id=w.id) note_text, "
           "(SELECT starred FROM notes n WHERE n.word_id=w.id) starred "
           "FROM words w WHERE 1=1")
    args = [rounds]
    if q:
        sql += (" AND (w.word LIKE ? OR w.meaning LIKE ? OR w.collocation LIKE ?"
                " OR w.pos_json LIKE ?)")
        args += ["%" + q + "%"] * 4
    if tier:
        sql += " AND w.tier = ?"
        args.append(tier)
    if status == "new":
        sql += " AND r1 IS NULL"
    elif status == "learning":
        sql += " AND r1 IS NOT NULL AND (rn IS NULL OR rn != 'graduated')"
    elif status == "done":
        sql += " AND rn = 'graduated'"
    elif status == "starred":
        sql += " AND starred = 1"

    cnt = db().execute("SELECT COUNT(*) c FROM (" + sql + ")", args).fetchone()["c"]
    # 基础功能词沉底，内容词优先；其余按词频排名
    sql += (" ORDER BY w.basic ASC, w.rank IS NULL, w.rank ASC, w.freq DESC"
            " LIMIT ? OFFSET ?")
    rows = [dict(r) for r in db().execute(sql, args + [size, (page - 1) * size])]
    return jsonify({"rows": rows, "total": cnt, "page": page, "size": size,
                    "pages": max(1, -(-cnt // size))})


@app.post("/api/enrich/<int:wid>")
def api_enrich(wid):
    """按需拉取英式音标 + 真人发音（dictionaryapi.dev，永久缓存）。"""
    w = db().execute("SELECT * FROM words WHERE id=?", (wid,)).fetchone()
    if not w:
        return jsonify({"error": "not found"}), 404
    if w["enriched"] and (w["audio_us"] or w["audio_uk"]):
        return jsonify({"ok": True, "cached": True, "word": dict(w)})

    word = w["word"].split()[0].strip()
    url = "https://api.dictionaryapi.dev/api/v2/entries/en/" + urllib.parse.quote(word)
    uk = us = au = auk = ex = None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "vocab-app/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for entry in data if isinstance(data, list) else []:
            for ph in entry.get("phonetics", []) or []:
                t = (ph.get("text") or "").strip()
                a = ph.get("audio") or ""
                if t.startswith("/") or t.startswith("["):
                    if "-uk." in a or "-gb." in a:
                        uk = uk or t
                    elif "-us." in a:
                        us = us or t
                    else:
                        us = us or t
                if a:
                    if "-uk." in a or "-gb." in a:
                        auk = auk or a
                    elif "-us." in a:
                        au = au or a
                    else:
                        au = au or a
            for m in entry.get("meanings", []) or []:
                for df in m.get("definitions", []) or []:
                    if not ex and df.get("example"):
                        ex = df["example"]
        if not us:
            for entry in data if isinstance(data, list) else []:
                if entry.get("phonetic"):
                    us = entry["phonetic"]
                    break
    except Exception as e:
        db().execute("UPDATE words SET enriched=1 WHERE id=?", (wid,))
        db().commit()
        return jsonify({"ok": False, "error": str(e), "word": dict(w)})

    db().execute("""UPDATE words SET phonetic_uk=COALESCE(?,phonetic_uk),
                        phonetic_us=COALESCE(?,phonetic_us),
                        audio_us=COALESCE(?,audio_us), audio_uk=COALESCE(?,audio_uk),
                        example_en=COALESCE(?,example_en), enriched=1 WHERE id=?""",
                 (uk, us, au, auk, ex, wid))
    db().commit()
    w = db().execute("SELECT * FROM words WHERE id=?", (wid,)).fetchone()
    return jsonify({"ok": True, "cached": False, "word": dict(w)})


@app.get("/api/settings")
def api_get_settings():
    return jsonify(get_settings())


@app.post("/api/settings")
def api_post_settings():
    save_settings(request.get_json(force=True) or {})
    return jsonify(get_settings())


@app.get("/api/export")
def api_export():
    out = {"exported_at": srs.iso(srs.now()), "settings": get_settings(),
           "progress": [], "notes": [], "daily": []}
    for r in db().execute("SELECT w.word, p.* FROM progress p JOIN words w ON w.id=p.word_id"):
        out["progress"].append(dict(r))
    for r in db().execute("SELECT w.word, n.text, n.starred FROM notes n JOIN words w ON w.id=n.word_id"):
        out["notes"].append(dict(r))
    for r in db().execute("SELECT * FROM daily"):
        out["daily"].append(dict(r))
    return jsonify(out)


@app.post("/api/reset")
def api_reset():
    d = request.get_json(force=True) or {}
    what = d.get("what", "progress")
    if what in ("progress", "all"):
        db().execute("DELETE FROM progress")
        db().execute("DELETE FROM review_log")
        db().execute("DELETE FROM daily")
    if what == "all":
        db().execute("DELETE FROM notes")
    db().commit()
    return jsonify({"ok": True})


@app.get("/api/health")
def api_health():
    return jsonify({"ok": True, "time": srs.iso(srs.now())})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5178))
    print("=" * 58)
    print("  考研单词背诵系统  http://127.0.0.1:%d" % port)
    print("  词库：%s" % DB_PATH)
    print("=" * 58)
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
