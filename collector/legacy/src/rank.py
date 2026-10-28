"""排序层：去重 -> 噪音过滤 -> 热度打分 -> 事件聚类。"""
from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime, timezone

STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "be", "been",
    "to", "of", "in", "on", "at", "for", "with", "by", "from", "as", "that", "this",
    "it", "its", "we", "you", "they", "he", "she", "i", "will", "has", "have", "had",
    "not", "no", "so", "if", "than", "then", "there", "their", "what", "which", "who",
    "all", "more", "most", "up", "down", "out", "about", "after", "over", "just",
    "now", "new", "one", "two", "can", "could", "would", "should", "may", "via",
    "amp", "rt", "https", "http", "com", "www",
}

_URL_RE = re.compile(r"https?://\S+")
_MENTION_RE = re.compile(r"[@#](\w+)")
_NONWORD_RE = re.compile(r"[^a-z0-9$ ]+")


def _compile(patterns: list[str]) -> list[re.Pattern]:
    out = []
    for p in patterns:
        try:
            out.append(re.compile(p, re.I))
        except re.error as e:
            print(f"  ! 跳过无效正则 {p!r}: {e}")
    return out


def clean_text(text: str) -> str:
    """去掉链接，保留 @/# 后面的词。

    先做 NFKC 规范化：推特上常见的花体字（𝗝𝗨𝗦𝗧 𝗜𝗡、𝐆𝐨𝐥𝐝𝐞𝐧）是数学字母符号，
    不规范化的话既判不出语种也切不出词。
    """
    t = unicodedata.normalize("NFKC", text or "")
    t = _URL_RE.sub(" ", t)
    return _MENTION_RE.sub(r"\1", t).strip()


def _latin_ratio(text: str) -> float:
    """拉丁字母占所有字母的比例，用来剔除日文/中文/俄文等非拉丁文字。"""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 1.0
    return sum(1 for c in letters if c.isascii()) / len(letters)


# 各语种高频功能词。拉丁占比只能判文字系统，判不出法语/西语/印尼语——
# 它们同样是拉丁字母，占比接近 1.0。功能词才能区分语种。
_LANG_MARKERS = {
    "en": {
        "the", "of", "to", "and", "in", "is", "that", "for", "with", "on", "as",
        "at", "by", "from", "this", "it", "are", "be", "has", "will", "was",
        "not", "have", "but", "they", "we", "you", "its", "their", "what",
    },
    "id": {
        "yang", "dan", "di", "ini", "itu", "untuk", "dengan", "dari", "ke",
        "pada", "tidak", "akan", "sudah", "bisa", "ada", "juga", "karena",
        "atau", "dalam", "saya", "kita", "para", "lebih", "masih", "adalah",
    },
    "es": {"que", "de", "la", "el", "en", "los", "las", "por", "para", "con",
           "una", "del", "se", "es", "su", "al", "como", "más", "pero"},
    "fr": {"le", "la", "les", "de", "des", "du", "et", "un", "une", "est",
           "pour", "dans", "sur", "avec", "que", "qui", "pas", "plus", "ce"},
    "pt": {"que", "de", "da", "do", "em", "para", "com", "uma", "os", "as",
           "não", "por", "mais", "como", "está", "são", "pelo"},
    "pl": {"nie", "sie", "się", "jest", "bez", "jak", "tego", "przez", "oraz",
           "który", "która", "tylko", "juz", "już", "czy", "dla", "ale"},
    "de": {"der", "die", "das", "und", "ist", "den", "von", "mit", "auf",
           "für", "ein", "eine", "nicht", "auch", "wird", "dem", "sich"},
    "it": {"che", "di", "il", "la", "per", "con", "una", "del", "sono",
           "non", "come", "più", "nel", "alla", "dei", "anche"},
    "tr": {"ve", "bir", "bu", "için", "ile", "olarak", "daha", "kadar",
           "sonra", "ancak", "veya", "gibi", "olan"},
    "vi": {"và", "của", "trong", "có", "được", "cho", "với", "này", "các",
           "là", "không", "từ", "khi", "trên"},
}

