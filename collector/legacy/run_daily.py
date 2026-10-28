#!/usr/bin/env python
"""
外汇社媒热点 · 每日采集入口

流程：采集 → 清洗 → 分类 → 聚类 → 检索取证 → 机会分排序 → 跨市场 Top 8

用法:
    python run_daily.py                        # 跑印尼 + 印度 + 巴基斯坦
    python run_daily.py --region india         # 只跑印度
    python run_daily.py --region all           # 含全球英文圈
    python run_daily.py --hours 48             # 改时间窗
    python run_daily.py --dry-run              # 复用上次原始数据重跑，不调 Apify
    python run_daily.py --dry-run --no-search  # 再省掉 Serper 检索
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Windows 控制台默认 GBK，推文里的 emoji 会让 print 崩掉，这里强制 UTF-8 并容错
for _stream in (sys.stdout, sys.stderr):
    try:
        # line_buffering: 输出重定向到文件时 Python 默认按块缓冲，
        # 会导致后台跑的时候日志文件长时间是空的，看不到进度
        _stream.reconfigure(encoding="utf-8", errors="replace",
                            line_buffering=True)
    except (AttributeError, ValueError):
        pass

from src.apify import Apify
from src.classify import classify_items
from src.collect import collect_all
from src.config import list_regions, load_config
from src.opportunity import attach_evidence, pick_top_board, score_topics
from src.rank import cluster, dedup, filter_noise, score_items
from src.report import write_reports, write_top_board
from src.topic_label import label_topics

ROOT = Path(__file__).resolve().parent
DEFAULT_REGIONS = ["indonesia", "india", "pakistan"]


def resolve_regions(arg: str | None) -> list[str]:
    available = list_regions()
    if not arg:
        return [r for r in DEFAULT_REGIONS if r in available]
    if arg.strip().lower() == "all":
        return available
    picked = [r.strip() for r in arg.split(",") if r.strip()]
    unknown = [r for r in picked if r not in available]
    if unknown:
        raise SystemExit(
            f"! 未知地区 {', '.join(unknown)}，可选：{', '.join(available)}"
        )
    return picked


def run_region(region: str, args, api: Apify | None) -> dict | None:
    """跑单个地区，返回结果摘要；失败返回 None。"""
    cfg = load_config(region)
    if args.hours:
        cfg["run"]["lookback_hours"] = args.hours
    if args.top:
        cfg["run"]["top_n"] = args.top

    disp = cfg["region"]["display"]
    raw_dir = ROOT / "data" / "raw" / region
    daily_dir = ROOT / "data" / "daily" / region
    date = datetime.now().strftime("%Y-%m-%d")

    print(f"\n{'─' * 62}\n▶ {disp}（{region}）\n{'─' * 62}")

    # --- 1 采集 ---
    if args.dry_run:
        files = sorted(raw_dir.glob("*.json"))
        if not files:
            print(f"  ! {disp} 没有历史原始数据，跳过（先跑一次正常采集）")
            return None
        raw = json.loads(files[-1].read_text(encoding="utf-8"))
        print(f"  [1/6] 复用 {files[-1].name}：{len(raw)} 条（未调用 Apify）")
    else:
        print("  [1/6] 采集中…")
        raw = collect_all(api, cfg)
        raw_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        (raw_dir / f"{stamp}.json").write_text(
            json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"    共 {len(raw)} 条")

    if not raw:
        print(f"  ! {disp} 没采到数据，检查 config/regions/{region}.yaml")
        return None

    # --- 2 清洗 ---
    print("  [2/6] 去重 + 噪音过滤…")
    deduped = dedup(raw)
    kept, dropped = filter_noise(deduped, cfg)
    print(f"    去重 {len(raw)} → {len(deduped)}")
    for reason, n in dropped.items():
        if n:
            print(f"    剔除[{reason}] {n} 条")
    print(f"    保留 {len(kept)} 条（信噪比 {len(kept) / len(raw) * 100:.0f}%）")
    if not kept:
        print(f"  ! {disp} 全部被过滤，建议放宽 scoring 门槛")
        return None

    # --- 3 分类 ---
    print("  [3/6] 内容分类…")
    classify_items(kept)
    cat_count: dict[str, int] = {}
    for x in kept:
        cat_count[x["category"]["name"]] = cat_count.get(x["category"]["name"], 0) + 1
    print("    " + "  ".join(f"{k} {v}" for k, v in
                             sorted(cat_count.items(), key=lambda kv: -kv[1])))

    # --- 4 聚类 ---
    print("  [4/6] 打分 + 同类别聚类…")
    scored = [x for x in score_items(kept, cfg)
              if x["score"] >= cfg["scoring"].get("min_score", 0)]
    topics = cluster(scored, cfg)
    print(f"    {len(scored)} 条 → {len(topics)} 个话题")
    if not topics:
        print(f"  ! {disp} 没有话题，建议调低 scoring.min_score")
        return None

    # --- 5 检索取证 ---
    limit = 0 if args.no_search else cfg["opportunity"].get("search_top_n", 25)
    print(f"  [5/6] 检索取证（前 {limit} 个话题）…" if limit
          else "  [5/6] 检索已关闭，证据仅按发布者判定")
    searched = attach_evidence(topics, cfg, region, limit=limit)
    solid = sum(1 for t in topics
                if t["evidence"]["first_party"] or t["evidence"]["trusted_count"] >= 2)
    print(f"    检索 {searched} 次，{solid} 个话题证据达标")

    # --- 6 机会分排序 ---
    print("  [6/7] 机会分排序…")
    topics = score_topics(topics, cfg)
    scores = [t["opportunity"]["score"] for t in topics]
    topic_cats: dict[str, int] = {}
    for t in topics:
        n = t["category"].get("name", "其他")
        topic_cats[n] = topic_cats.get(n, 0) + 1
    topic_cats = dict(sorted(topic_cats.items(), key=lambda kv: -kv[1]))
    print(f"    {len(topics)} 个话题　最高 {max(scores):.1f}"
          f"　中位 {scores[len(scores) // 2]:.1f}　最低 {min(scores):.1f}")
    print("    话题类别：" + "  ".join(f"{k} {v}" for k, v in topic_cats.items()))

    # --- 7 话题命名 ---
    # 只给会进榜的那些起名，后面的没人看，白花时间
    named_n = cfg["run"]["top_n"]
    print(f"  [7/7] 给前 {named_n} 个话题起中文名…")
    ok = label_topics(topics[:named_n])
    for t in topics[named_n:]:
        t.setdefault("label", "")
        t.setdefault("label_by", "")
    print(f"    AI 命名 {ok}/{min(named_n, len(topics))}，其余用规则兜底")

    meta = {
        "region": region,
        "region_display": disp,
        "lookback_hours": cfg["run"]["lookback_hours"],
        "top_n": cfg["run"]["top_n"],
        "raw_count": len(raw),
        "kept_count": len(kept),
        "topic_count": len(topics),
        "category_counts": topic_cats,
        "item_category_counts": cat_count,
        "searched": searched,
        "labeled": ok,
        "cost_usd": 0.0,   # 全部地区跑完后统一结算
    }
    res = write_reports(topics, meta, daily_dir, date)
    print(f"    → {res['md'].relative_to(ROOT)}")

    return {"region": region, "display": disp, "topics": topics, "cfg": cfg,
            "meta": meta, "paths": res, "date": date, "daily_dir": daily_dir}


def main() -> int:
    ap = argparse.ArgumentParser(description="外汇社媒热点采集（分地区）")
    ap.add_argument("--region", help="地区名，逗号分隔，或 all。默认印尼,印度,巴基斯坦")
    ap.add_argument("--hours", type=int, help="回溯小时数，覆盖配置")
    ap.add_argument("--top", type=int, help="每地区榜单条数，覆盖配置")
    ap.add_argument("--dry-run", action="store_true", help="复用上次原始数据，不调 Apify")
    ap.add_argument("--no-search", action="store_true", help="跳过 Serper 检索取证")
    args = ap.parse_args()

    regions = resolve_regions(args.region)
    if not regions:
        print("! 没有可跑的地区，检查 config/regions/ 目录")
        return 1

    date = datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'=' * 62}")
    print(f"外汇社媒热点采集 · {date}")
    print(f"本次地区：{'、'.join(regions)}")
    print("=" * 62)

    api = None
    if not args.dry_run:
        api = Apify()
        usage = api.account_usage()
        if usage:
            left = usage["limit"] - usage["used"]
            print(f"账户余额 ${left:.2f} / ${usage['limit']}"
                  f"（周期至 {usage['cycle_end']}）")
            need = load_config(regions[0])["run"].get("max_cost_usd", 0.5)
            if left < need * len(regions):
                print(f"! 余额不足以跑 {len(regions)} 个地区，中止")
                return 1

    results = [r for r in (run_region(r, args, api) for r in regions) if r]
    if not results:
        return 1

    # --- 跨市场 Top 8 ---
    print(f"\n{'─' * 62}\n▶ 跨市场 Top 8\n{'─' * 62}")
    base_cfg = results[0]["cfg"]
    by_region = {r["region"]: r["topics"] for r in results}

    # 只跑了部分地区时，其余地区读当天已有的榜单一起参与汇总 ——
    # 否则补跑一个市场就会把跨市场榜整个覆盖成那个市场的专榜
    for m in base_cfg["top_board"]["markets"]:
        if m in by_region:
            continue
        f = ROOT / "data" / "daily" / m / f"{date}.json"
        if not f.exists():
            continue
        try:
            saved = json.loads(f.read_text(encoding="utf-8")).get("topics", [])
        except (json.JSONDecodeError, OSError) as e:
            print(f"  ! 读 {m} 当天榜单失败，跳过：{e}")
            continue
        if saved:
            by_region[m] = saved
            print(f"  · 复用 {m} 当天已有的 {len(saved)} 个话题")

    board = pick_top_board(by_region, base_cfg)
    board_path = write_top_board(board, date, ROOT / "data" / "daily" / "_board",
                                 base_cfg)
    print(f"  选出 {len(board)} 条 → {board_path.relative_to(ROOT)}")

    # 成本统一结算后回写各地区报告
    cost = api.settle_cost() if api else 0.0
    if cost:
        share = cost / len(results)
        for r in results:
            r["meta"]["cost_usd"] = round(share, 4)
            write_reports(r["topics"], r["meta"], r["daily_dir"], r["date"])

    # Additive persistence: reports remain authoritative and unchanged.
    # A database failure must never turn a successful collection into a failed run.
    try:
        from src.content_store import import_daily
        for report_date in sorted({r["date"] for r in results}):
            counts = import_daily(ROOT / "data", report_date)
            print(f"  SQLite content import: {counts}")
    except Exception as exc:
        print(f"  ! SQLite content import failed ({type(exc).__name__}); reports preserved; rerun tools/import_content.py")

    print(f"\n{'=' * 62}\n汇总\n{'=' * 62}")
    for r in results:
        m = r["meta"]
        print(f"  {r['display']:<8} 原始{m['raw_count']:>4} → 保留{m['kept_count']:>4}"
              f" → 话题{m['topic_count']:>3}"
              f"　{'  '.join(f'{k}{v}' for k, v in m['category_counts'].items())}")
    print(f"\n  Top {len(board)}：")
    for t in board:
        o = t["opportunity"]
        # board 里混着两种结构：本次跑的是原始话题（有 members），
        # 从磁盘复用的是已拍平的 payload（有 stats）
        st = t.get("stats") or {}
        mem = t.get("members")
        n_author = (st.get("author_count") if st
                    else len({m.get("author", "") for m in mem}) if mem else "-")
        n_post = (st.get("post_count") if st
                  else len(mem) if mem else "-")
        txt = " ".join(t["lead"]["text"].split())[:42]
        print(f"    {t['board_rank']}. [{o['score']:>5.1f}]"
              f" {t['region'][:9]:<9} {t['category'].get('name', ''):<7}"
              f" {n_author}号/{n_post}帖 {txt}")
    print(f"\n  本次 Apify 花费 ${cost:.4f}")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
