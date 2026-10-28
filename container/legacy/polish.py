"""成稿后处理：清标点残留、算节奏指数。

模型偶尔会拼出「句号紧跟破折号」这类畸形标点（实测出现过
"menjual aset.— atau lebih tepatnya"）。这类东西在正文里很扎眼，
但让模型自己避免不可靠，用规则清一遍更省事。
"""
from __future__ import annotations

import re
import statistics as st

# 每条是 (模式, 替换)。只处理明确是残留的组合，不动正常标点
_FIXES: list[tuple[re.Pattern, str]] = [
    # 句末标点后紧跟破折号 —— 二者取破折号，它才是作者本意的转折
    (re.compile(r"[.。,，;；]\s*(—|――|--)"), r" \1"),
    # 破折号后紧跟句末标点
    (re.compile(r"(—|――)\s*[.。,，]"), r"\1"),
    # 重复标点
    (re.compile(r"([,，;；:：])\1+"), r"\1"),
    (re.compile(r"\.{4,}"), "..."),
    (re.compile(r"。{2,}"), "。"),
    # 标点前的空格（中英文都不该有）
    (re.compile(r"\s+([,.;:!?，。；：！？、])"), r"\1"),
    # 中文标点后多余空格
    (re.compile(r"([，。；：！？、])\s+"), r"\1"),
    # 连续空格和行尾空白
    (re.compile(r"[ \t]{2,}"), " "),
    (re.compile(r"[ \t]+$", re.M), ""),
    # 三个以上连续空行压成两个
    (re.compile(r"\n{4,}"), "\n\n\n"),
    # 括号紧贴前一个字时补空格（英文语境）
    (re.compile(r"(\w)\(([A-Z])"), r"\1 (\2"),
]


def tidy(text: str) -> tuple[str, int]:
    """清理标点残留。返回 (清理后文本, 改动处数)。"""
    if not text:
        return text, 0
    out, n = text, 0
    for pat, rep in _FIXES:
        out, k = pat.subn(rep, out)
        n += k
    return out, n


_SENT_SPLIT = re.compile(r"(?<=[.!?。！？])\s+")
_SKIP_LINE = ("#", "-", "*", ">", "|", "[")

# 来源小节的标题写法不统一：中文/印尼语稿多用 "## Sumber Informasi"，
# 英文稿常写成加粗的 "**Sources:**"。只认 ## 会漏掉后者，
# 于是整段链接被当成正文，词数虚高、句长统计也被拉偏
_SOURCE_HEAD = re.compile(
    r"\n\s*(?:#{1,6}\s*|\*\*)\s*"
    r"(?:sources?|sumber(?:\s+informasi)?|informasi\s+sumber|"
    r"referensi|信息来源|来源|参考资料)\s*[:：]?\s*\*{0,2}\s*\n",
    re.I)


def strip_sources(body: str) -> str:
    """剥掉文末的来源小节，只留正文。"""
    return _SOURCE_HEAD.split(body)[0]


def rhythm_index(body: str) -> float:
    """句长的变异系数（标准差/均值）。

    AI 写的句子长度高度一致，这个值通常低于 0.35；人写的在 0.45 以上。
    只看正文，跳过标题行、列表项和链接行 —— 它们的长度分布跟散文不是一回事。
    """
    main = re.split(r"\n#+\s*(?:Sources|Sumber|Informasi|信息来源)", body)[0]
    sents = []
    for para in main.split("\n"):
        p = para.strip()
        if not p or p.startswith(_SKIP_LINE):
            continue
        sents.extend(s for s in _SENT_SPLIT.split(p) if len(s.strip()) > 15)
    lens = [len(re.findall(r"\S+", s)) for s in sents]
    if len(lens) < 3:
        return 0.0
    mean = st.mean(lens)
    return round(st.pstdev(lens) / mean, 2) if mean else 0.0


_SOURCE_LABEL = {
    "id": ("Sumber Informasi", "Unggahan asli"),
    "en": ("Sources", "Original post"),
    "zh": ("信息来源", "社媒原帖"),
    "hi": ("Sources", "Original post"),
}


def ensure_sources(body: str, lead_url: str, lead_author: str,
                   cited: list[str], all_sources: list[dict],
                   lang: str = "en") -> tuple[str, bool]:
    """正文没有来源小节时补一个。返回 (正文, 是否补过)。

    prompt 里要求文末列出信息来源，但实测 8 篇里有 2 篇漏写 —— 引用信息只留在
    元数据里，读者看不到出处。这种确定性的东西交给代码比交给模型可靠。
    """
    if _SOURCE_HEAD.search(body):
        return body, False

    head, orig = _SOURCE_LABEL.get(lang, _SOURCE_LABEL["en"])
    by_url = {s.get("url"): s for s in (all_sources or [])}
    lines = [f"\n\n## {head}\n"]
    if lead_url:
        lines.append(f"- {orig}: [@{lead_author}]({lead_url})")
    for u in cited or []:
        if not u or u == lead_url:
            continue
        s = by_url.get(u) or {}
        name = s.get("source") or s.get("title") or u
        lines.append(f"- {name}: {u}")
    if len(lines) == 1:          # 什么都没有就不加空标题
        return body, False
    return body.rstrip() + "\n".join(lines) + "\n", True


def word_count(body: str) -> int:
    """正文词数，不含来源小节。"""
    main = re.split(r"\n#+\s*(?:Sources|Sumber|Informasi|信息来源)", body)[0]
    return len(re.findall(r"\S+", main))
