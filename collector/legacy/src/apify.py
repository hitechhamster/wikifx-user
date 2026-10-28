"""Apify API 轻封装：跑 actor、取数据、算成本。"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

API = "https://api.apify.com/v2"


def load_token() -> str:
    """从环境变量或 .env 读取 token。"""
    tok = os.environ.get("APIFY_TOKEN")
    if tok:
        return tok
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("APIFY_TOKEN="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("找不到 APIFY_TOKEN，请在 .env 中配置")


class Apify:
    def __init__(self, token: str | None = None):
        self.token = token or load_token()
        self.cost_usd = 0.0
        # 记录会话开始时间，结算时据此圈定本次跑了哪些 run
        self.session_start = datetime.now(timezone.utc)

    def run_actor(self, actor_id: str, payload: dict, timeout: int = 300) -> list[dict]:
        """异步跑 actor：启动 -> 轮询 -> 取数据。

        相比 run-sync 的两个好处：
          1. 超时会主动 abort，立刻停止计费，而不是干烧到 Apify 侧超时
          2. 无论 run 最终成功还是失败/超时，都把数据集里已有的条目捞回来
        失败返回空列表而不抛异常，避免单个平台拖垮整条管道。
        """
        # 1) 启动
        try:
            r = requests.post(
                f"{API}/acts/{actor_id}/runs",
                params={"token": self.token},
                json=payload,
                timeout=60,
            )
            if r.status_code >= 400:
                print(f"    ! {actor_id} 启动失败 HTTP {r.status_code}: "
                      f"{r.text[:160]}")
                return []
            run = r.json()["data"]
        except (requests.RequestException, ValueError, KeyError) as e:
            print(f"    ! {actor_id} 启动异常: {e}")
            return []

        run_id, ds_id = run["id"], run.get("defaultDatasetId")

        # 2) 轮询到终态或超时
        deadline = time.time() + timeout
        status = run.get("status", "READY")
        while time.time() < deadline:
            time.sleep(5)
            try:
                r = requests.get(
                    f"{API}/actor-runs/{run_id}",
                    params={"token": self.token},
                    timeout=30,
                )
                d = r.json()["data"]
                status = d["status"]
                ds_id = d.get("defaultDatasetId") or ds_id
            except (requests.RequestException, ValueError, KeyError):
                continue
            if status not in ("READY", "RUNNING"):
                break
        else:
            status = "TIMEOUT"

        # 3) 超时则主动中止，止损
        if status in ("READY", "RUNNING", "TIMEOUT"):
            try:
                requests.post(
                    f"{API}/actor-runs/{run_id}/abort",
                    params={"token": self.token},
                    timeout=30,
                )
                print(f"    ! {actor_id} 超时({timeout}s)，已中止并抢救已抓数据")
            except requests.RequestException:
                pass
        elif status != "SUCCEEDED":
            print(f"    ! {actor_id} 结束状态 {status}，尝试抢救已抓数据")

        # 4) 不管什么状态，都把数据集里已有的取回来
        if not ds_id:
            return []
        try:
            r = requests.get(
                f"{API}/datasets/{ds_id}/items",
                params={"token": self.token, "format": "json"},
                timeout=120,
            )
            data = r.json()
        except (requests.RequestException, ValueError):
            print(f"    ! {actor_id} 读取数据集失败")
            return []
        return data if isinstance(data, list) else []

    def settle_cost(self) -> float:
        """结算本次会话的实际花费。

        按会话开始时间圈定 run（响应头里拿不到 run id，改用时间窗更可靠）。
        Apify 计费有几秒延迟，所以重试几次。
        """
        total, counted = 0.0, 0
        for attempt in range(4):
            total, counted = 0.0, 0
            try:
                r = requests.get(
                    f"{API}/actor-runs",
                    params={"token": self.token, "limit": 50, "desc": "true"},
                    timeout=30,
                )
                for run in r.json()["data"]["items"]:
                    started = run.get("startedAt")
                    if not started:
                        continue
                    dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                    if dt < self.session_start:
                        break  # 已按时间倒序，更早的不用看了
                    total += float(run.get("usageTotalUsd") or 0)
                    counted += 1
            except (requests.RequestException, ValueError, KeyError) as e:
                print(f"    ! 结算失败({attempt + 1}/4): {e}")
            # 花费还没结算出来时（全 0）再等等
            if total > 0 or attempt == 3:
                break
            time.sleep(3)

        self.cost_usd = total
        if counted:
            print(f"  本次共 {counted} 个 run，花费 ${total:.4f}")
        return total

    def account_usage(self) -> dict:
        """返回本计费周期的用量，用于预算保险丝。"""
        try:
            r = requests.get(
                f"{API}/users/me/limits", params={"token": self.token}, timeout=30
            )
            d = r.json()["data"]
            return {
                "used": d["current"]["monthlyUsageUsd"],
                "limit": d["limits"]["maxMonthlyUsageUsd"],
                "cycle_end": d["monthlyUsageCycle"]["endAt"][:10],
            }
        except (requests.RequestException, ValueError, KeyError) as e:
            print(f"  ! 读取账户用量失败: {e}")
            return {}
