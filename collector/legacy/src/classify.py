"""内容分类：把每条内容归到八个业务类别之一。

分类是新流程的第一道工序 —— 聚类只在「同市场 + 同类别」内比对，
类别还决定搜索意图加分和编辑相关度，所以分错会一路错到底。
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from .rank import clean_text

CONFIG = Path(__file__).resolve().parent.parent / "config" / "taxonomy.yaml"


def _compile_all(patterns: list[str], where: str) -> list[re.Pattern]:
    out = []
    for p in patterns or []:
        try:
            out.append(re.compile(p, re.I))
        except re.error as e:
            print(f"  ! {where} 有无效正则 {p!r}: {e}")
    return out


@lru_cache(maxsize=1)
def load_taxonomy() -> dict:
    """读分类体系并预编译正则。正则编译不便宜，缓存住。"""
    raw = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    cats = [
        {
            **c,
            "re_strong": _compile_all(c.get("strong"), f"分类 {c['id']}.strong"),
            "re_weak": _compile_all(c.get("weak"), f"分类 {c['id']}.weak"),
        }
        for c in raw["categories"]
    ]
    return {
        "categories": cats,
        "fallback": raw["fallback"],
        "weights": raw.get("weights", {"strong": 3, "weak": 1, "min_score": 2}),
        "allegation": set(raw.get("allegation_categories", [])),
    }


def classify(text: str) -> dict:
    """返回 {id, name, search_intent, editorial, score, hits}。

    按强弱信号计分取最高，不是第一个命中就定类 —— 顺口提一句 RBI 的行情播报
    不该被判成监管，长文里出现一个"亏损"也不该被判成诈骗。
    平分时按配置里的排列顺序取前者。
    """
    tax = load_taxonomy()
    w = tax["weights"]
    body = clean_text(text)

    best, best_score, best_hits = None, 0, []
    for c in tax["categories"]:
        hits = [p.pattern[:48] for p in c["re_strong"] if p.search(body)]
        score = len(hits) * w["strong"]
        weak_hits = [p.pattern[:48] for p in c["re_weak"] if p.search(body)]
        score += len(weak_hits) * w["weak"]
        if score > best_score:          # 严格大于：平分保留先出现的类别
            best, best_score, best_hits = c, score, hits + weak_hits

    if best is None or best_score < w["min_score"]:
        f = tax["fallback"]
        return {"id": f["id"], "name": f["name"],
                "search_intent": f["search_intent"],
                "editorial": f["editorial"], "score": best_score, "hits": []}
    return {
        "id": best["id"], "name": best["name"],
        "search_intent": best["search_intent"],
        "editorial": best["editorial"],
        "score": best_score, "hits": best_hits[:3],
    }


def is_allegation(category_id: str) -> bool:
    """诈骗/出金/平台指控类。这类不能因为「负面严重」就自动升 Strong，
    必须有一手来源或多家可信媒体佐证。"""
    return category_id in load_taxonomy()["allegation"]


def classify_items(items: list[dict]) -> list[dict]:
    """给每条内容打上类别，就地写入 category 字段。"""
    for it in items:
        it["category"] = classify(it.get("text", ""))
    return items
