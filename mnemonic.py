# -*- coding: utf-8 -*-
"""词根词缀助记引擎。

为每个单词生成可读的「拆解式记忆」：前缀 + 词根 + 后缀，
再配合同根词族、形近词、真题搭配，组成一条完整的助记卡。
纯规则实现，不依赖任何外部 API。
"""
from __future__ import annotations

# ---------------------------------------------------------------- 前缀
PREFIXES = {
    "ab": "离开、脱离", "abs": "离开", "ad": "朝向、加强", "ac": "朝向、加强",
    "af": "朝向、加强", "ag": "朝向、加强", "al": "朝向、加强", "ap": "朝向、加强",
    "ar": "朝向、加强", "as": "朝向、加强", "at": "朝向、加强",
    "ante": "之前", "anti": "反对", "auto": "自己、自动", "be": "使、加强",
    "bene": "好", "bi": "二、双", "circum": "环绕", "co": "共同", "col": "共同",
    "com": "共同、加强", "con": "共同、加强", "cor": "共同、加强",
    "contra": "相反", "counter": "反对", "de": "向下、去除、加强", "dia": "穿过",
    "dis": "否定、分开", "dif": "否定、分开", "di": "分开、二", "dys": "不良",
    "e": "向外、出", "ef": "向外、出", "ex": "向外、出、前任", "ec": "向外",
    "en": "使…、进入", "em": "使…、进入", "epi": "在…之上", "equi": "相等",
    "eu": "好", "extra": "超出", "fore": "在前、预先", "geo": "地球",
    "hetero": "不同", "homo": "相同", "hyper": "过度、超", "hypo": "在…下、次",
    "il": "否定", "im": "否定、进入", "in": "否定、进入", "ir": "否定",
    "inter": "在…之间、相互", "intra": "在…内部", "intro": "向内",
    "macro": "大", "mal": "坏", "micro": "微小", "mid": "中间", "mini": "小",
    "mis": "错误、坏", "mono": "单一", "multi": "多", "neo": "新",
    "non": "非", "ob": "反对、朝向", "oc": "朝向", "of": "朝向", "op": "朝向",
    "omni": "全部", "out": "超过、向外", "over": "过度、在上",
    "pan": "全", "para": "旁边、类似", "per": "贯穿、彻底", "peri": "周围",
    "poly": "多", "post": "之后", "pre": "之前、预先", "pro": "向前、支持",
    "proto": "原始", "pseudo": "假的", "quadr": "四", "re": "再次、回、反",
    "retro": "向后", "se": "分开", "semi": "一半", "sub": "在下、次",
    "suc": "在下", "suf": "在下", "sup": "在下", "sur": "在上、超",
    "super": "超、上", "sus": "在下", "syn": "共同", "sym": "共同",
    "tele": "远", "trans": "穿过、转变", "tri": "三", "ultra": "极端、超",
    "un": "否定、相反", "under": "在下、不足", "uni": "单一", "up": "向上",
    "vice": "副的", "with": "向后、离开",
}

