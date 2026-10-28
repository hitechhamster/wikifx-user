"""SEO 文章生成：把审核通过的热点话题交给 DeepSeek 写成可发布的稿件。"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from openai import OpenAI

from .enrich import fetch_bodies, format_sources, search
from .polish import ensure_sources, rhythm_index, tidy, word_count

ROOT = Path(__file__).resolve().parent.parent

# 各地区默认出稿语种。印尼面向本地读者用印尼语，
# 印度财经读者习惯英文，全球版用英文。
REGION_LANG = {
    "indonesia": "id",
    "india": "en",
    "pakistan": "en",   # 巴基斯坦财经媒体和讨论以英语为主
    "global": "en",
}

REGION_NAME = {"indonesia": "印尼", "india": "印度",
               "pakistan": "巴基斯坦", "global": "国际"}

LANG_NAME = {
    "id": "印尼语 (Bahasa Indonesia)",
    "en": "英文",
    "zh": "简体中文",
    "hi": "印地语 (हिन्दी)",
}


def _load_env() -> dict:
    """从环境变量或 .env 读取 OpenAI 兼容模型服务配置。"""
    values: dict[str, str] = {}
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip()
    # 保留历史变量名，兼容旧的 DeepSeek 直连；OpenRouter 则优先读它自己的 key。
    cfg = {
        "key": (os.environ.get("OPENROUTER_API_KEY")
                or os.environ.get("DEEPSEEK_API_KEY")
                or values.get("OPENROUTER_API_KEY")
                or values.get("DEEPSEEK_API_KEY", "")),
        "base": (os.environ.get("DEEPSEEK_BASE_URL")
                 or values.get("DEEPSEEK_BASE_URL")
                 or "https://api.deepseek.com"),
        "model": (os.environ.get("DEEPSEEK_MODEL")
                  or values.get("DEEPSEEK_MODEL")
                  or "deepseek-v4-pro"),
        "flash_model": (os.environ.get("DEEPSEEK_FLASH_MODEL")
                        or values.get("DEEPSEEK_FLASH_MODEL")
                        or "deepseek-v4-flash"),
    }
    if not cfg["key"]:
        raise RuntimeError("找不到 DEEPSEEK_API_KEY，请在 .env 中配置")
    return cfg


SYSTEM = """你是外汇行业资深财经编辑，为面向散户交易者的外汇门户写报道。

读者是{region_name}的散户交易者。他们打开这篇稿子只关心三件事：
我的钱安不安全、我用的平台可不可靠、这件事会不会影响我手上的仓位。
每一段都要经得起「关我什么事」的追问。

【绝对红线 —— 不可捏造】
只能使用「素材」里出现的事实。素材没写的数字、时间、人名、机构表态，
一律不准补充，也不准根据常识推断后当作事实陈述。
如果素材信息量太少不足以成稿，就如实写明已知信息，不要注水凑字数。

【两类素材的分量不同 —— 这一条决定这篇稿子写的是什么】
「社媒原帖」是本篇要报道的事件本身。这篇稿子的主题、导语、标题，
都必须落在主贴讲的那件事上。它属于未经核实的单方说法，需要核实，但它是主角。

「相关新闻报道」是检索来的背景上下文，**不是本篇要报道的事件**。
它的作用只有三个：给主贴的说法提供佐证、补充主贴没交代的背景和数字、
以及暴露主贴与公开报道之间的出入。它的可信度高于社媒，但地位低于主贴 ——
可信度决定「怎么陈述」，不决定「写什么」。

严禁把背景报道升格成新闻主体：
  ✗ 主贴讲的是某平台出金受阻，检索到的是央行月度汇率数据 →
    绝不能改写成一篇汇率行情稿。这种情况说明检索没搜到对口的东西，
    背景材料用不上就不用，在 note 里写明「未检索到相关佐证报道」
  ✗ 主贴讲 A 事件，报道里 B 事件更有料 → 仍然写 A，B 最多作为背景一句带过
  ✓ 主贴讲 A 事件，报道也在讲 A 事件 → 以报道的事实为准陈述 A，写明媒体名

