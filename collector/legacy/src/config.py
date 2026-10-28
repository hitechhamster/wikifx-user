"""配置加载：公共 base.yaml + 地区 regions/<name>.yaml 合并。"""
from __future__ import annotations

from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
REGION_DIR = CONFIG_DIR / "regions"


def list_regions() -> list[str]:
    """返回所有可用地区名。"""
    return sorted(p.stem for p in REGION_DIR.glob("*.yaml"))


def _merge(base: dict, override: dict) -> dict:
    """递归合并：字典逐键深合并，其余类型（含列表）由 override 直接替换。"""
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(region: str) -> dict:
    """加载并合并某地区的完整配置。

    合并规则：
      - 同名字段以地区配置为准（列表整体替换，避免继承到不相干的关键词）
      - 唯独 noise_patterns / signal_boost_patterns 走 *_extra 追加，
        这样地区配置只写本地话术，不必抄一遍公共规则
    """
    base_path = CONFIG_DIR / "base.yaml"
    region_path = REGION_DIR / f"{region}.yaml"
    if not region_path.exists():
        raise FileNotFoundError(
            f"没有地区配置 {region!r}，可选：{', '.join(list_regions())}"
        )

    cfg = _merge(
        yaml.safe_load(base_path.read_text(encoding="utf-8")) or {},
        yaml.safe_load(region_path.read_text(encoding="utf-8")) or {},
    )

    for key in ("noise_patterns", "signal_boost_patterns"):
        extra = cfg.pop(f"{key}_extra", None)
        if extra:
            cfg[key] = list(cfg.get(key, [])) + list(extra)

    cfg.setdefault("region", {}).setdefault("name", region)
    cfg["region"].setdefault("display", region)
    return cfg
