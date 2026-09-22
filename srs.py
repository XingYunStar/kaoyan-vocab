# -*- coding: utf-8 -*-
"""间隔重复调度：复合遗忘曲线。

设计要点
--------
1. 每个单词要过 N 轮（默认 3 轮），**上一轮毕业才解锁下一轮**。
   轮 1 识记（看词认义）→ 轮 2 回忆（看义拼词）→ 轮 3 运用（搭配填空）。
2. 每一轮内部用 SM-2 变体调度：ease 因子 + 间隔阶梯 + 遗忘曲线。
3. 遗忘曲线用指数模型 R(t) = exp(-t / S)，S 即该词当前的间隔天数。
   复习时机 = R 掉到保留率阈值以下的时间点。
4. 同一单词的每一轮各自独立调度，互不干扰。
"""
from __future__ import annotations

import datetime

RATING_Q = {"again": 2, "hard": 3, "good": 4, "easy": 5}
RATINGS = ("again", "hard", "good", "easy")

# 轮次难度修正：轮次越高（回忆/运用比识记难），同样评级下间隔收紧
ROUND_FACTOR = {1: 1.0, 2: 0.85, 3: 0.7, 4: 0.6}

MIN_EASE, MAX_EASE = 1.3, 3.2
MAX_INTERVAL = 365.0
RELEARN_MINUTES = 10        # 忘了 -> 10 分钟后在本次会话里重来
TARGET_RETENTION = 0.9      # 目标保留率，用于文档与曲线标注


def now():
    return datetime.datetime.now()


def iso(dt):
    return dt.replace(microsecond=0).isoformat(sep=" ")


def schedule(ease, interval, reps, rating, round_no):
    """算出下一次复习时间。

    参数
      ease     当前 ease 因子
      interval 当前间隔（天），也是遗忘曲线的稳定性 S
      reps     已连续答对次数
      rating   again / hard / good / easy
      round_no 第几轮（1 起）
    返回 dict(ease, interval, reps, due, lapsed)
    """
    if rating not in RATING_Q:
        rating = "good"
    q = RATING_Q[rating]
    new_ease = ease + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    new_ease = max(MIN_EASE, min(MAX_EASE, new_ease))
    factor = ROUND_FACTOR.get(int(round_no), 0.7)

    if rating == "again":
        # 没想起来：ease 下调、连续计数清零、本次会话内重来
        due = now() + datetime.timedelta(minutes=RELEARN_MINUTES)
        return {"ease": round(new_ease, 3), "interval": 0.0, "reps": 0,
                "due": iso(due), "lapsed": True}

    r = reps + 1
    if r == 1:
        iv = {"hard": 0.5, "good": 1.0, "easy": 2.0}[rating]
    elif r == 2:
        iv = {"hard": 2.0, "good": 3.0, "easy": 5.0}[rating]
    else:
        iv = interval * new_ease
        if rating == "hard":
            iv *= 0.7
        elif rating == "easy":
            iv *= 1.3

    iv *= factor
    iv = max(0.5, min(iv, MAX_INTERVAL))
    due = now() + datetime.timedelta(days=iv)
    return {"ease": round(new_ease, 3), "interval": round(iv, 3), "reps": r,
            "due": iso(due), "lapsed": False}


def retrievability(elapsed_days, stability):
    """遗忘曲线 R(t) = exp(-t/S)。stability<=0 视为刚学，返回 0。"""
    import math
    if not stability or stability <= 0:
        return 0.0
    if elapsed_days <= 0:
        return 1.0
    return math.exp(-elapsed_days / stability)


def stability_for(interval, retention=TARGET_RETENTION):
    """反过来：想让复习时保留率恰好是 retention，稳定性该是多少。"""
    import math
    if retention <= 0 or retention >= 1:
        return interval
    return interval / (-math.log(retention))


def days_left(exam_date, today=None):
    today = today or datetime.date.today()
    try:
        y, m, d = (int(x) for x in str(exam_date).split("-"))
        exam = datetime.date(y, m, d)
    except Exception:
        return 0
    return (exam - today).days


def daily_plan(total, learned, due_today, days, rounds, rounds_pending):
    """倒计时驱动的每日计划。

    total          选中的总词数
    learned        已开始学的词数（轮 1 已有进度）
    due_today      今天到期的复习量
    days           距考试天数
    rounds         每词轮数
    rounds_pending 还没毕业的轮次总数（所有词的剩余轮数之和）
    返回每日需要的新词数与总负荷。
    """
    days = max(1, int(days))
    remaining_new = max(0, total - learned)
    new_per_day = -(-remaining_new // days)          # 向上取整
    # 剩余轮次也要塞进剩余天数
    rounds_per_day = -(-max(0, rounds_pending) // days)
    return {
        "days_left": days,
        "remaining_new": remaining_new,
        "new_per_day": new_per_day,
        "rounds_pending": rounds_pending,
        "rounds_per_day": rounds_per_day,
        "due_today": due_today,
        "daily_load": new_per_day + due_today,
        "eta_days": -(-remaining_new // max(1, new_per_day)) if new_per_day else 0,
    }
