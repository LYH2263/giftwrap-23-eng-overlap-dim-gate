"""阶段日志模块：为门禁的每个阶段打印统一格式的开始/成功/失败记录。

观测约定：所有打印都基于门禁通过 HTTP 接口读到的真实读数，
绝不记录本地"以为写入成功"的变量作为事实。
"""
from __future__ import annotations

import sys
from datetime import datetime


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def info(stage: str, message: str) -> None:
    print(f"[{_now()}] {stage} | {message}", flush=True)


def stage_start(stage: str, message: str) -> None:
    print(f"[{_now()}] {stage} | 开始：{message}", flush=True)


def stage_ok(stage: str, message: str) -> None:
    print(f"[{_now()}] {stage} | 通过：{message}", flush=True)


def stage_fail(stage: str, message: str, paper_m2: float | None = None,
               exc: BaseException | None = None) -> None:
    """任一步失败时调用：打出阶段名与当时面积，便于定位。"""
    area = "n/a" if paper_m2 is None else f"{paper_m2:.6f}"
    print(f"[{_now()}] {stage} | 失败：{message} | 当时 paper_m2={area}",
          file=sys.stderr, flush=True)
    if exc is not None:
        print(f"[{_now()}] {stage} | 异常：{type(exc).__name__}: {exc}",
              file=sys.stderr, flush=True)
