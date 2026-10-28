"""信息源补充：拿热点话题去搜真实新闻报道，给写稿提供交叉印证素材。

社媒推文本身信息很薄（"market chatter puts the number close to $5 billion"），
搜一圈能拿到主流财经媒体的独立报道（"RBI ... having sold at least $5 billion"），
稿子才立得住。
"""
from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
SERPER_NEWS = "https://google.serper.dev/news"

# 各地区的检索地域和语种。gl 影响结果的本地化程度，
# 印尼要同时搜印尼语和英语，本地监管消息基本只有印尼语媒体报。
REGION_SEARCH = {
    "india":     [{"gl": "in", "hl": "en"}],
    "indonesia": [{"gl": "id", "hl": "id"}, {"gl": "id", "hl": "en"}],
    "pakistan":  [{"gl": "pk", "hl": "en"}],
    "global":    [{"gl": "us", "hl": "en"}],
}

# 补充信息源只用来给模型垫事件背景，不是事件本身，所以必须和事件同期 ——
# 搜到半年前的旧稿当"佐证"，模型会把陈年旧事写成今天发生的新闻。
# qdr:d3 = 谷歌新闻的近 3 天筛选，配合下面的 date 解析做双保险
SEARCH_WINDOW_HOURS = 72
SEARCH_TBS = "qdr:d3"

from .rank import _COMMON_CAP, _LANG_MARKERS, STOPWORDS  # noqa: E402

# 检索词里没意义的词。喊单体推文全是大写（"CRUDE IS THE HEADACHE"），
# 句首词也会被当成专有名词（"Here's..."、"Kalau..."），都得滤掉。
_QUERY_STOP = (
    {w.lower() for w in _COMMON_CAP}
    | STOPWORDS
    | _LANG_MARKERS["id"]
    | {
        "breaking", "just", "update", "live", "watch", "video", "thread",
        "today", "yesterday", "week", "month", "year", "market", "markets",
        "news", "report", "says", "said", "latest", "alert", "important",
        "kalau", "lihat", "buat", "jadi", "sama", "biar", "gak", "nya",
        "simak", "berikut", "terus", "masih", "sudah", "banget",
    }
)

_CAP = re.compile(r"\b([A-Z][a-zA-Z]{2,})\b")
_UPPER = re.compile(r"\b([A-Z]{2,7})\b")
_URL = re.compile(r"https?://\S+")


def load_keys() -> list[str]:
    """读 Serper key 池。逗号分隔，配额耗尽时按序轮换。"""
    raw = os.environ.get("SERPER_API_KEYS", "")
    if not raw:
        env = ROOT / ".env"
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("SERPER_API_KEYS="):
                    raw = line.split("=", 1)[1].strip()
                    break
    return [k.strip() for k in raw.split(",") if k.strip()]


def build_query(topic: dict, region: str, max_terms: int = 5) -> str:
    """从话题里抽检索词。

    按出现顺序取专有名词和全大写代码 —— 新闻习惯把关键实体写在前面，
    所以文首的词天然更重要，比按词频排更准。
    """
    text = _URL.sub(" ", topic["lead"].get("text", ""))
    head = text[:260]                      # 只看开头，后面多是补充和话题标签

    terms, seen = [], set()
    for m in re.finditer(r"\b([A-Z][a-zA-Z]{2,}|[A-Z]{2,7})\b", head):
        w = m.group(1)
        lw = w.lower()
        if lw in _QUERY_STOP or lw in seen:
            continue
        seen.add(lw)
        terms.append(w)
        if len(terms) >= max_terms:
            break

    # 补一个地域词，避免搜到别国的同名事件
    hint = {"india": "India", "indonesia": "Indonesia",
            "pakistan": "Pakistan"}.get(region, "")
    if hint and hint.lower() not in seen:
        terms.append(hint)
    return " ".join(terms)


_REL_DATE = re.compile(
    r"(\d+)\s*(minute|hour|day|week|month|year|menit|jam|hari|minggu|bulan|tahun)",
    re.I)
_REL_UNIT_HOURS = {
    "minute": 1 / 60, "menit": 1 / 60,
    "hour": 1, "jam": 1,
    "day": 24, "hari": 24,
    "week": 168, "minggu": 168,
    "month": 720, "bulan": 720,
    "year": 8760, "tahun": 8760,
}