# ---------------------------------------------------------------- 词根
ROOTS = {
    "act": "做、行动", "alter": "改变", "anim": "生命、精神", "ann": "年",
    "anthrop": "人类", "aqua": "水", "arm": "武器", "art": "技艺",
    "aud": "听", "band": "束缚、带子", "bar": "栏、阻挡", "bat": "打",
    "bio": "生命", "brev": "短", "cap": "拿、抓", "capt": "拿、抓",
    "carn": "肉", "cav": "洞", "cede": "走、让", "ceed": "走、让",
    "cess": "走、让", "cent": "百", "cept": "拿、取", "cern": "分辨",
    "cert": "确定", "chron": "时间", "cide": "切、杀", "cis": "切",
    "civ": "公民", "claim": "喊", "clam": "喊", "clar": "清楚",
    "clin": "倾斜", "clud": "关闭", "clus": "关闭", "cogn": "知道",
    "corp": "身体", "cosm": "宇宙", "crat": "统治", "cred": "相信",
    "cresc": "生长", "cur": "关心、跑", "cura": "关心", "dict": "说",
    "doc": "教", "domin": "主宰", "don": "给予", "dot": "给",
    "econom": "经济、家务", "soci": "社会、同伴", "techn": "技术", "polit": "政治、城市",
    "cult": "耕作、培养", "educ": "教育、引出", "medic": "医疗", "organ": "器官、工具",
    "commun": "共同", "histor": "历史", "univers": "宇宙、普遍", "legis": "法律",
    "nomin": "名字", "scient": "知道", "capit": "头、资本", "civil": "公民",
    "natur": "自然、出生", "signif": "表示", "defin": "限定", "consid": "考虑",
    "duc": "引导", "duct": "引导", "dur": "持久、硬", "equ": "相等",
    "fac": "做", "fact": "做", "fect": "做", "fer": "带来、拿",
    "fid": "信任", "fin": "结束、界限", "firm": "坚固", "flect": "弯曲",
    "flex": "弯曲", "flu": "流", "form": "形状", "fort": "强",
    "frag": "破碎", "fract": "破碎", "fund": "基础、底", "gen": "产生、种类",
    "geo": "地球", "grad": "走、步", "gress": "走", "graph": "写",
    "grat": "感谢、愉快", "grav": "重", "hab": "拥有、居住", "hosp": "客人",
    "her": "粘附、继承", "ject": "投掷", "jud": "判断", "junct": "连接",
    "jur": "法律、发誓", "labor": "劳动", "lect": "选择、读", "leg": "读、法律",
    "lev": "举起、轻", "liber": "自由", "lingu": "语言", "liter": "文字",
    "loc": "地方", "log": "说、学科", "loqu": "说", "luc": "光",
    "lumin": "光", "magn": "大", "man": "手", "mand": "命令",
    "mar": "海", "matr": "母", "med": "中间", "medi": "中间",
    "memor": "记忆", "ment": "思想", "merg": "沉、浸", "mers": "沉、浸",
    "meter": "测量", "metr": "测量", "migr": "迁移", "min": "小、突出",
    "mit": "送、发", "miss": "送、发", "mob": "移动", "mot": "移动",
    "mov": "移动", "mut": "改变", "nat": "出生", "nav": "船",
    "nom": "名字、法则", "nov": "新", "numer": "数字", "oper": "工作",
    "opt": "选择、看", "ora": "说、嘴", "ord": "顺序", "pac": "和平",
    "par": "准备、显现", "part": "部分", "pass": "通过、感情", "pat": "忍受、父亲",
    "path": "感情、疾病", "ped": "脚", "pel": "推", "puls": "推、跳",
    "pend": "悬挂、称量", "pens": "称量、花费", "pet": "追求", "plac": "使高兴",
    "ple": "填满", "plen": "满", "plic": "折叠", "ply": "折叠",
    "pon": "放置", "pos": "放置", "port": "搬运、港口", "pot": "能力",
    "prehend": "抓住", "press": "压", "prim": "第一", "prin": "第一",
    "priv": "私人", "prob": "证明、试验", "propr": "自己的", "prot": "第一",
    "psych": "心理", "punct": "点", "put": "思考、计算", "quir": "寻求",
    "quis": "寻求", "quest": "寻求", "radi": "光线", "reg": "统治、规则",
    "rect": "直、正", "rid": "笑", "rog": "问", "rupt": "破",
    "sacr": "神圣", "sci": "知道", "scop": "看", "scrib": "写",
    "script": "写", "sec": "跟随、切", "sect": "切", "sembl": "相似",
    "sent": "感觉", "sens": "感觉", "sequ": "跟随", "serv": "服务、保持",
    "sid": "坐", "sess": "坐", "sign": "记号", "simil": "相似",
    "sist": "站立", "sta": "站立", "stat": "站立", "stitut": "建立",
    "sol": "太阳、单独", "somn": "睡", "son": "声音", "soph": "智慧",
    "spec": "看", "spic": "看", "spir": "呼吸", "sta": "站立",
    "struct": "建造", "sum": "拿、总", "sumpt": "拿", "tact": "接触",
    "tang": "接触", "tect": "覆盖", "tele": "远", "temp": "时间",
    "tend": "伸展", "tens": "伸展", "tent": "伸展", "term": "界限、结束",
    "terr": "土地", "test": "证明", "text": "编织", "theo": "神",
    "therm": "热", "tort": "扭曲", "tour": "转", "tract": "拉、拖",
    "trib": "给予、部落", "trud": "推", "trus": "推", "turb": "搅动",
    "umbr": "阴影", "uni": "一", "urb": "城市", "vac": "空",
    "vad": "走", "vas": "走", "val": "价值、强", "ven": "来",
    "vent": "来", "ver": "真实", "verb": "词", "vert": "转",
    "vers": "转", "vest": "衣服", "vi": "路", "vid": "看",
    "vis": "看", "viv": "生命", "voc": "叫、声音", "vok": "叫",
    "vol": "意愿、飞", "volv": "滚、转", "vor": "吃", "zo": "动物",
}