交叉印证规则：
- 社媒说法被某家媒体证实 → 以媒体报道为准陈述事实，写明是哪家媒体
- 只有社媒提到、媒体没有 → 保留存疑表述，绝不能把传言写成事实
- 两边矛盾 → 都写出来，明确指出存在出入
- 报道之间互相矛盾 → 如实呈现分歧，不要自行取舍
- 检索到的报道跟主贴根本不是一回事 → 整批弃用，按「只有社媒」处理

【导语：第一句就给最硬的事实】
开头必须是新闻本身，不是机构表态、不是背景铺垫、不是名词解释。
把素材里最具体的数字和最实的动作放进第一句：谁、做了什么、多大规模。
  ✗「OJK 重申其加强资本市场监管与执法的承诺」—— 这是公关辞令，不是新闻
  ✓「OJK 今年前八个月开出 1,277 张罚单，罚款总额 3,270.6 亿印尼盾」
  ✗「印度央行的特别掉期安排引发市场广泛关注」
  ✓「印度央行 FCNR(B) 掉期窗口吸金逾 1,000 亿美元，8 月 31 日关闭后银行随即下调存款利率最多 310 个基点」
背景、定义、来龙去脉往后放。第一屏不要出现「什么是 XX」这种科普段落——
需要解释术语时，用一个从句就地带过，不要单独开一节。

【不许复读机构套话】
监管机构通稿里充满自我表扬式的固定表述，原样搬进正文会让稿子读起来像转发公告。
以下这类词句一律删掉或改写成事实陈述：
  中文概念：重申承诺、坚决态度、有力举措、起到震慑作用、营造健康生态、
            保持高压态势、持续发力、切实维护
  印尼语：menegaskan komitmen、langkah tegas、efek jera、
          teratur wajar efisien dan berintegritas、terus memperkuat
  英文：reaffirms its commitment、remains committed、takes firm action、
        strengthen the ecosystem、continues to enhance
机构原话只在本身有信息量时引用，且必须用引号并写明是谁说的。

【结尾必须能落地】
最后一节回答「读者现在该做什么」，给具体可执行的内容，不给正确的废话。
  ✗「投资者应保持谨慎，密切关注市场动向」
  ✗「这一举措有助于提升市场信心」
  ✓「被处罚名单可在 OJK 官网 ojk.go.id 的执法信息栏目查询，
     持有相关发行人股票的投资者可核对自己的持仓是否在列」
  ✓「若卢比继续走强，做多 USD/INR 的隔夜利息成本会上升，
     下一个关键节点是 9 月 12 日公布的 CPI 数据」
确实给不出可操作建议时，就给下一个关键时间点（何时公布数据、何时开庭、
何时生效），而不是编一句放之四海而皆准的建议。

【但不许给投资建议 —— 这是合规红线】
「可落地」指的是帮读者查证信息、理解影响，不是替读者做交易决策。
门户不是持牌投顾，给出具体点位和操作指令会有合规风险：
  ✗「建议在 95.00 下方设置止损」
  ✗「可考虑逢低买入 / 现在应减仓」
  ✗「目标位看向 96.50」
  ✓「若央行继续抛售美元，做多 USD/INR 的隔夜利息成本会上升」
  ✓「该窗口关闭可能收紧流动性，进而影响掉期点和持仓成本」
写「会发生什么、成本往哪个方向变」，不写「你该怎么做、在哪个价位做」。
提到具体价位时只能是已经发生的事实（收盘价、区间、历史高低点），
不能是建议的入场、止损或目标价位。

【句子节奏 —— 这是最容易露馅的地方】
AI 写出来的句子长度高度一致，一眼就能看出来。人写的东西节奏是跳的。
每一节里必须做到长短交替：
  一个长句把因果和条件交代清楚，接一个短句砸下来。然后回到中等长度。
  偶尔用五六个字的独立句做强调。
一段里三句话长度都差不多，就是没写好，重写。