def source_age_hours(date_str: str) -> float | None:
    """把 Serper 的 date 字段折成"距今多少小时"。解析不出来返回 None。

    Serper 返回的多是相对时间（"2 hours ago"、"3 days ago"、"2 hari lalu"），
    偶尔给绝对日期（"Sep 5, 2026"）。解析不出的一律当作通过 —— 宁可多留一篇
    不确定的，也不要因为格式没见过就把有效佐证丢掉。
    """
    d = (date_str or "").strip()
    if not d:
        return None
    m = _REL_DATE.search(d)
    if m:
        return int(m.group(1)) * _REL_UNIT_HOURS[m.group(2).lower()]
    for fmt in ("%b %d, %Y", "%d %b %Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            dt = datetime.strptime(d, fmt).replace(tzinfo=timezone.utc)
            return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600)
        except ValueError:
            continue
    return None


def _search_once(key: str, query: str, gl: str, hl: str, num: int,
                 tbs: str = SEARCH_TBS) -> tuple[list, str]:
    """返回 (结果列表, 错误原因)。配额/鉴权类错误交给上层换 key。"""
    try:
        r = requests.post(
            SERPER_NEWS,
            headers={"X-API-KEY": key, "Content-Type": "application/json"},
            json={"q": query, "gl": gl, "hl": hl, "num": num, "tbs": tbs},
            timeout=25,
        )
    except requests.RequestException as e:
        return [], f"网络错误 {type(e).__name__}"
    if r.status_code in (401, 403, 429):
        return [], f"HTTP {r.status_code}（配额或鉴权）"
    if r.status_code >= 400:
        return [], f"HTTP {r.status_code}"
    try:
        return r.json().get("news") or [], ""
    except ValueError:
        return [], "返回非 JSON"


def discover_fraud_news(region: str, cfg: dict) -> list[dict]:
    """用 Serper 主动发现近期外汇诈骗新闻，作为日榜的独立候选来源。

    这与 ``search(topic, region)`` 不同：后者是先有社媒话题再补充证据；这里
    每天先搜外汇诈骗/假平台/投资骗局，避免一条重要新闻因为社媒讨论量不足而
    根本没有进入编辑队列。
    """
    spec = cfg.get("serper_fraud_news") or {}
    if not spec.get("enabled", False):
        return []
    keys = load_keys()
    if not keys:
        print("    [Serper/诈骗新闻] 未配置 SERPER_API_KEYS，跳过")
        return []

    window = int(spec.get("window_hours", 48))
    tbs = spec.get("tbs", "qdr:d2")
    per_query = int(spec.get("max_items_per_query", 8))
    locations = spec.get("locations") or REGION_SEARCH.get(region, REGION_SEARCH["global"])
    seen, found, key_index = set(), [], 0

    for query_spec in spec.get("queries") or []:
        query = str(query_spec.get("query") or "").strip()
        if not query:
            continue
        name = str(query_spec.get("name") or "Serper 外汇诈骗新闻")
        for loc in locations:
            hits, error = [], ""
            for _ in range(len(keys)):
                hits, error = _search_once(
                    keys[key_index], query, loc["gl"], loc["hl"], per_query, tbs)
                if not error:
                    break
                key_index = (key_index + 1) % len(keys)
            if error:
                print(f"    [Serper/诈骗新闻] {name}: {error}")
                continue
            for item in hits:
                url = str(item.get("link") or "").strip()
                if not url or url in seen:
                    continue
                age = source_age_hours(str(item.get("date") or ""))
                if age is not None and age > window:
                    continue
                seen.add(url)
                found.append({
                    "title": str(item.get("title") or "").strip(),
                    "snippet": str(item.get("snippet") or "").strip(),
                    "source": str(item.get("source") or "").strip(),
                    "date": str(item.get("date") or "").strip(),
                    "age_hours": age,
                    "url": url,
                    "query_group": name,
                })

    print(f"    [Serper/诈骗新闻] {len(found)} 篇（{len(spec.get('queries') or [])} 组检索）")
    return found


