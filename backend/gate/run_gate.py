#!/usr/bin/env python3
"""折边 × 盒高 可重复门禁 —— 主执行脚本。

四个阶段（书型盒）：
  1. BASELINE       记下种子状态基准 paper_m2
  2. RAISE_OVERLAP  仅把 overlap 调到严格更大，再算，面积必须上升
  3. RAISE_HEIGHT   仅增加该盒高度，再算，面积继续上升，并用公式核对增量
  4. RESTORE        overlap 与三边全部复原，面积回到基准，
                    且设置读回 overlap、礼盒详情三边与复原目标一致

观测源取舍：每一步都「写接口 → 独立 GET 读回 → 再走算纸接口读数」三重核对，
断言只认接口返回的真实读数，不认脚本本地变量。不直接改数据库文件，
也不改算纸公式。任一步失败：进程非零退出，并打出阶段名与当时 paper_m2。

用法：
  python3 run_gate.py                      # 自动拉起一次性 uvicorn（临时数据目录，可重复）
  GATE_BASE_URL=http://127.0.0.1:9900 python3 run_gate.py   # 对接已在跑的服务
期望数值从同目录 expected_values.json 读取。
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from gate_client import GateAPIError, GateClient
import stage_log

GATE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = GATE_DIR.parent
EXPECTED_PATH = GATE_DIR / "expected_values.json"


class GateFailure(RuntimeError):
    def __init__(self, stage: str, message: str):
        super().__init__(f"[{stage}] {message}")
        self.stage = stage
        self.message = message


class AreaTracker:
    """保存最近一次从算纸接口读到的 paper_m2，供失败时打印。"""

    def __init__(self) -> None:
        self.value: float | None = None

    def set(self, value: float) -> None:
        self.value = float(value)


def expect_close(stage: str, label: str, actual: float, expected: float,
                 tol: float) -> None:
    if abs(float(actual) - float(expected)) > tol:
        raise GateFailure(
            stage, f"{label} 读数 {actual} 与期望 {expected} 偏差超过 {tol}")


def expect_true(stage: str, condition: bool, message: str) -> None:
    if not condition:
        raise GateFailure(stage, message)


# ---------------- 各阶段 ----------------

def phase_baseline(client: GateClient, area: AreaTracker, exp: dict) -> int:
    stage = "BASELINE"
    base = exp["baseline"]
    stage_log.stage_start(stage, "确认种子书型盒与基准算纸读数")

    box = client.find_box_by_name(exp["box_name"])
    bid = box["id"]

    # 写之前先读：种子三边必须就是基准三边
    detail = client.get_box(bid)
    for dim in ("length", "width", "height"):
        expect_close(stage, f"box.{dim}", detail[dim], base[dim], exp["tol"])

    # 设置读回必须是种子 overlap
    expect_close(stage, "settings.overlap", client.get_overlap(),
                 base["overlap"], exp["tol"])

    # 算纸不传 overlap：强制使用服务端当前全局设置
    est = client.estimate(bid)
    area.set(est["paper_m2"])
    expect_close(stage, "estimate.overlap（服务端实际采用）",
                 est["overlap"], base["overlap"], exp["tol"])
    expect_close(stage, "box_surface", est["box_surface"],
                 base["box_surface"], exp["tol"])
    expect_close(stage, "paper_m2 基准", est["paper_m2"],
                 base["paper_m2"], exp["tol"])

    stage_log.stage_ok(stage, f"基准 paper_m2={est['paper_m2']} (box_id={bid})")
    return bid


def phase_raise_overlap(client: GateClient, area: AreaTracker, exp: dict,
                        bid: int, baseline_paper: float) -> float:
    stage = "RAISE_OVERLAP"
    base = exp["baseline"]
    target = exp["raised_overlap"]
    stage_log.stage_start(stage, f"overlap {base['overlap']} -> {target}（严格更大）")
    expect_true(stage, target > base["overlap"],
                f"期望 raised_overlap {target} 必须严格大于基准 {base['overlap']}")

    # 1) 写接口
    written = client.set_overlap(target)
    expect_close(stage, "PUT overlap 回显", written, target, exp["tol"])
    # 2) 独立 GET 设置读回——不能只信写接口回显 / 本地变量
    expect_close(stage, "GET settings.overlap 读回", client.get_overlap(),
                 target, exp["tol"])
    # 3) 算纸读数（不传 overlap，逼服务端用新设置）
    est = client.estimate(bid)
    area.set(est["paper_m2"])
    expect_close(stage, "estimate.overlap（服务端实际采用）",
                 est["overlap"], target, exp["tol"])
    expect_close(stage, "paper_m2（overlap 调大）", est["paper_m2"],
                 exp["checks"]["raised_overlap_paper_m2"], exp["tol"])
    expect_true(stage, est["paper_m2"] > baseline_paper + exp["tol"],
                f"overlap 调大后面积应上升：{est['paper_m2']} !> {baseline_paper}")

    stage_log.stage_ok(stage, f"paper_m2={est['paper_m2']} > 基准 {baseline_paper}")
    return est["paper_m2"]


def phase_raise_height(client: GateClient, area: AreaTracker, exp: dict,
                       bid: int, prev_paper: float) -> float:
    stage = "RAISE_HEIGHT"
    base = exp["baseline"]
    h_new = exp["raised_height"]
    stage_log.stage_start(stage, f"仅增高：height {base['height']} -> {h_new}")
    expect_true(stage, h_new > base["height"],
                f"raised_height {h_new} 必须严格大于基准高度 {base['height']}")

    # 只改高度；长、宽保持基准
    written = client.update_box(bid, base["length"], base["width"], h_new)
    for dim, val in (("length", base["length"]), ("width", base["width"]),
                     ("height", h_new)):
        expect_close(stage, f"PUT box.{dim} 回显", written[dim], val, exp["tol"])
    # 独立 GET 礼盒详情读回
    detail = client.get_box(bid)
    for dim, val in (("length", base["length"]), ("width", base["width"]),
                     ("height", h_new)):
        expect_close(stage, f"GET box detail.{dim} 读回", detail[dim], val,
                     exp["tol"])

    # 算纸读数
    est = client.estimate(bid)
    area.set(est["paper_m2"])
    expect_close(stage, "paper_m2（高度增加）", est["paper_m2"],
                 exp["checks"]["raised_height_paper_m2"], exp["tol"])
    expect_true(stage, est["paper_m2"] > prev_paper + exp["tol"],
                f"增高后面积应继续上升：{est['paper_m2']} !> {prev_paper}")

    # 公式核对：paper = 2(LW+LH+WH) * overlap
    L, W, H = base["length"], base["width"], h_new
    overlap = client.get_overlap()
    formula = round(2 * (L * W + L * H + W * H) * overlap, 3)
    expect_close(stage, "公式复算 paper_m2", formula, est["paper_m2"], exp["tol"])

    # 增量核对：Δpaper = 2(L+W)·ΔH·overlap（长、宽未动）
    delta = est["paper_m2"] - prev_paper
    expect_close(stage, "Δpaper vs 2(L+W)·ΔH·overlap",
                 delta, exp["checks"]["height_delta_paper"], exp["tol"])
    formula_delta = round(2 * (L + W) * (h_new - base["height"]) * overlap, 3)
    expect_close(stage, "Δpaper 公式增量", delta, formula_delta, exp["tol"])

    stage_log.stage_ok(
        stage,
        f"paper_m2={est['paper_m2']} > {prev_paper}；Δpaper={delta:.3f} 与公式一致")
    return est["paper_m2"]


def phase_restore(client: GateClient, area: AreaTracker, exp: dict,
                  bid: int, baseline_paper: float) -> None:
    stage = "RESTORE"
    base = exp["baseline"]
    stage_log.stage_start(stage, "复原 overlap 与礼盒三边")

    # 复原 overlap：写 + 读回
    written_ov = client.set_overlap(base["overlap"])
    expect_close(stage, "PUT overlap 回显", written_ov, base["overlap"], exp["tol"])
    readback_ov = client.get_overlap()
    expect_close(stage, "GET settings.overlap 复原读回", readback_ov,
                 base["overlap"], exp["tol"])

    # 复原三边：写 + 礼盒详情独立读回
    written_box = client.update_box(bid, base["length"], base["width"],
                                    base["height"])
    for dim in ("length", "width", "height"):
        expect_close(stage, f"PUT box.{dim} 回显", written_box[dim],
                     base[dim], exp["tol"])
    detail = client.get_box(bid)
    for dim in ("length", "width", "height"):
        expect_close(stage, f"GET 礼盒详情.{dim} 复原读回", detail[dim],
                     base[dim], exp["tol"])

    # 算纸读数必须回到基准
    est = client.estimate(bid)
    area.set(est["paper_m2"])
    expect_close(stage, "estimate.overlap（服务端实际采用）",
                 est["overlap"], base["overlap"], exp["tol"])
    expect_close(stage, "paper_m2 复原", est["paper_m2"],
                 exp["checks"]["restored_paper_m2"], exp["tol"])
    expect_close(stage, "paper_m2 回到基准", est["paper_m2"],
                 baseline_paper, exp["tol"])

    stage_log.stage_ok(
        stage,
        f"overlap={readback_ov}，三边="
        f"{detail['length']}×{detail['width']}×{detail['height']}，"
        f"paper_m2={est['paper_m2']} 回到基准")


# ---------------- 一次性服务拉起 ----------------

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class EphemeralServer:
    """无 GATE_BASE_URL 时，用临时数据目录拉起一次性 uvicorn，保证可重复。

    数据目录由服务端自己建库/播种，门禁全程只通过 HTTP 接触它。
    """

    def __init__(self) -> None:
        self.port = _free_port()
        self.data_dir = tempfile.mkdtemp(prefix="giftwrap-gate-")
        self.proc: subprocess.Popen | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> str:
        env = dict(os.environ)
        env["DATA_DIR"] = self.data_dir
        env["PYTHONPATH"] = str(BACKEND_DIR)
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app",
             "--host", "127.0.0.1", "--port", str(self.port)],
            cwd=str(BACKEND_DIR), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        client = GateClient(self.base_url)
        deadline = time.time() + 30
        last_err: Exception | None = None
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("uvicorn 子进程提前退出")
            try:
                if client.health().get("ok") is True:
                    return self.base_url
            except GateAPIError as exc:
                last_err = exc
            time.sleep(0.3)
        raise RuntimeError(f"等待一次性服务就绪超时：{last_err}")

    def __exit__(self, *exc_info) -> None:
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


# ---------------- 入口 ----------------

def main() -> int:
    exp = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    area = AreaTracker()
    stage = "SETUP"

    base_url = os.environ.get("GATE_BASE_URL")
    ephemeral: EphemeralServer | None = None
    try:
        if base_url:
            stage_log.info(stage, f"对接外部服务 {base_url}")
        else:
            stage_log.info(stage, "未设置 GATE_BASE_URL，拉起一次性 uvicorn（临时数据目录）")
            ephemeral = EphemeralServer()
            base_url = ephemeral.__enter__()

        client = GateClient(base_url)

        bid = phase_baseline(client, area, exp)
        baseline_paper = area.value
        p2 = phase_raise_overlap(client, area, exp, bid, baseline_paper)
        phase_raise_height(client, area, exp, bid, p2)
        phase_restore(client, area, exp, bid, baseline_paper)

        stage_log.info("RESULT", "全部四阶段通过，门禁成功 (exit 0)")
        return 0

    except GateFailure as exc:
        stage_log.stage_fail(exc.stage, exc.message, area.value)
        return 1
    except Exception as exc:  # noqa: BLE001 - 任何意外都算门禁失败
        stage_log.stage_fail(stage, f"未预期异常：{exc}", area.value, exc)
        return 1
    finally:
        if ephemeral is not None:
            ephemeral.__exit__(*sys.exc_info())


if __name__ == "__main__":
    sys.exit(main())