_WORD_RE = re.compile(r"[a-zà-ÿąćęłńóśźż]+", re.U)


def detect_lang_ok(text: str, target, min_words: int = 8) -> bool:
    """判断文本是否属于目标语种。target 可以是单个语种或语种列表。

    地区配置里常见一个地区混跑两种语言（印尼版既有印尼语查询组、
    也有英文的国际视角组），所以要允许放行多个语种。

    判别信号是"目标语种命中数压过其他所有语种"，而不是命中占比 —— 印尼语
    新闻标题实词密集（"Bappebti resmi mencabut izin usaha..."功能词只占 1/14），
    卡占比会把监管新闻这类高价值内容误杀。

    两种情况一律放行，宁可漏过也不误杀：
      - 文本太短，样本不足以判定
      - 所有语种都零命中（多半是纯代码/数字列表）
    """
    targets = [target] if isinstance(target, str) else list(target)
    targets = [t for t in targets if t in _LANG_MARKERS]
    if not targets:
        return True
    words = _WORD_RE.findall(text.lower())
    if len(words) < min_words:
        return True
    counts = {lg: sum(1 for w in words if w in mk) for lg, mk in _LANG_MARKERS.items()}
    hit = max(counts[t] for t in targets)
    rivals = max((v for lg, v in counts.items() if lg not in targets), default=0)
    if hit == 0 and rivals == 0:
        return True
    return hit > rivals


def tokens(text: str) -> set[str]:
    """提取内容词，用于去重指纹。"""
    t = _NONWORD_RE.sub(" ", clean_text(text).lower())
    return {w for w in t.split() if len(w) > 2 and w not in STOPWORDS}


# ---------------------------------------------------------------------------
# 事件实体提取
# ---------------------------------------------------------------------------
# 句首常见大写词，不算实体
_COMMON_CAP = {
    "The", "This", "That", "These", "Those", "It", "We", "You", "They", "He", "She",
    "A", "An", "And", "But", "Or", "If", "So", "As", "At", "In", "On", "To", "For",
    "With", "From", "What", "Which", "Who", "When", "Where", "Why", "How", "Now",
    "New", "Just", "Breaking", "My", "Here", "There", "Not", "No", "Yes", "All",
    "More", "Most", "One", "Two", "After", "Before", "Today", "Yesterday", "Will",
    "Can", "Should", "Would", "Its", "Their", "Our", "His", "Her", "Is", "Are",
    "Was", "Were", "Be", "Been", "Has", "Have", "Had", "Do", "Does", "Did", "Get",
    "Got", "Only", "Also", "Still", "Even", "Every", "Some", "Any", "Because",
    "Look", "See", "Watch", "Read", "Via", "Everyone", "Update", "Live", "Next",
}

_CAP_RE = re.compile(r"\b([A-Z][a-zA-Z]{2,})\b")
_UPPER_RE = re.compile(r"\b([A-Z]{2,7})\b")
_NUM_RE = re.compile(
    r"\b(\d+(?:\.\d+)?\s*(?:bps|bp|%|k|bn|billion|trillion))\b", re.I
)


def entities(text: str) -> set[str]:
    """抽事件特征实体：专有名词 + 全大写代码 + 带单位数字。

    为什么不用词袋：实测一条推平均 58 个内容词，两条讲同一事件的推共享的
    却全是 said / because / things 这类通用词，相似度被稀释到 0.1 以下。
    只看实体后平均降到 17 个，共享的是 bessent / boj / ueda 这种真正
    标识事件的词。
    """
    t = clean_text(text)
    e = {w.lower() for w in _CAP_RE.findall(t) if w not in _COMMON_CAP}
    e |= {w.lower() for w in _UPPER_RE.findall(t) if len(w) >= 2}
    e |= {m.lower().replace(" ", "") for m in _NUM_RE.findall(t)}
    return {w for w in e if w not in STOPWORDS}