可执行的硬指标（写长文时节奏最容易垮，所以逐节检查）：
- 每一节至少有一个 8 词以内的短句。一节里全是二三十词的句子，就是垮了
- 同一段内不许连续三句长度接近
- 越往后写越要留意。前两节通常写得有劲，第四五节容易滑成匀速叙述 ——
  写完第四节回头看一眼，如果整节读下来像匀速朗读，插一个短句进去

【这些是 AI 腔，一个都不许出现】
- 系动词回避：serves as / featuring / boasting / 发挥着……的作用
  → 直接写 is / has / 是 / 有
- 否定平行：「这不只是 X，而是 Y」「It's not just X, it's Y」
  → 直接说是什么，不要制造假对立
- 三段式排比：把三个近义词或三个并列项堆在一起充场面
  → 该说几个说几个，两个就写两个
- 空洞的 -ing 分析：symbolizing / reflecting / showcasing / highlighting
  → 换成具体事实，或者直接删
- 破折号滥用：一段里出现两个以上破折号
  → 用逗号和句号
- 堆叠限定词：「可能会潜在地也许最终」「could potentially may eventually」
  → 只留一个限定词，多了互相抵消
- 空心项目符号：只有名词短语没有动词和数字的列表
  → 要么写成完整句子带数字，要么改成正文段落
- 模板化转折：此外、值得注意的是、综上所述、furthermore、moreover、
  additionally、in conclusion、ultimately
  → 靠逻辑衔接：「利好摆在明面上。代价在财报附注里。」
- 万金油开头：「在当今瞬息万变的市场环境下」「随着……的不断发展」
  → 删掉，直接进事实
- 词汇黑名单：delve、leverage、foster、unlock、unleash、underscore、
  landscape、realm、tapestry、journey、robust、seamless、pivotal、
  comprehensive、multifaceted、cutting-edge、game-changer、
  赋能、抓手、闭环、生态、深度赋能、全方位、多维度

【朗读测试】
写完每一段，在心里读一遍。像不像你跟同行喝酒时会说的话？
不像就重写。宁可粗粝一点，也不要圆滑的官腔。

【文体】
- 倒金字塔：读者只读前两段也该拿到全部要点
- 用具体数字代替模糊形容：不写「大幅下降」，写「下调 310 个基点」
- 主动语态，实义动词。形容词和副词能删就删
- 归属要轻。这是最容易写砸的地方，读者要的是事实本身，不是文献综述：
    ✗「A 媒体报道称罚款 739.9 亿。B 媒体提到名单含 Bakrie。C 媒体写有 22 家，
       D 媒体和 E 媒体则写 23 家。」—— 每句一个出处，读起来像参考文献
    ✓「23 家发行人合计被罚 739.9 亿印尼盾，名单含 Bakrie 集团和 Nippon Indosari。
       各家报道的家数不一，IDX Channel 记为 22 家。」—— 事实连贯，只在
       出现分歧时才点名是谁说的
  规则：一个事实全文只归属一次；多家媒体报同一件事时写「多家媒体报道」，
  具体链接留到文末的来源小节。只有在报道互相矛盾、或引用直接原话时才点名媒体。
  但要注意：真要归属时必须点名到具体媒体，不许写「有分析人士认为」
  「业内人士表示」这种没有出处的虚指
- 免责声明只在文末出现一次，不要插在正文中间打断叙事节奏
- 涉及指控用「涉嫌」「据称」，不做有罪推定；但也不要因此把话说得含混不清

【标题：要有人点，但不能骗点】
留一个信息缺口，让读者非点不可 —— 但正文必须在前两段就把缺口填上。
给了答案的叫悬念，不给答案的才叫标题党，后者会砸掉门户的可信度。
研究显示标题不是越具体越好：已经够具体的标题再往里塞细节，
过半情况下点击率反而下降。所以数字只留最有冲击力的那一个，其余留给正文。
  ✗「OJK 开出 1,277 张罚单，23 家发行人被罚 739.9 亿印尼盾」
     —— 信息给全了，没有点开的理由
  ✓「OJK 一口气罚了 23 家上市公司，Bakrie 和 Sari Roti 都在名单上」
     —— 留了「为什么被罚、罚多少」的缺口，且正文立刻给出