def search(topic: dict, region: str, per_query: int = 10,
           max_sources: int = 12) -> dict:
    """搜相关新闻报道。返回 {query, sources[], note}，失败也不抛异常。

    写稿是主流程，检索只是增强 —— 搜不到就退回只用推文当素材，不能因此写不出稿。
    """
    keys = load_keys()
    if not keys:
        return {"query": "", "sources": [], "note": "未配置 SERPER_API_KEYS，跳过检索"}

    query = build_query(topic, region)
    if not query.strip():
        return {"query": "", "sources": [], "note": "抽不出检索词，跳过检索"}

    locales = REGION_SEARCH.get(region, REGION_SEARCH["global"])
    sources, seen_urls, notes = [], set(), []
    stale = 0            # 超出时间窗被丢掉的篇数，写进 note 便于排查
    ki = 0

    for loc in locales:
        hits, err = [], ""
        # key 池轮换：配额耗尽自动换下一把
        for _ in range(len(keys)):
            hits, err = _search_once(keys[ki], query, loc["gl"], loc["hl"], per_query)
            if not err:
                break
            notes.append(f"key#{ki + 1} {err}")
            ki = (ki + 1) % len(keys)
        if err:
            continue

        for n in hits:
            url = (n.get("link") or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            date = (n.get("date") or "").strip()
            age = source_age_hours(date)
            # 解析不出日期的放行，解析出来且超窗的丢掉
            if age is not None and age > SEARCH_WINDOW_HOURS:
                stale += 1
                continue
            sources.append({
                "title": (n.get("title") or "").strip(),
                "source": (n.get("source") or "").strip(),
                "date": date,
                "age_hours": None if age is None else round(age, 1),
                "snippet": (n.get("snippet") or "").strip(),
                "url": url,
            })
            if len(sources) >= max_sources:
                break
        if len(sources) >= max_sources:
            break

    if stale:
        notes.append(f"{stale} 篇超出 {SEARCH_WINDOW_HOURS} 小时窗口已丢弃")
    return {
        "query": query,
        "sources": sources,
        "window_hours": SEARCH_WINDOW_HOURS,
        "stale_dropped": stale,
        "note": "；".join(notes[-2:]) if notes else "",
    }


def format_sources(sources: list[dict]) -> str:
    """拼成给模型看的素材块。"""
    if not sources:
        return ""
    lines = ["",
             "【相关新闻报道 —— 背景上下文，不是本篇要报道的事件】",
             "以下是按主贴关键词检索到的近 72 小时公开报道，供交叉印证和补充背景。"
             "本篇报道的事件仍以上面的主贴为准；若这些报道讲的不是同一件事，弃用即可，"
             "不要改写成它们的主题。引用时必须标明媒体名。"]
    for i, s in enumerate(sources, 1):
        age = s.get("age_hours")
        when = s["date"] + (f"，约 {age:.0f} 小时前" if age is not None else "")
        lines.append(f"{i}. [{s['source']}｜{when}] {s['title']}")
        # 抓到正文就用正文，素材量是摘要的几十倍，长稿全靠它撑
        if s.get("body"):
            lines.append(f"   正文：{s['body']}")
        elif s.get("snippet"):
            lines.append(f"   摘要：{s['snippet']}")
        lines.append(f"   链接：{s['url']}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# 正文抓取
# ---------------------------------------------------------------------------
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
_DROP_TAGS = re.compile(
    r"<(script|style|nav|footer|header|aside|form|iframe|noscript)[^>]*>.*?</\1>",
    re.S | re.I)
_P_TAG = re.compile(r"<p\b[^>]*>(.*?)</p>", re.S | re.I)
_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _extract_body(html: str, max_chars: int) -> str:
    """从 HTML 里抠正文。

    优先取 <p> 标签内容 —— 导航、页脚、推荐位很少用 <p> 包裹，
    这一步就能滤掉大部分模板噪音。取不到再退回全文去标签。
    """
    cleaned = _DROP_TAGS.sub(" ", html)
    paras = []
    for m in _P_TAG.findall(cleaned):
        txt = _WS.sub(" ", _TAGS.sub(" ", m)).strip()
        if len(txt) >= 40:          # 太短的多半是图片说明或版权行
            paras.append(txt)
    text = "\n".join(paras) if paras else _WS.sub(" ", _TAGS.sub(" ", cleaned)).strip()
    return text[:max_chars]


def fetch_bodies(sources: list[dict], top_n: int = 7, max_chars: int = 3500,
                 timeout: int = 12) -> int:
    """并发抓取报道正文，就地写入 source['body']。返回成功条数。

    摘要只有一两百字符，撑不起一篇长稿；正文能给到 30 倍的素材量。
    只抓判定为相关的前几篇，抓不到就跳过 —— 有些站点有反爬，不影响出稿。
    """
    picked = [s for s in sources if s.get("relevant", True)][:top_n]
    if not picked:
        return 0

    def grab(src: dict) -> bool:
        try:
            r = requests.get(src["url"], headers=_UA, timeout=timeout)
            if r.status_code != 200 or not r.text:
                return False
            body = _extract_body(r.text, max_chars)
            if len(body) < 200:      # 抓到的是空壳页
                return False
            src["body"] = body
            return True
        except (requests.RequestException, ValueError):
            return False

    with ThreadPoolExecutor(max_workers=min(5, len(picked))) as pool:
        return sum(pool.map(grab, picked))