# ---------------------------------------------------------------------------
# 管道各步
# ---------------------------------------------------------------------------
def dedup(items: list[dict]) -> list[dict]:
    """按 ID 去重，再按文本指纹去重（同一内容多号发的情况）。"""
    seen_id, seen_fp, out = set(), set(), []
    for it in items:
        if it["id"] in seen_id:
            continue
        seen_id.add(it["id"])
        fp = frozenset(sorted(tokens(it["text"]))[:12])
        if len(fp) >= 5:
            if fp in seen_fp:
                continue
            seen_fp.add(fp)
        out.append(it)
    return out


def filter_noise(items: list[dict], cfg: dict) -> tuple[list[dict], dict]:
    """规则过滤。返回 (保留项, 各原因剔除计数)。"""
    noise = _compile(cfg.get("noise_patterns", []))
    sc = cfg["scoring"]
    min_len = sc.get("min_text_length", 40)
    min_fol = sc.get("min_author_followers", 0)

    # 时间窗硬过滤。采集端已把 since: 写进搜索词，这里再兜一道底 ——
    # 上游一旦回退成字段方式就会混进几年前的旧推，纯靠时效衰减压制不够干净
    max_age = cfg["run"].get("lookback_hours", 24) * 1.5
    now_utc = datetime.now(timezone.utc)

    min_latin = sc.get("min_latin_ratio", 0.85)
    want_lang = sc.get("require_language")
    # 主题闸：必须命中至少一条才算外汇相关。
    # 搜索词只能保证"提到过某个词"，拦不住印度政治推特里满天飞的
    # "RICE SCAM"、GDP 党派宣传——那些同样命中 scam / GDP。
    topic = _compile(cfg.get("topic_patterns", []))

    kept, dropped = [], {"噪音规则": 0, "文本过短": 0, "粉丝不足": 0,
                         "无时间": 0, "超出时间窗": 0,
                         "非拉丁文字": 0, "语种不符": 0, "非外汇主题": 0}
    for it in items:
        body = clean_text(it["text"])
        if not it.get("created_at"):
            dropped["无时间"] += 1
            continue
        age_h = (now_utc - datetime.fromisoformat(it["created_at"])).total_seconds() / 3600
        if age_h > max_age:
            dropped["超出时间窗"] += 1
            continue
        if len(body) < min_len:
            dropped["文本过短"] += 1
            continue
        # X 的 lang 参数不严格，日文/俄文等仍会混进来；
        # 日英混排的推（前半日文、后半引英文原文）拉丁占比能到 0.7，所以卡 0.85
        if _latin_ratio(body) < min_latin:
            dropped["非拉丁文字"] += 1
            continue
        if want_lang and not detect_lang_ok(body, want_lang):
            dropped["语种不符"] += 1
            continue
        if it["platform"] == "x" and it["author_followers"] < min_fol:
            dropped["粉丝不足"] += 1
            continue
        if any(p.search(body) for p in noise):
            dropped["噪音规则"] += 1
            continue
        if topic and not any(p.search(body) for p in topic):
            dropped["非外汇主题"] += 1
            continue
        kept.append(it)
    return kept, dropped