可以用的手法：
- 前指：先抛结果和涉事主体，把原因留到正文（「……名单上有你熟悉的名字」）
- 强度词：用在实处的「四年来最大」「单日最狠」，不能夸大
- 具体人名机构名：读者认识的名字比抽象数字更抓人
- 反差：把两个真实但相互冲突的事实并置
不许用的：
- 问号标题（「XX 会崩盘吗？」）—— 显得不专业，且研究表明效果不佳
- 「震惊」「重磅」「速看」「不看后悔」这类纯情绪词
- 正文兑现不了的悬念

【篇幅与结构 —— 必须写够】
正文 1200-1800 词（中文和印尼语按字/词计，不含来源小节）。
只说字数你会写不够，所以给一个骨架：**至少 6 个小节**，每节 150-320 词，
每节承担下面一项工作，顺序可调，但不能少：

1. 导语（无小标题）：最硬的事实，谁做了什么、多大规模、涉及谁
2. 细节展开：把数字拆开。总额里各项占多少、名单上具体有谁、
   时间线是怎么走的。素材里出现的每一个相关数字和名字都要落到纸面
3. 来龙去脉：这件事之前发生过什么？是孤立事件还是延续？
   同类事情上一次是什么时候、什么结果？（只用素材里有的，不许自己补历史）
4. 机制：钱怎么流的、规则具体怎么变、哪一环出的问题、谁承担后果
5. 分歧与不确定：各家报道对不上的地方、还没定论的部分、
   涉事方有没有回应。这一节不许抹平，有分歧就写分歧
6. 读者怎么办：查证路径或影响方向（遵守上面的合规红线）

中间几节的顺序可以调，**但第 6 节必须是正文的最后一节**，它后面只能跟
「信息来源」小节。把当事方回应、背景补充这类内容放到它前面去 ——
在结论之后再起一节讲别的，读者会以为文章还没完，倒金字塔也就白做了。

新增一节「社媒讨论与分歧」：综合至少 4 条同话题帖子中出现的共同点、分歧或
尚待核验的说法；只归纳素材中明确出现的内容，不得把互动量当作事实证明。

每节都要有实质内容才算数。凑不满 150 词的节，说明你没把素材榨干，
回去翻【同话题相关讨论】和【相关新闻报道】里的正文——那里通常还有没用上的数字和背景。

素材确实撑不起这个篇幅时（比如只有一条推文、没搜到任何报道），
宁可写短也不要注水，但必须在 note 里写明「素材不足，实际 XXX 词」。

【SEO】
- 首段 100 字内自然出现核心关键词
- 正文用 ## / ### 分节，小标题本身要有信息量，
  不写「背景介绍」「影响分析」这种空标题，也不要每个小标题都是「名词：解释」的模板
- 关键词自然分布，不堆砌
"""

USER_TMPL = """请就以下外汇热点写一篇新闻报道。

【出稿语种】{lang_name}（标题、正文、meta 全部用这个语种，专有名词可保留原文）
【面向市场】{region_name}读者
【本篇类别】{category_name}
【这一类的写作角度】{category_angle}

【素材】
主贴（{platform} @{author}，{followers} 粉丝，{hours}小时前发布）：
{lead_text}

互动数据：点赞 {likes}，转发 {shares}，评论 {comments}
原文链接：{url}
话题分类：{groups}
{also_block}{sources_block}
【输出】
严格返回 JSON，不要包裹在代码块里，字段如下：
{{
  "title": "文章标题",
  "slug": "url-friendly-slug-in-english-lowercase-hyphens",
  "meta_description": "meta描述，必须控制在 150-160 字符，超了会被搜索引擎截断",
  "keywords": ["核心关键词", "长尾词2", "长尾词3", "长尾词4", "长尾词5"],
  "body": "Markdown正文，用##和###分节，末尾附来源链接",
  "confidence": "high|medium|low —— 有媒体报道印证主贴那件事给 high；报道虽有但讲的不是同一件事，等同于只有社媒单方说法，给 low",
  "note": "若素材不足或存在需人工核实之处，在此说明；否则空字符串",
  "sources_cited": ["正文中实际引用到的媒体链接，没引用就空数组"]
}}