# ---------------------------------------------------------------- 后缀
SUFFIXES = {
    "ability": "n. 能力、性质", "able": "adj. 能…的", "ible": "adj. 能…的",
    "ably": "adv. 能…地", "acy": "n. 状态、性质", "age": "n. 行为、状态",
    "al": "adj. …的 / n. 行为", "ality": "n. 性质", "ally": "adv. …地",
    "an": "adj./n. …的人", "ance": "n. 状态、行为", "ancy": "n. 状态",
    "ant": "n. …的人 / adj. …的", "ar": "adj. …的", "ary": "adj./n. …的、场所",
    "ate": "v. 使… / adj. …的", "ation": "n. 行为、结果", "ative": "adj. 有…倾向的",
    "cy": "n. 状态", "dom": "n. 领域、状态", "ee": "n. 被…的人",
    "eer": "n. 从事…的人", "en": "v. 使… / adj. …的", "ence": "n. 状态、性质",
    "ency": "n. 状态", "ent": "adj. …的 / n. …者", "er": "n. …的人、物",
    "ery": "n. 行为、场所", "ese": "adj./n. …的、…人", "esque": "adj. …风格的",
    "ess": "n. 女性", "ful": "adj. 充满…的", "hood": "n. 身份、状态",
    "ial": "adj. …的", "ian": "n./adj. …的人、…的", "ic": "adj. …的",
    "ical": "adj. …的", "ics": "n. …学", "ify": "v. 使…化",
    "ile": "adj. 易…的", "ine": "adj. …的", "ing": "n./adj. 进行、…的",
    "ion": "n. 行为、状态", "ious": "adj. 充满…的", "ise": "v. 使…化",
    "ish": "adj. 略…的", "ism": "n. 主义、学说", "ist": "n. …者、…家",
    "ite": "n./adj. …人、…的", "ity": "n. 性质、状态", "ive": "adj. 有…性质的",
    "ize": "v. 使…化", "less": "adj. 无…的", "let": "n. 小…",
    "like": "adj. 像…的", "ly": "adv./adj. …地、…的", "ment": "n. 行为、结果",
    "most": "adj. 最…的", "ness": "n. 性质、状态", "ology": "n. …学",
    "or": "n. …者、…物", "ory": "adj./n. …的、场所", "ous": "adj. 充满…的",
    "ship": "n. 身份、关系", "sion": "n. 行为、状态", "some": "adj. 有…倾向的",
    "tion": "n. 行为、状态", "tious": "adj. 充满…的", "ty": "n. 性质",
    "ure": "n. 行为、结果", "ward": "adv. 朝…方向", "ware": "n. 制品",
    "wise": "adv. 在…方面", "y": "adj./n. …的、性质",
}

_VOWELS = set("aeiou")


def _strip_suffix(word: str):
    """尝试切掉后缀，返回 (词干, 后缀, 后缀释义) 或 (word, None, None)。"""
    for suf in sorted(SUFFIXES, key=len, reverse=True):
        if len(word) - len(suf) < 3:
            continue
        if word.endswith(suf):
            stem = word[: -len(suf)]
            # 处理「双写辅音」：running -> run, stopping -> stop
            # 只在去重后确实是已知词根时才还原；另外 ss 结尾几乎都是词本身
            # （pass / class / press / miss），一律不去重。
            if (len(stem) > 3 and stem[-1] == stem[-2]
                    and stem[-1] not in _VOWELS and stem[-1] != "s"
                    and suf[0] in _VOWELS):
                undoubled = stem[:-1]
                if undoubled in ROOTS or any(
                        undoubled.startswith(r) for r in ROOTS if len(r) >= 3):
                    return undoubled, suf, SUFFIXES[suf]
            return stem, suf, SUFFIXES[suf]
    return word, None, None


def _match_prefix(word: str):
    """最长前缀匹配，且剩余部分至少 2 个字母。"""
    for p in sorted(PREFIXES, key=len, reverse=True):
        if word.startswith(p) and len(word) - len(p) >= 2:
            return p, PREFIXES[p]
    return None, None


def _match_root0(word: str):
    """词根必须**从词首开始**（前缀剥离之后），否则很容易误判。

    例如 people 里能"找到" ple(填满)，但那只是巧合；要求从首字母匹配后，
    passage -> pass(通过)、inspect -> spect(看) 这类正确拆解不受影响。
    """
    best = None
    for r in sorted(ROOTS, key=len, reverse=True):
        if len(r) >= 3 and word.startswith(r):
            best = (r, 0)
            break
    return best


def _suffix_splits(rest: str):
    """列出所有可能的 (词干, 后缀) 切分，长后缀优先。"""
    out = []
    for suf in sorted(SUFFIXES, key=len, reverse=True):
        if len(suf) < 2 or len(rest) - len(suf) < 3 or not rest.endswith(suf):
            continue
        stem = rest[: -len(suf)]
        # 双写还原：running -> run（ss 结尾的一律不动，pass/class/press 是词本身）
        if (len(stem) > 3 and stem[-1] == stem[-2] and stem[-1] not in _VOWELS
                and stem[-1] != "s" and suf[0] in _VOWELS and stem[:-1] in ROOTS):
            stem = stem[:-1]
        out.append((stem, suf))
    return out


