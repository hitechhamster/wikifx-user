"""采集层：抓 X 和 Reddit，归一化成统一结构。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import hashlib
import re
from urllib.parse import urlparse

from .enrich import discover_fraud_news

X_ACTOR = "kaitoeasyapi~twitter-x-data-tweet-scraper-pay-per-result-cheapest"
REDDIT_ACTOR = "trudax~reddit-scraper-lite"

# 查询在时间窗内零命中时，这个 actor 会返回十几行自己的推广文案充数，
# 而且照常按条计费。不滤掉的话日志会显示"某查询组 15 条"，
# 实际真实命中是 0 —— 查询调优就无从谈起了。
_FILLER = re.compile(r"KaitoEasyAPI|Our API pricing is based on", re.I)


def _is_filler(tweet: dict) -> bool:
    if _FILLER.search(tweet.get("text") or ""):
        return True
    # 占位行没有作者信息
    return not ((tweet.get("author") or {}).get("userName") or "").strip()


def _parse_time(value) -> datetime | None:
    """尽量把各家的时间格式解析成带时区的 datetime。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):  # unix 时间戳
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    s = str(value).strip()
    if not s:
        return None
    # Twitter 格式: "Mon Aug 31 11:01:49 +0000 2026"
    try:
        return parsedate_to_datetime(s)
    except (TypeError, ValueError):
        pass
    for fmt in ("%a %b %d %H:%M:%S %z %Y", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(s.replace("Z", "+0000"), fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _norm(**kw) -> dict:
    """统一条目结构。"""
    item = {
        "id": kw["id"],
        "platform": kw["platform"],
        "url": kw.get("url", ""),
        "title": kw.get("title", ""),
        "text": kw.get("text", "") or "",
        "author": kw.get("author", ""),
        "author_name": kw.get("author_name", ""),
        "author_followers": kw.get("author_followers", 0) or 0,
        # 认证状态：编辑判断信源可靠性要看这个。蓝V是付费的，跟旧的官方认证
        # 不是一回事，两者分开存，不合并成一个布尔值
        "author_verified": bool(kw.get("author_verified")),
        "author_blue": bool(kw.get("author_blue")),
        "created_at": kw["created_at"].isoformat() if kw.get("created_at") else None,
        "engagement": kw.get("engagement", {}),
        "group": kw.get("group", ""),
        "group_weight": kw.get("group_weight", 1.0),
    }
    # Serper 新闻作为独立候选进入榜单时，保留来源属性，供机会分和审核台说明。
    for key in ("news_source", "news_trusted", "serper_fraud_news"):
        if key in kw:
            item[key] = kw[key]
    return item


def _trusted_news_source(url: str, trusted: list[str]) -> bool:
    try:
        domain = (urlparse(url).netloc or "").lower().removeprefix("www.")
    except ValueError:
        return False
    return any(domain == item.lower() or domain.endswith("." + item.lower())
               for item in trusted)


def fetch_serper_fraud_news(cfg: dict, region: str) -> list[dict]:
    """将 Serper 的新闻结果归一成候选条目。"""
    conf = cfg.get("serper_fraud_news") or {}
    group_weight = float(conf.get("group_weight", 2.6))
    trusted = cfg.get("trusted_media") or []
    now = datetime.now(timezone.utc)
    out = []
    for news in discover_fraud_news(region, cfg):
        title = news.get("title", "")
        snippet = news.get("snippet", "")
        text = f"{title}. {snippet}".strip()
        if not text:
            continue
        age = news.get("age_hours")
        created = now - timedelta(hours=float(age or 0))
        url = news.get("url", "")
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
        out.append(_norm(
            id=f"serper-news:{digest}",
            platform="serper_news",
            url=url,
            title=title,
            text=text,
            author=news.get("source") or "Serper News",
            author_name=news.get("source") or "Serper News",
            created_at=created,
            engagement={"likes": 0, "shares": 0, "comments": 0,
                        "quotes": 0, "views": 0},
            group=news.get("query_group") or "Serper 外汇诈骗新闻",
            group_weight=group_weight,
            news_source=news.get("source") or "",
            news_trusted=_trusted_news_source(url, trusted),
            serper_fraud_news=True,
        ))
    return out


def fetch_x(api, cfg, since: datetime) -> list[dict]:
    """按配置里的每个查询组抓 X。"""
    s = cfg["x_settings"]
    # 时间窗必须写进搜索词本身，不能用 since_time 字段。
    # 实测三种写法：since_time 传 unix 秒只有 51% 的结果在窗口内，传
    # "_UTC" 字符串 63%，把 since: 直接拼进查询串才是 100%。
    # 之前用字段方式，抓回来的数据里有近半超过 30 天，最老的是 2014 年的推文，
    # 等于一直在为大量陈旧内容付费。
    since_str = since.strftime("%Y-%m-%d_%H:%M:%S_UTC")
    out: list[dict] = []

    for q in cfg["x_queries"]:
        payload = {
            "searchTerms": [f'{q["query"]} since:{since_str}'],
            "queryType": s.get("query_type", "Top"),
            "maxItems": s.get("max_items_per_query", 50),
            # 地区配置里可以按查询组单独指定语种（比如印尼版同时跑 id 和 en）
            "lang": q.get("lang", s.get("lang", "en")),
            "min_faves": q.get("min_faves", 30),
        }
        items = api.run_actor(X_ACTOR, payload, timeout=180)

        # Top 排序 + min_faves 在 actor 侧偶发返回“15 条推广占位行”而不是结果。
        # 这不代表整个查询真的没有帖子；按最新排序、取消互动门槛重试一次，仍严格
        # 保留同一个 since: 时间窗。这样修复数据可用性，且不会为了填榜混进陈旧内容。
        real_items = [x for x in items if x.get("id") and not _is_filler(x)]
        if (not real_items and items and s.get("retry_empty_with_latest", True)):
            retry_payload = {
                **payload,
                "queryType": "Latest",
                "min_faves": s.get("fallback_min_faves", 0),
            }
            print(f"    · {q['name']} 首次仅占位行，Latest/0赞重试…")
            retry_items = api.run_actor(X_ACTOR, retry_payload, timeout=180)
            retry_real = [x for x in retry_items
                          if x.get("id") and not _is_filler(x)]
            if retry_real:
                items = retry_items
                print(f"    · {q['name']} 重试补回 {len(retry_real)} 条真实帖子")
        kept, filler = 0, 0
        for t in items:
            tid = t.get("id")
            if not tid:
                continue
            if _is_filler(t):
                filler += 1
                continue
            a = t.get("author") or {}
            out.append(
                _norm(
                    id=f"x:{tid}",
                    platform="x",
                    url=t.get("twitterUrl") or t.get("url", ""),
                    text=t.get("text", ""),
                    author=a.get("userName", ""),
                    author_name=a.get("name", ""),
                    author_followers=a.get("followers", 0),
                    author_verified=a.get("isVerified"),
                    author_blue=a.get("isBlueVerified"),
                    created_at=_parse_time(t.get("createdAt")),
                    engagement={
                        "likes": t.get("likeCount", 0) or 0,
                        "shares": t.get("retweetCount", 0) or 0,
                        "comments": t.get("replyCount", 0) or 0,
                        "quotes": t.get("quoteCount", 0) or 0,
                        "views": t.get("viewCount", 0) or 0,
                    },
                    group=q["name"],
                    group_weight=q.get("weight", 1.0),
                )
            )
            kept += 1
        lang = q.get("lang", s.get("lang", "en"))
        note = f"（另有 {filler} 条 actor 占位行已丢弃）" if filler else ""
        print(f"    [X/{lang}] {q['name']}: {kept} 条{note}")
    return out


def fetch_reddit(api, cfg) -> list[dict]:
    """抓配置里的各个 subreddit 当日热帖。"""
    s = cfg["reddit_settings"]
    if not s.get("enabled", True):
        print("    [Reddit] 已在配置中关闭，跳过")
        return []
    subs = cfg["reddit_subreddits"]
    weights = {x["name"].lower(): x.get("weight", 1.0) for x in subs}

    payload = {
        "startUrls": [
            {
                "url": f"https://www.reddit.com/r/{x['name']}/top/"
                       f"?t={s.get('time', 'day')}"
            }
            for x in subs
        ],
        "sort": s.get("sort", "top"),
        "time": s.get("time", "day"),
        "maxItems": s.get("max_items_per_sub", 25) * len(subs),
        "maxPostCount": s.get("max_items_per_sub", 25),
        "skipComments": True,
        "skipUserPosts": True,
        "searchPosts": True,
        "searchComments": False,
        "searchCommunities": False,
        "searchUsers": False,
        "includeNSFW": False,
        "includeMediaLinks": True,
        "proxy": {"useApifyProxy": True},
        # 默认 40s/页滚动，4个板块串行会超时；压到 15s 足够拿到当日热帖
        "scrollTimeout": 15,
        "navigationTimeout": 45,
    }
    items = api.run_actor(REDDIT_ACTOR, payload, timeout=600)

    out: list[dict] = []
    min_up = s.get("min_upvotes", 0)
    for p in items:
        # 该 actor 会混入 community/user 类型条目，只保留帖子
        if p.get("dataType") not in (None, "post"):
            continue
        pid = p.get("id") or p.get("parsedId") or p.get("url")
        if not pid:
            continue
        ups = p.get("upVotes") or p.get("score") or p.get("upvotes") or 0
        if ups < min_up:
            continue
        sub = (p.get("parsedCommunityName") or p.get("communityName") or "").lstrip("r/")
        title = p.get("title") or ""
        body = p.get("body") or p.get("text") or ""
        out.append(
            _norm(
                id=f"reddit:{pid}",
                platform="reddit",
                url=p.get("url", ""),
                title=title,
                text=f"{title}. {body}".strip(),
                author=p.get("username") or p.get("author", ""),
                author_followers=0,
                created_at=_parse_time(p.get("createdAt") or p.get("created")),
                engagement={
                    "likes": ups,
                    "shares": 0,
                    "comments": p.get("numberOfComments") or p.get("numComments") or 0,
                    "quotes": 0,
                    "views": 0,
                },
                group=f"r/{sub}" if sub else "reddit",
                group_weight=weights.get(sub.lower(), 1.0),
            )
        )
    print(f"    [Reddit] {len(out)} 条 (来自 {len(subs)} 个板块)")
    return out


def collect_all(api, cfg) -> list[dict]:
    hours = cfg["run"].get("lookback_hours", 24)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    print(f"  时间窗: {since:%Y-%m-%d %H:%M} UTC 起，回溯 {hours} 小时")
    social = fetch_x(api, cfg, since) + fetch_reddit(api, cfg)
    region = (cfg.get("region") or {}).get("name", "global")
    news = fetch_serper_fraud_news(cfg, region)
    print(f"    [汇总] 社媒 {len(social)} 条 + Serper 诈骗新闻 {len(news)} 条")
    return social + news