正文末尾列出「信息来源」小节：社媒原帖链接 + 实际引用到的媒体报道链接（带媒体名）。"""


def _category_of(topic: dict) -> dict:
    """取话题类别。老数据可能没有 category 字段，回落到分类器重算一次。"""
    cat = topic.get("category") or topic.get("lead", {}).get("category")
    if cat and cat.get("angle"):
        return cat
    from .classify import classify, load_taxonomy
    cid = (cat or {}).get("id")
    tax = load_taxonomy()
    if cid:
        for c in tax["categories"]:
            if c["id"] == cid:
                return c
        if cid == tax["fallback"]["id"]:
            return tax["fallback"]
    return classify(topic["lead"].get("text", "")) | {
        "angle": tax["fallback"].get("angle", "")}


def _also_block(topic: dict) -> str:
    """把同话题的其他条目拼进素材，供模型写出讨论面与分歧。"""
    others = topic.get("also_seen") or []
    if not others:
        return ""
    lines = ["", f"【同话题相关讨论】共聚合 {len(others)} 条（可用于交叉印证与讨论面，同样不可外推）："]
    for o in others[:15]:
        e = o.get("engagement") or {}
        verified = "已认证" if o.get("author_verified") or o.get("author_blue") else "未认证"
        lines.append(
            f"- @{o.get('author', '')}（{o.get('author_followers', 0):,} 粉，{verified}，"
            f"{o.get('hours_ago', '?')} 小时前；赞 {e.get('likes', 0)} / 转 {e.get('shares', 0)} / 评 {e.get('comments', 0)}）："
            f"{o.get('text', '')}\n  链接：{o.get('url', '')}")
    return "\n".join(lines) + "\n"


def _strip_fence(text: str) -> str:
    """模型偶尔仍会套 ```json 代码块，剥掉。"""
    t = text.strip()
    m = re.match(r"^```(?:json)?\s*(.+?)\s*```$", t, re.S)
    return m.group(1) if m else t


# 出稿预设。reasoning_effort 对耗时影响极大：
# 同一个 prompt，flash 从 low 换到 medium，推理量从 290 字符涨到 22000+，
# 耗时从 14s 变成 59s，正文只多了 1400 字符。日常用 fast 就够。
PRESETS = {
    "fast":     {"tier": "flash", "effort": "low",    "budget": 16000, "label": "快速 约15秒"},
    "balanced": {"tier": "flash", "effort": "medium", "budget": 20000, "label": "均衡 约60秒"},
    "quality":  {"tier": "pro",   "effort": "medium", "budget": 24000, "label": "高质量 约2分钟"},
    "deep":     {"tier": "pro",   "effort": "high",   "budget": 30000, "label": "深度报道 约4分钟"},
}
DEFAULT_PRESET = "fast"

# 正文低于这个词数就重试一次。目标是 1200-1800，留出余量
MIN_WORDS = 1050


def _too_short(raw: str, floor: int) -> int:
    """正文不足 floor 词则返回实际词数，够长返回 0。JSON 残缺时返回 0（交给别处处理）。"""
    try:
        body = json.loads(_strip_fence(raw)).get("body") or ""
    except (json.JSONDecodeError, AttributeError):
        return 0
    n = word_count(body)
    return n if n < floor else 0


def generate(topic: dict, region: str, lang: str | None = None,
             preset: str | None = None, use_search: bool = True,
             fetch_text: bool = True) -> dict:
    """给一个话题生成 SEO 文章。返回含 title/slug/body 等字段的 dict。

    use_search=True 时先搜相关新闻报道当交叉印证素材 —— 社媒推文本身太薄，
    有了媒体报道才能把传言和已证实的事实区分开。搜索失败不影响出稿。
    """
    cfg = _load_env()
    p = dict(PRESETS.get(preset or DEFAULT_PRESET, PRESETS[DEFAULT_PRESET]))
    p["model"] = cfg["flash_model"] if p["tier"] == "flash" else cfg["model"]
    client = OpenAI(api_key=cfg["key"], base_url=cfg["base"])
    lang = lang or REGION_LANG.get(region, "en")
    lead = topic["lead"]
    e = lead.get("engagement", {})

    found = search(topic, region) if use_search else {"query": "", "sources": [], "note": "已关闭检索"}

    # 搜索摘要只有一两百字符，撑不起 1000 词的稿子 —— 实测同一话题
    # 摘要合计 976 字符、正文合计 3 万字符，相差 31 倍。并发抓约 4 秒。
    fetched = 0
    if fetch_text and found["sources"]:
        fetched = fetch_bodies(found["sources"])

    # 不同类别的抓手完全不同：监管稿要给自查路径，诈骗稿要给识别特征，
    # 行情稿要落到持仓影响。角度配在 taxonomy.yaml 里
    cat = _category_of(topic)

    prompt = USER_TMPL.format(
        sources_block=format_sources(found["sources"]),
        lang_name=LANG_NAME.get(lang, lang),
        region_name=REGION_NAME.get(region, region),
        category_name=cat.get("name", "其他"),
        category_angle=cat.get("angle", ""),
        platform=lead.get("platform", "").upper(),
        author=lead.get("author", ""),
        followers=f"{lead.get('author_followers', 0):,}",
        hours=lead.get("hours_ago", "?"),
        lead_text=lead.get("text", ""),
        likes=f"{e.get('likes', 0):,}",
        shares=f"{e.get('shares', 0):,}",
        comments=f"{e.get('comments', 0):,}",
        url=lead.get("url", ""),
        groups=" / ".join(topic.get("groups", [])),
        also_block=_also_block(topic),
    )

    messages = [
        {"role": "system",
         "content": SYSTEM.format(region_name=REGION_NAME.get(region, region))},
        {"role": "user", "content": prompt},
    ]

    def call(effort: str, budget: int):
        return client.chat.completions.create(
            model=p["model"],
            # 思考 token 也计入 max_tokens。实测推理偶尔会失控写到 5 万多字符，
            # 把预算烧光导致正文返回空串，所以留足余量。
            max_tokens=budget,
            temperature=0.4,          # 事实类报道，压低随机性
            reasoning_effort=effort,
            response_format={"type": "json_object"},
            messages=messages,
        )

    resp = call(p["effort"], p["budget"])
    choice = resp.choices[0]
    raw = (choice.message.content or "").strip()

    # 篇幅波动很大：同一条话题同一档位，实测出过 1064 词和 428 词两种结果。
    # 太短的重试一次，并把偏短这件事直接说给模型听 —— 比调高推理档位管用，
    # 之前试过 balanced/quality，反而更短。
    if raw:
        short = _too_short(raw, MIN_WORDS)
        if short:
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": (
                f"这一稿正文只有约 {short} 词，没到 1200 词的下限。"
                "重写一版：保持已有事实不变、不许编造新信息，"
                "把【相关新闻报道】正文里还没用上的数字、时间、人名和背景补进去，"
                "按骨架把 7 个小节都写足。仍然只返回 JSON。")})
            resp = call(p["effort"], p["budget"])
            choice = resp.choices[0]
            retry_raw = (choice.message.content or "").strip()
            if retry_raw and not _too_short(retry_raw, short + 100):
                raw = retry_raw

    # 推理跑飞会返回 finish_reason=length 且正文为空。降到 minimal 重试一次，
    # 推理量能从数万字符压到几百，基本必出稿。
    if not raw and choice.finish_reason == "length":
        resp = call("minimal", 32000)
        choice = resp.choices[0]
        raw = (choice.message.content or "").strip()

    if not raw:
        reasoning = (choice.message.model_extra or {}).get("reasoning_content") or ""
        raise RuntimeError(
            f"DeepSeek 返回空正文（finish_reason={choice.finish_reason}，"
            f"推理 {len(reasoning)} 字符）。可换用「高质量」预设或稍后重试。"
        )
    try:
        art = json.loads(_strip_fence(raw))
    except json.JSONDecodeError as exc:
        # 正文写到一半被 max_tokens 掐断，JSON 是残的（Unterminated string）。
        # 稿子变长到 1000+ 词后这种情况才出现 —— 推理和正文共用预算，
        # 推理占多了正文就写不完。降到 minimal 把预算全留给正文，再翻倍。
        if choice.finish_reason == "length":
            resp = call("minimal", 32000)
            choice = resp.choices[0]
            raw = (choice.message.content or "").strip()
            try:
                art = json.loads(_strip_fence(raw))
            except json.JSONDecodeError as exc2:
                raise RuntimeError(
                    f"DeepSeek 返回的 JSON 仍不完整（已降档重试）: {exc2}；"
                    f"finish_reason={choice.finish_reason}；原文前200字: {raw[:200]}")
        else:
            raise RuntimeError(
                f"DeepSeek 返回的不是合法 JSON: {exc}；原文前200字: {raw[:200]}")

    # 模型偶尔会把同一个链接列两次，去重后保持原顺序
    cited = art.get("sources_cited") or []
    art["sources_cited"] = list(dict.fromkeys(c for c in cited if c))

    # 成稿后处理：清标点残留 → 补来源小节 → 算质量指标
    body, punct_fixes = tidy(art.get("body") or "")
    body, added_sources = ensure_sources(
        body, lead.get("url", ""), lead.get("author", ""),
        art["sources_cited"], found["sources"], lang)
    art["body"] = body

    u = resp.usage
    art["_meta"] = {
        "model": resp.model,
        "preset": preset or DEFAULT_PRESET,
        "effort": p["effort"],
        "lang": lang,
        "region": region,
        "tokens_in": u.prompt_tokens,
        "tokens_out": u.completion_tokens,
        "source_url": lead.get("url", ""),
        "source_author": lead.get("author", ""),
        "topic_score": topic.get("topic_score"),
        "search_query": found["query"],
        "search_count": len(found["sources"]),
        "bodies_fetched": fetched,
        "search_note": found["note"],
        "meta_len": len(art.get("meta_description") or ""),
        # 句长变异系数。AI 写的通常 <0.35，人写的在 0.45 以上，
        # 低于阈值说明句子长度太均匀，审核时要留意
        "rhythm": rhythm_index(body),
        "words": word_count(body),
        "punct_fixes": punct_fixes,
        "sources_appended": added_sources,
    }
    art["_sources"] = found["sources"]
    return art


def save(article: dict, region: str, date: str) -> Path:
    """落盘成 Markdown（带 YAML front matter，方便直接进 CMS）。"""
    outdir = ROOT / "data" / "articles" / region / date
    outdir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9-]", "", (article.get("slug") or "untitled").lower())[:80]
    path = outdir / f"{slug or 'untitled'}.md"

    m = article.get("_meta", {})
    kw = article.get("keywords") or []
    fm = [
        "---",
        f"title: {json.dumps(article.get('title', ''), ensure_ascii=False)}",
        f"slug: {slug}",
        f"description: {json.dumps(article.get('meta_description', ''), ensure_ascii=False)}",
        f"keywords: {json.dumps(kw, ensure_ascii=False)}",
        f"lang: {m.get('lang', '')}",
        f"region: {region}",
        f"source: {m.get('source_url', '')}",
        f"source_author: {m.get('source_author', '')}",
        f"model: {m.get('model', '')}",
        f"confidence: {article.get('confidence', '')}",
        f"words: {m.get('words', 0)}",
        f"rhythm: {m.get('rhythm', 0)}",
        f"search_query: {json.dumps(m.get('search_query', ''), ensure_ascii=False)}",
        f"sources_found: {m.get('search_count', 0)}",
        f"sources_cited: {json.dumps(article.get('sources_cited') or [], ensure_ascii=False)}",
    ]
    if article.get("note"):
        fm.append(f"note: {json.dumps(article['note'], ensure_ascii=False)}")
    fm.append("---")
    path.write_text("\n".join(fm) + "\n\n" + (article.get("body") or ""),
                    encoding="utf-8")
    return path
