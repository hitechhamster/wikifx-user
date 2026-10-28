"""输出层：热点榜写成 JSON（给审核台）和 Markdown（给人看）。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .rank import clean_text

_ENG_KEYS = ("likes", "shares", "comments", "quotes", "views")


def _topic_stats(members: list[dict]) -> dict:
    """整簇的账号与互动维度 —— 给编辑判断"这个热度是真是假"用的。

    「多少个不同账号在说」比「多少条帖子」重要得多：单账号连发 4 条和
    4 个账号各发 1 条，热度含义完全不同，但只看帖子数是分不出来的。
    """
    per_author: dict[str, dict] = {}
    total = {k: 0 for k in _ENG_KEYS}

    for m in members:
        e = m.get("engagement") or {}
        for k in _ENG_KEYS:
            total[k] += e.get(k, 0) or 0
        name = m.get("author", "")
        a = per_author.setdefault(name, {
            "author": name,
            "author_name": m.get("author_name", ""),
            "followers": m.get("author_followers", 0),
            "verified": bool(m.get("author_verified")),
            "blue": bool(m.get("author_blue")),
            "posts": 0,
        })
        a["posts"] += 1
        a["followers"] = max(a["followers"], m.get("author_followers", 0))

    authors = sorted(per_author.values(),
                     key=lambda a: (-a["posts"], -a["followers"]))
    return {
        "post_count": len(members),
        "author_count": len(per_author),
        "authors": authors,
        "followers_max": max((a["followers"] for a in authors), default=0),
        "verified_count": sum(1 for a in authors if a["verified"] or a["blue"]),
        "engagement_total": total,
        "engagement_sum": sum(total[k] for k in ("likes", "shares",
                                                 "comments", "quotes")),
    }


def _snippet(text: str, n: int = 200) -> str:
    t = " ".join(clean_text(text).split())
    return t[:n] + ("…" if len(t) > n else "")


def _topic_payload(t: dict, rank: int) -> dict:
    """把一个话题拍平成可序列化的结构。members 里的原始对象不整个带出去。

    对已经拍平过的结构（跨市场榜会从磁盘读回其他地区当天的榜单）直接改个名次
    返回 —— 否则单跑一个地区时，其他地区的数据就没法参与汇总榜。
    """
    if "members" not in t:
        return {**t, "rank": rank}
    lead = t["lead"]
    ev = t.get("evidence") or {}
    return {
        "rank": rank,
        "label": t.get("label", ""),
        "label_by": t.get("label_by", ""),
        # AI 聚合层：标题、摘要、关键词/查询组都有中英印尼语三套文案。
        # 原始帖子及新闻标题仍保持原文，作为可复核证据。
        "i18n": t.get("i18n", {}),
        "opportunity": t.get("opportunity", {}),
        "category": t.get("category", {}),
        "topic_score": t["topic_score"],
        "mention_count": t["mention_count"],
        "platforms": t["platforms"],
        "groups": t["groups"],
        "key_entities": t.get("key_entities", []),
        "stats": _topic_stats(t["members"]),
        "evidence": {
            "first_party": ev.get("first_party", False),
            "trusted_media": ev.get("trusted_media", []),
            "trusted_count": ev.get("trusted_count", 0),
            "total_media": ev.get("total_media", 0),
            "found_total": ev.get("found_total", 0),
            "relevant_count": ev.get("relevant_count", 0),
            "searched": ev.get("searched", False),
            "query": ev.get("query", ""),
            "window_hours": ev.get("window_hours"),
            "stale_dropped": ev.get("stale_dropped", 0),
            "sources": ev.get("sources", []),
        },
        "lead": {
            "text": clean_text(lead["text"]),
            "author": lead["author"],
            "author_name": lead.get("author_name", ""),
            "author_verified": bool(lead.get("author_verified")),
            "author_blue": bool(lead.get("author_blue")),
            "author_followers": lead["author_followers"],
            "url": lead["url"],
            "platform": lead["platform"],
            "news_source": lead.get("news_source", ""),
            "news_trusted": bool(lead.get("news_trusted")),
            "serper_fraud_news": bool(lead.get("serper_fraud_news")),
            "created_at": lead["created_at"],
            "hours_ago": lead["hours_ago"],
            "score": lead["score"],
            "engagement": lead["engagement"],
            "has_signal": lead["has_signal"],
        },
        "also_seen": [
            {
                "text": _snippet(m["text"], 120),
                "author": m["author"],
                "author_followers": m.get("author_followers", 0),
                "author_verified": bool(m.get("author_verified")),
                "author_blue": bool(m.get("author_blue")),
                "url": m["url"],
                "platform": m["platform"],
                "engagement": m.get("engagement", {}),
                "hours_ago": m.get("hours_ago"),
                "score": m["score"],
            }
            for m in t["members"][1:]
        ],
    }


def write_reports(topics: list[dict], meta: dict, outdir: Path, date: str) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    picked = topics[:meta.get("top_n", 20)]

    payload = {
        "date": date,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "meta": meta,
        "topics": [_topic_payload(t, i) for i, t in enumerate(picked, 1)],
    }
    (outdir / f"{date}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path = outdir / f"{date}.md"
    md_path.write_text(_render_md(payload), encoding="utf-8")
    return {"json": outdir / f"{date}.json", "md": md_path, "count": len(picked)}


def write_top_board(board: list[dict], date: str, outdir: Path, cfg: dict) -> Path:
    """跨市场 Top 8 汇总榜。"""
    outdir.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": date,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "size": cfg["top_board"]["size"],
        "markets": cfg["top_board"]["markets"],
        "items": [
            {**_topic_payload(t, t.get("board_rank", i)), "region": t["region"]}
            for i, t in enumerate(board, 1)
        ],
    }
    (outdir / f"{date}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    L = [f"# 跨市场热点 Top {len(board)} · {date}", "",
         f"生成时间：{payload['generated_at']}　|　市场："
         f"{'、'.join(payload['markets'])}", "", "---", ""]
    for t in board:
        L += _render_topic(_topic_payload(t, t.get("board_rank", 0)),
                           region=t["region"])
    (outdir / f"{date}.md").write_text("\n".join(L), encoding="utf-8")
    return outdir / f"{date}.md"


def _render_topic(p: dict, region: str = "") -> list[str]:
    """渲染一个话题的 Markdown 段落。"""
    lead, o, ev = p["lead"], p["opportunity"], p["evidence"]
    st = p.get("stats", {})
    e = lead["engagement"]
    tot = st.get("engagement_total", {})
    head = f"## {p['rank']}. {p.get('label') or _snippet(lead['text'], 100)}"
    tags = [p["category"].get("name", "")]
    if region:
        tags.insert(0, region)
    if ev["first_party"]:
        tags.append("一手来源")
    if lead["has_signal"]:
        tags.append("新闻信号词")

    vmark = "✔" if (lead.get("author_verified") or lead.get("author_blue")) else ""
    L = [head, "", "　".join(f"`{t}`" for t in tags if t), "",
         f"- **机会分 {o.get('score', 0)}**"
         f"（流量 {o.get('traffic', 0)}　编辑 {o.get('editorial', 0)}"
         f"　证据 {o.get('evidence', 0)}）"
         + (f"　互动降权 ×{o.get('engagement_decay', 1)}"
            f"（加权互动 {o.get('weighted_engagement', 0)}）"
            if o.get('engagement_decay', 1) < 1 else ""),
         f"- **主贴** [{lead['platform'].upper()} @{lead['author']}{vmark}]"
         f"({lead['url']})（{lead['author_followers']:,} 粉）"
         f"　{lead['hours_ago']} 小时前",
         f"- **传播** {st.get('author_count', 1)} 个账号发了 "
         f"{st.get('post_count', 1)} 条"
         f"　认证号 {st.get('verified_count', 0)} 个"
         f"　最大粉丝量 {st.get('followers_max', 0):,}",
         f"- **互动（整簇合计）** 👍{tot.get('likes', 0):,}"
         f"　🔁{tot.get('shares', 0):,}　💬{tot.get('comments', 0):,}"
         f"　❝{tot.get('quotes', 0):,}　👀{tot.get('views', 0):,}",
         f"- **互动（主贴）** 👍{e.get('likes', 0):,}　🔁{e.get('shares', 0):,}"
         f"　💬{e.get('comments', 0):,}　👀{e.get('views', 0):,}",
         ]
    if p.get("key_entities"):
        L.append(f"- **关键词** {'、'.join(p['key_entities'])}")
    if ev["searched"]:
        L.append(f"- **信源** 检索到 {ev['found_total']} 篇 → "
                 f"判定相关 {ev['relevant_count']} 篇 → "
                 f"可信媒体 {ev['trusted_count']} 家"
                 + (f"（{'、'.join(ev['trusted_media'])}）"
                    if ev["trusted_media"] else "")
                 + (f"　⏱ 另有 {ev['stale_dropped']} 篇超 "
                    f"{ev.get('window_hours', 72)} 小时被丢弃"
                    if ev.get("stale_dropped") else ""))
    else:
        L.append("- **信源** 未检索")
    L += ["", "> " + _snippet(lead["text"], 400).replace("\n", " "), ""]

    if p["also_seen"]:
        L.append(f"<details><summary>同话题其他 {len(p['also_seen'])} 条</summary>")
        L.append("")
        for a in p["also_seen"]:
            ae = a.get("engagement") or {}
            v = "✔" if (a.get("author_verified") or a.get("author_blue")) else ""
            L.append(f"- [@{a['author']}{v}]({a['url']})"
                     f"（{a.get('author_followers', 0):,} 粉）"
                     f"　👍{ae.get('likes', 0):,} 🔁{ae.get('shares', 0):,}"
                     f" 💬{ae.get('comments', 0):,} — {a['text']}")
        L += ["", "</details>", ""]
    if ev["sources"]:
        L.append(f"<details><summary>检索到 {len(ev['sources'])} 篇报道</summary>")
        L.append("")
        for s in ev["sources"]:
            mark = "✓ " if s.get("relevant") else "　"
            L.append(f"- {mark}[{s['title']}]({s['url']}) — "
                     f"{s['source']}｜{s['date']}")
        L += ["", "</details>", ""]
    L += ["---", ""]
    return L


def _render_md(p: dict) -> str:
    m = p["meta"]
    cats = m.get("category_counts", {})
    L = [
        f"# {m.get('region_display', '')}外汇社媒热点榜 · {p['date']}",
        "",
        f"生成时间：{p['generated_at']}　|　回溯 {m.get('lookback_hours')} 小时",
        f"采集 {m.get('raw_count')} 条 → 过滤后 {m.get('kept_count')} 条 → "
        f"{m.get('topic_count')} 个话题（本页 {len(p['topics'])} 条）"
        f"　|　检索取证 {m.get('searched', 0)} 次",
        "类别分布：" + ("　".join(f"{k} {v}" for k, v in cats.items())
                    if cats else "-"),
        f"排序：机会分降序（已取消 Strong/Verify/Watch 分级）",
        f"Apify 花费：**${m.get('cost_usd', 0):.4f}**",
        "", "---", "",
    ]
    if not p["topics"]:
        L.append("> 本时段没有达到阈值的热点。可下调 config 里的 "
                 "`min_faves` 或 `scoring.min_score`。")
        return "\n".join(L)
    for t in p["topics"]:
        L += _render_topic(t)
    return "\n".join(L)
