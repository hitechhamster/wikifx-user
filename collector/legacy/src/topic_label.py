"""为审核台生成可切换语言的 AI 聚合文案。

原始帖子、新闻标题是证据，应始终保留原语言；编辑面对的选题标题、摘要和
标签则是系统的聚合层，需要随界面的中/英/印尼语一起切换。
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

from .article import _load_env, _strip_fence
from .rank import clean_text

LANGS = ("zh", "en", "id")

SYSTEM = """你是外汇新闻编辑台的多语种选题编辑。

根据一段社媒原文，为同一个事件制作中文、英文和印尼语的编辑聚合文案。
只概括原文中明确存在的事实，绝不增加推测；保留机构简称、股票代码、货币
代码、人名及关键数字。原帖本身不需要翻译。

严格返回 JSON，结构如下：
{
  "zh": {"label": "12-28字中文选题标题", "summary": "一句中文编辑摘要", "tags": ["标签1", "标签2"], "groups": ["查询组译名"]},
  "en": {"label": "English editorial title", "summary": "One-sentence English editorial summary", "tags": ["tag"], "groups": ["Translated query group"]},
  "id": {"label": "Judul editorial Bahasa Indonesia", "summary": "Ringkasan editorial satu kalimat", "tags": ["tag"], "groups": ["Terjemahan grup kueri"]}
}

要求：
- label 清楚写出主体和动作，不加句号；英文/印尼语最多 14 个词。
- summary 只写 1 句、最多 42 个词；不要写“该帖称”之类的来源提示。
- tags 给 2-5 个可供编辑筛选的语义标签；翻译普通词，但不要翻译专名/代码。
- groups 必须逐一翻译输入的查询组（输入为空则返回 []）。
- 中文使用行业通行译名：RBI=印度央行，OJK=印尼金融管理局，SBP=巴基斯坦央行，
  BI=印尼央行，rupee=卢比，rupiah=印尼盾。
"""


def _text(topic: dict) -> str:
    return " ".join(clean_text(topic["lead"].get("text", "")).split())


def _fallback(topic: dict) -> dict:
    """接口不可用时仍提供结构完整的三语数据。"""
    category = (topic.get("category") or {}).get("name", "其他")
    source = _text(topic)
    head = re.split(r"(?<=[.!?。！？])\s", source)[0][:110].rstrip(" ,，、")
    groups = [str(x) for x in (topic.get("groups") or [])]
    tags = [str(x) for x in (topic.get("key_entities") or [])[:5]]
    zh = (topic.get("label") or "").strip() or (f"[{category}] {head}" if head else f"[{category}] 未命名话题")
    return {
        "zh": {"label": zh, "summary": head or zh, "tags": tags, "groups": groups},
        # 英文/印尼语回落为原始证据文本，而不是把中文标题误展示给海外同事。
        "en": {"label": head or "Untitled topic", "summary": head or "", "tags": tags, "groups": groups},
        "id": {"label": head or "Topik tanpa judul", "summary": head or "", "tags": tags, "groups": groups},
    }


def _clean_locale(value: object, fallback: dict) -> dict:
    """清理模型输出，避免单条异常破坏每日榜单。"""
    raw = value if isinstance(value, dict) else {}
    result = {}
    for lang in LANGS:
        candidate = raw.get(lang) if isinstance(raw.get(lang), dict) else {}
        fb = fallback[lang]
        label = re.sub(r"^[\s\d.、]+", "", str(candidate.get("label") or fb["label"])).strip(" 。.，,")
        summary = str(candidate.get("summary") or fb["summary"]).strip()
        tags = candidate.get("tags") if isinstance(candidate.get("tags"), list) else fb["tags"]
        groups = candidate.get("groups") if isinstance(candidate.get("groups"), list) else fb["groups"]
        result[lang] = {
            "label": label[:160],
            "summary": summary[:360],
            "tags": [str(x).strip()[:48] for x in tags if str(x).strip()][:5],
            "groups": [str(x).strip()[:100] for x in groups if str(x).strip()][:8],
        }
    return result


def label_topics(topics: list[dict], workers: int = 4) -> int:
    """写入 ``i18n`` 聚合层，并保留旧 ``label`` 供 Markdown 报告兼容。

    每个话题只请求一次，让模型同时返回三种语言；比三次独立翻译更一致，也不
    会把日更的模型调用量放大三倍。
    """
    if not topics:
        return 0

    for topic in topics:
        fallback = _fallback(topic)
        topic["i18n"] = fallback
        topic["label"] = fallback["zh"]["label"]
        topic["label_by"] = "rule"

    try:
        cfg = _load_env()
        client = OpenAI(api_key=cfg["key"], base_url=cfg["base"])
    except RuntimeError:
        return 0

    def one(topic: dict) -> bool:
        fallback = topic["i18n"]
        payload = {
            "category": (topic.get("category") or {}).get("name", "其他"),
            "query_groups": topic.get("groups") or [],
            "entity_hints": topic.get("key_entities") or [],
            "source_post": _text(topic)[:900],
        }
        try:
            response = client.chat.completions.create(
                model=cfg["flash_model"],
                max_tokens=6000,
                temperature=0.15,
                reasoning_effort="minimal",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                timeout=90,
            )
            raw = response.choices[0].message.content or ""
            localized = _clean_locale(json.loads(_strip_fence(raw)), fallback)
        except Exception:
            return False
        if not all(len(localized[lang]["label"]) >= 4 for lang in LANGS):
            return False
        topic["i18n"] = localized
        topic["label"] = localized["zh"]["label"]
        topic["label_by"] = "llm"
        return True

    with ThreadPoolExecutor(max_workers=min(workers, len(topics))) as pool:
        return sum(pool.map(one, topics))