def analyze(word: str) -> dict:
    """把单词拆成 前缀 + 词根 + 后缀。

    切分策略：在所有可能的 (词干, 后缀) 里，优先选「切完后词首能命中已知词根」
    的那一种。这样 question 会走 quest(寻求)+ion，而不是 ques+tion。
    """
    w = word.lower().strip()
    parts = []
    rest = w

    pre, pre_gloss = _match_prefix(rest)
    if pre and len(pre) >= 2:
        rest = rest[len(pre):]

    # 分别试「保留前缀」和「丢掉前缀」两种拆法，谁拆出的词根更长就用谁。
    # 这样 biology 走 bio(生命)+logy 而不是 bi-(双)+ology，
    # dictionary 走 dict(说)+ion+ary 而不是 di-(二)+ction+ary。
    def parse_without_prefix(text):
        splits = _suffix_splits(text)
        for s, f in splits:
            if _match_root0(s):
                return s, f
        return (splits[0] if splits else (text, None))

    stem_b, suf_b = parse_without_prefix(w)
    root_b = _match_root0(stem_b)
    score_b = (len(root_b[0]) * 2 if root_b else 0) + (1 if suf_b else 0)

    if pre and len(pre) >= 2:
        stem_a, suf_a = parse_without_prefix(rest)
        root_a = _match_root0(stem_a)
        score_a = (len(root_a[0]) * 2 if root_a else 0) + (1 if suf_a else 0) + 1
        if score_a > score_b:
            stem, suf, root_hit = stem_a, suf_a, root_a
            parts = [{"text": pre + "-", "type": "prefix", "gloss": pre_gloss}]
        else:
            stem, suf, root_hit = stem_b, suf_b, root_b
            parts = []
            pre, pre_gloss = None, None
    else:
        stem, suf, root_hit = stem_b, suf_b, root_b
        pre, pre_gloss = None, None
        parts = []
    if root_hit:
        r, _ = root_hit
        parts.append({"text": r, "type": "root", "gloss": ROOTS[r]})
        if len(stem) > len(r):
            parts.append({"text": stem[len(r):], "type": "stem", "gloss": ""})
    elif stem and (pre or suf):
        parts.append({"text": stem, "type": "stem", "gloss": ""})

    if suf:
        parts.append({"text": "-" + suf, "type": "suffix", "gloss": SUFFIXES[suf]})

    # 没有任何一段带释义（既无词根也无词缀）时不显示拆解，免得写出 "well" 这种废话
    if not any(p["gloss"] for p in parts):
        parts = []
    has_root = any(p["type"] == "root" for p in parts)
    return {"parts": parts, "root": root_hit[0] if root_hit and parts else None,
            "confidence": "high" if has_root else ("medium" if parts else "low")}


def base_form(word: str) -> str:
    """取词干，用于把同根词归到一起。

    只剥离一层后缀（且后缀至少 2 个字母、词干至少 4 个字母），
    避免 assessment -> assess -> ass 这类过度剥离。
    """
    w = word.lower().strip()
    w = w.replace("-", "").replace(" ", "").replace("'", "")
    if len(w) < 6:
        return w
    pre, _ = _match_prefix(w)
    if pre and len(pre) >= 3 and len(w) - len(pre) >= 4:
        w = w[len(pre):]
    for suf in sorted(SUFFIXES, key=len, reverse=True):
        if len(suf) >= 2 and w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w


def split_mnemonic(word: str, meaning: str, collocation: str = "",
                   category: str = "", family=None, similar=None) -> dict:
    """生成助记卡：拆解 + 同根词 + 形近词 + 语境提示。"""
    a = analyze(word)
    pieces = []
    for p in a["parts"]:
        pieces.append(p["text"] + ("(" + p["gloss"] + ")" if p["gloss"] else ""))
    breakdown = " + ".join(pieces) if a["parts"] else ""

    tips = []
    if breakdown:
        chain = " → ".join(x for x in [p.get("gloss", "") for p in a["parts"] if p.get("gloss")])
        if chain:
            tips.append("构词：" + breakdown + "，字面义「" + chain + "」，引申为「" + meaning + "」")
        else:
            tips.append("构词：" + breakdown)

    if category:
        tips.append("语境：" + category + "类词汇，真题多出现在该主题的阅读/翻译中")
    if collocation:
        tips.append("真题搭配：" + collocation)
    if family:
        tips.append("同根词族：" + "、".join(family[:8]))
    if similar:
        tips.append("形近词辨析：" + "、".join(similar[:6]) + "（注意区分首尾字母）")

    return {"breakdown": breakdown, "root": a["root"], "confidence": a["confidence"],
            "tips": tips}