def score_items(items: list[dict], cfg: dict, now: datetime | None = None) -> list[dict]:
    """热度分 = 互动量 × 作者权重 × 时效衰减 × 信号词加成 × 查询组权重。"""
    sc = cfg["scoring"]
    boost_pats = _compile(cfg.get("signal_boost_patterns", []))
    now = now or datetime.now(timezone.utc)
    half = sc.get("recency_halflife_hours", 10) or 10
    cap = sc.get("author_weight_cap", 1.6)

    for it in items:
        e = it["engagement"]
        if it["platform"] == "x":
            raw = (
                e.get("likes", 0) * sc.get("x_like_weight", 1.0)
                + e.get("shares", 0) * sc.get("x_retweet_weight", 2.5)
                + e.get("comments", 0) * sc.get("x_reply_weight", 1.2)
                + e.get("quotes", 0) * sc.get("x_quote_weight", 2.0)
            )
            author_w = min(cap, 1 + math.log10(it["author_followers"] + 10) / 10)
        elif it["platform"] == "serper_news":
            # 新闻没有社媒互动指标，给一个稳定的基准分，由新闻时效、查询组权重
            # 以及后续的诈骗优先级决定名次，避免把它误按 0 热度直接筛掉。
            raw = sc.get("serper_news_base_score", 60)
            author_w = 1.0
        else:
            raw = (
                e.get("likes", 0) * sc.get("reddit_upvote_weight", 1.0)
                + e.get("comments", 0) * sc.get("reddit_comment_weight", 2.5)
            )
            author_w = 1.0

        created = datetime.fromisoformat(it["created_at"])
        hours = max(0.0, (now - created).total_seconds() / 3600)
        recency = 0.5 ** (hours / half)

        body = clean_text(it["text"])
        signal = sc.get("signal_boost", 1.35) if any(
            p.search(body) for p in boost_pats
        ) else 1.0

        it["hours_ago"] = round(hours, 1)
        it["has_signal"] = signal > 1.0
        it["score"] = round(
            math.log1p(raw) * author_w * recency * signal * it["group_weight"], 2
        )
    return sorted(items, key=lambda x: -x["score"])


def cluster(items: list[dict], cfg: dict) -> list[dict]:
    """把讲同一件事的条目并成话题。

    先按类别分桶，只在「同市场 + 同类别」内比对（市场维度由调用方保证——
    每次只处理一个地区）。这样监管稿不会跟行情稿并到一起，即使它们
    共享 RBI、rupee 这些实体。

    桶内用实体重叠系数而非词 Jaccard：
      - Jaccard 分母是并集，推文一长相似度就被拉到 0.1 以下，永远合并不了
      - 重叠系数 |A∩B| / min(|A|,|B|) 对长短不一的文本更稳
    再要求至少共享 min_shared_terms 个实体，避免只撞上一个词就误合并。
    """
    buckets: dict[str, list[dict]] = {}
    for it in items:
        cid = (it.get("category") or {}).get("id", "other")
        buckets.setdefault(cid, []).append(it)

    topics: list[dict] = []
    for group in buckets.values():
        topics.extend(_cluster_bucket(group, cfg))
    return sorted(topics, key=lambda t: -t["topic_score"])


def _cluster_bucket(items: list[dict], cfg: dict) -> list[dict]:
    """在单个类别桶内做聚类。items 需已按分降序。"""
    cc = cfg["clustering"]
    thr = cc.get("overlap_threshold", 0.40)
    min_shared = cc.get("min_shared_terms", 2)
    max_size = cc.get("max_cluster_size", 8)

    ents = {it["id"]: entities(it["text"]) for it in items}
    used, topics = set(), []

    for seed in items:  # items 已按分降序，高分的当种子
        if seed["id"] in used:
            continue
        used.add(seed["id"])
        members = [seed]
        se = ents[seed["id"]]

        if len(se) >= min_shared:
            for other in items:
                if other["id"] in used or len(members) >= max_size:
                    continue
                oe = ents[other["id"]]
                if len(oe) < min_shared:
                    continue
                shared = se & oe
                if len(shared) >= min_shared and len(shared) / min(len(se), len(oe)) >= thr:
                    used.add(other["id"])
                    members.append(other)

        # 共同实体：主贴与其他成员都提到的词，用来给话题贴标签
        if len(members) > 1:
            common = set.union(*(se & ents[m["id"]] for m in members[1:]))
        else:
            common = se
        # 话题分：主贴分 + 其余成员的衰减贡献（体现"多人在讲同一件事"）
        topic_score = seed["score"] + sum(m["score"] * 0.25 for m in members[1:])

        topics.append({
            "topic_score": round(topic_score, 2),
            "lead": seed,
            "members": members,
            "mention_count": len(members),
            "platforms": sorted({m["platform"] for m in members}),
            "groups": sorted({m["group"] for m in members}),
            "key_entities": sorted(common)[:6],
            "category": seed.get("category", {}),
        })

    return sorted(topics, key=lambda t: -t["topic_score"])
