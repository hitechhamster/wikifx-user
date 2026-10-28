"""机会分。

机会分 = 流量潜力 55% + 编辑相关度 25% + 证据可信度 20%，榜单直接按它降序排。

原先还有一层 Strong / Verify / Watch 三级分流，已移除：证据强度不再当闸门，
而是作为机会分里的一个分项 + 卡片上的展示维度，由编辑自己判断。
"""
from __future__ import annotations

import math
from urllib.parse import urlparse

from concurrent.futures import ThreadPoolExecutor

from .classify import is_allegation
from .enrich import search
from .rank import entities


# ---------------------------------------------------------------------------
# 证据
# ---------------------------------------------------------------------------
def _domain(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def _is_corroborating(source: dict, topic_ents: set[str], rel: dict) -> bool:
    """这篇报道是不是真在讲同一件事。

    检索是按话题关键词搜的，只要提到某个热词就能搜到一堆报道 —— 不校验的话，
    一条「FCNR(B) 是什么意思」的科普会因为媒体都在报 FCNR(B) 相关新闻而
    拿到满分证据分。要求报道标题摘要与推文共享足够多的实体才算佐证。
    """
    if not topic_ents:
        return False
    se = entities(f"{source.get('title', '')} {source.get('snippet', '')}")
    if not se:
        return False
    shared = topic_ents & se
    if len(shared) < rel.get("min_shared_entities", 2):
        return False
    return len(shared) / min(len(topic_ents), len(se)) >= rel.get(
        "overlap_threshold", 0.25)


def attach_evidence(topics: list[dict], cfg: dict, region: str,
                    limit: int | None = None) -> int:
    """给分数最高的前 N 个话题检索取证，写入 topic['evidence']。

    检索是为了拿证据（有几家可信媒体报道过），不是为了写稿素材 —— 后者在
    生成文章时另外再搜一次。全量搜太贵也太慢，所以只搜前 N 个候选。
    返回实际检索的话题数。
    """
    opp = cfg["opportunity"]
    limit = limit if limit is not None else opp.get("search_top_n", 25)
    officials = {a.lower() for a in (cfg.get("official_accounts") or [])}
    trusted = {d.lower() for d in (cfg.get("trusted_media") or [])}

    # 检索是纯 IO 等待，串行跑 50 个话题要几分钟。并发度压在 4，
    # 免得把 Serper 的速率限制打爆
    head = topics[:limit]
    if head:
        with ThreadPoolExecutor(max_workers=min(4, len(head))) as pool:
            results = list(pool.map(lambda t: search(t, region), head))
    else:
        results = []
    searched = len(results)

    for i, t in enumerate(topics):
        lead = t["lead"]
        first_party = lead.get("author", "").lower() in officials
        found = (results[i] if i < len(results)
                 else {"query": "", "sources": [], "note": "未进入检索名额"})

        # 只有讲同一件事的报道才算佐证
        rel = opp["evidence"].get("relevance", {})
        topic_ents = entities(lead.get("text", ""))
        for s in found["sources"]:
            s["relevant"] = _is_corroborating(s, topic_ents, rel)

        relevant = [s for s in found["sources"] if s["relevant"]]
        media_domains = {_domain(s["url"]) for s in relevant}
        media_domains.discard("")
        trusted_hits = sorted(
            d for d in media_domains
            if any(d == td or d.endswith("." + td) for td in trusted)
        )

        t["evidence"] = {
            "first_party": first_party,
            "trusted_media": trusted_hits,
            "trusted_count": len(trusted_hits),
            "total_media": len(media_domains),
            "found_total": len(found["sources"]),
            "relevant_count": len(relevant),
            "query": found["query"],
            "sources": found["sources"],
            "searched": i < limit,
            "window_hours": found.get("window_hours"),
            "stale_dropped": found.get("stale_dropped", 0),
        }
    return searched


def evidence_score(t: dict, cfg: dict) -> float:
    """证据可信度 0~1。按最强的一条证据取值。"""
    e = cfg["opportunity"]["evidence"]
    ev = t.get("evidence") or {}

    lead = t["lead"]
    lead_news = lead.get("platform") == "serper_news"
    lead_trusted = bool(lead.get("news_trusted"))
    if ev.get("first_party"):
        base = e["first_party"]
    elif lead_news and lead_trusted:
        # 独立新闻发现源本身是一家可信媒体；它仍会走后续交叉检索。
        base = e["media_1"]
    elif lead_news:
        base = e["media_untrusted"]
    elif ev.get("trusted_count", 0) >= 2:
        base = e["media_2plus"]
    elif ev.get("trusted_count", 0) == 1:
        base = e["media_1"]
    elif ev.get("total_media", 0) > 0:
        base = e["media_untrusted"]
    else:
        base = e["social_only"]

    # 指控类（诈骗/出金/平台）没有一手来源也没有两家以上可信媒体时打折。
    # 需求明确：这类不能因为「负面严重」就自动成为强热点
    cat = t["lead"].get("category", {}).get("id", "")
    if is_allegation(cat) and not ev.get("first_party") and not lead_trusted \
            and ev.get("trusted_count", 0) < 2:
        base *= e["allegation_discount"]
    return base


# ---------------------------------------------------------------------------
# 流量 / 编辑
# ---------------------------------------------------------------------------
def _norm(value: float, cap: float) -> float:
    return min(1.0, value / cap) if cap else 0.0


def traffic_score(t: dict, cfg: dict) -> tuple[float, dict]:
    """流量潜力 0~1，附各分项明细便于排查。"""
    w = cfg["opportunity"]["traffic"]
    half = cfg["scoring"].get("recency_halflife_hours", 10) or 10
    lead = t["lead"]
    ev = t.get("evidence") or {}

    # 互动量按整簇累计 —— 同一件事多人在讲，热度是加总的
    total_eng = 0.0
    for m in t["members"]:
        e = m["engagement"]
        total_eng += (e.get("likes", 0) + e.get("shares", 0) * 2.5
                      + e.get("comments", 0) * 1.2 + e.get("quotes", 0) * 2.0)

    parts = {
        "recency": 0.5 ** (lead.get("hours_ago", 0) / half),
        "media_count": _norm(ev.get("trusted_count", 0), w["media_cap"]),
        "platform_count": _norm(len(t.get("platforms") or []), 2),
        "query_groups": _norm(len(t.get("groups") or []), w["group_cap"]),
        "engagement": _norm(math.log1p(total_eng),
                            math.log1p(w["engagement_cap"])),
        "search_intent": lead.get("category", {}).get("search_intent", 0.35),
    }
    score = sum(parts[k] * w[k] for k in parts)
    return score, parts


def engagement_decay(t: dict, cfg: dict) -> tuple[float, float]:
    """返回（整体机会分系数，加权互动量）。

    分级取消后，一手来源的例行帖会因证据分满分压过真正有传播的新闻。这里不
    删除低互动话题，只将它们的总分平滑折减；编辑仍能在类别筛选中看到它们。
    """
    total = 0.0
    for member in t["members"]:
        e = member.get("engagement") or {}
        total += (e.get("likes", 0) + e.get("shares", 0) * 2.5
                  + e.get("comments", 0) * 1.2 + e.get("quotes", 0) * 2.0)
    conf = cfg["opportunity"].get("engagement_decay", {})
    full_at = max(1.0, float(conf.get("full_at", 20)))
    floor = min(1.0, max(0.0, float(conf.get("floor", 0.25))))
    factor = floor + (1 - floor) * min(1.0, total / full_at)
    return factor, total


def editorial_score(t: dict, cfg: dict) -> tuple[float, dict]:
    """编辑相关度 0~1。"""
    w = cfg["opportunity"]["editorial"]
    lead = t["lead"]
    # 查询组权重最高到 2.0，归一化到 0~1
    gw = min(1.0, max(m.get("group_weight", 1.0) for m in t["members"]) / 2.0)
    parts = {
        "category": lead.get("category", {}).get("editorial", 0.35),
        "group_weight": gw,
        "mentions": _norm(t.get("mention_count", 1), w["mention_cap"]),
    }
    return sum(parts[k] * w[k] for k in parts), parts


def score_topics(topics: list[dict], cfg: dict) -> list[dict]:
    """算机会分（0~100）并按分排序。"""
    W = cfg["opportunity"]["weights"]
    for t in topics:
        traffic, tparts = traffic_score(t, cfg)
        editorial, eparts = editorial_score(t, cfg)
        evidence = evidence_score(t, cfg)
        decay, weighted_engagement = engagement_decay(t, cfg)
        raw_score = (traffic * W["traffic"] + editorial * W["editorial"]
                     + evidence * W["evidence"]) * 100
        priority = cfg["opportunity"].get("fraud_priority", {})
        is_fraud = t["lead"].get("category", {}).get("id") == "fraud"
        serper_fraud = is_fraud and any(
            member.get("serper_fraud_news") for member in t["members"])
        multiplier = 1.0
        if is_fraud:
            multiplier = float(priority.get("base_multiplier", 1.35))
            if serper_fraud:
                multiplier = float(priority.get("serper_news_multiplier", 1.65))
        t["opportunity"] = {
            "score": round(raw_score * decay * multiplier, 1),
            "raw_score": round(raw_score, 1),
            "engagement_decay": round(decay, 3),
            "weighted_engagement": round(weighted_engagement, 1),
            "traffic": round(traffic * 100, 1),
            "editorial": round(editorial * 100, 1),
            "evidence": round(evidence * 100, 1),
            "fraud_priority_multiplier": round(multiplier, 2),
            "serper_fraud_news": serper_fraud,
            "traffic_parts": {k: round(v, 3) for k, v in tparts.items()},
            "editorial_parts": {k: round(v, 3) for k, v in eparts.items()},
        }
    return sorted(topics, key=lambda x: -x["opportunity"]["score"])


# ---------------------------------------------------------------------------
# 分位数工具
# ---------------------------------------------------------------------------
def _percentile(sorted_desc: list[float], q: float) -> float:
    """取分位值。sorted_desc 是降序分数列表，q=0.7 表示 70 分位。"""
    if not sorted_desc:
        return 0.0
    asc = sorted(sorted_desc)
    idx = min(len(asc) - 1, max(0, int(round(q * (len(asc) - 1)))))
    return asc[idx]


# ---------------------------------------------------------------------------
# 跨市场 Top 8
# ---------------------------------------------------------------------------
def pick_top_board(by_region: dict[str, list[dict]], cfg: dict) -> list[dict]:
    """跨市场汇总榜：先按市场配额保底，再用高分补满。

    by_region: {地区名: 已评分排序的话题列表}
    """
    board_cfg = cfg["top_board"]
    size = board_cfg["size"]
    markets = [m for m in board_cfg["markets"] if m in by_region]
    quota = board_cfg["quota_per_market"]
    floor_q = board_cfg["min_percentile"]

    # 每个市场先算准入线，低于本市场分位线的不参与
    pool: list[dict] = []
    for region in markets:
        topics = by_region[region]
        line = _percentile([t["opportunity"]["score"] for t in topics], floor_q)
        for t in topics:
            if t["opportunity"]["score"] >= line:
                pool.append({**t, "region": region})

    picked, used = [], set()

    def key(t):
        return (t["region"], t["lead"]["url"])

    def order(t):
        return -t["opportunity"]["score"]

    pool.sort(key=order)

    # 一轮配额：每个市场先保底
    for region in markets:
        cand = [t for t in pool if t["region"] == region][:quota]
        for t in cand:
            if len(picked) < size and key(t) not in used:
                used.add(key(t))
                picked.append(t)

    # 剩余名额按机会分补满
    rest = sorted((t for t in pool if key(t) not in used), key=order)
    for t in rest:
        if len(picked) >= size:
            break
        used.add(key(t))
        picked.append(t)

    picked.sort(key=order)
    for i, t in enumerate(picked, 1):
        t["board_rank"] = i
    return picked
