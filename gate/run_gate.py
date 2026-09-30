#!/usr/bin/env python3
"""折边(overlap) × 盒高门禁主执行脚本（黑盒，只走 HTTP 接口，不碰数据库文件）。

阶段：
  0 复位基准   把 overlap/三边写成种子基准并 GET 读回，保证可重复执行
  1 基准       用设置里的 overlap 算纸，记下基准 paper_m2
  2 提高overlap overlap 严格调大：写设置 + GET 读回 + 算纸，面积必须严格上升且等于清单值
  3 只增加高度  仅把高度调大：写礼盒 + GET 读回三边 + 算纸，面积继续上升，并用独立公式核对
  4 复原       overlap 与三边全部复原，GET 读回须与复原目标一致，面积回到基准

任一步失败：打印阶段名与当时 paper_m2，进程以非零码退出。
期望值全部来自 expected_values.json，脚本内不硬编码期望面积。
"""
import argparse
import json
import os
import sys

from gate_client import GateClient, GateClientError
from stage_log import StageLogger

TOL = 1e-9


class GateFailure(RuntimeError):
    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


def approx(a: float, b: float) -> bool:
    return abs(float(a) - float(b)) <= TOL


def check(cond: bool, detail: str) -> None:
    if not cond:
        raise GateFailure(detail)


def independent_paper_m2(length, width, height, overlap) -> float:
    """门禁侧独立公式（不 import 后端）：2(LW+LH+WH)*overlap，按接口口径保留三位。"""
    surface = 2 * (length * width + length * height + width * height)
    return round(surface, 3), round(surface * overlap, 3)


def main() -> int:
    ap = argparse.ArgumentParser(description="giftwrap overlap×盒高 门禁")
    ap.add_argument("--base-url", default=os.environ.get("GATE_BASE_URL", "http://127.0.0.1:9900"))
    default_expected = os.path.join(os.path.dirname(os.path.abspath(__file__)), "expected_values.json")
    ap.add_argument("--expected", default=default_expected)
    args = ap.parse_args()

    log = StageLogger()
    last_area = None
    stage = "init"
    try:
        with open(args.expected, encoding="utf-8") as f:
            expected = json.load(f)
        client = GateClient(args.base_url)

        base = expected["baseline"]
        raised_ov = expected["raised_overlap"]
        raised_h = expected["raised_height"]
        restored = expected["restored"]

        # ---------- 阶段 0：健康检查 + 复位到种子基准（保证可重复跑） ----------
        stage = "0-复位基准"
        log.stage(stage)
        h = client.health()
        check(h.get("ok") is True, f"健康检查返回异常: {h}")
        box = client.find_box_by_name(expected["box_name"])
        box_id = box["id"]
        log.info(f"目标礼盒：{box['name']} (id={box_id})")

        client.put_overlap(base["overlap"])
        settings_after = client.get_settings()
        ov_after = float(settings_after["overlap"])
        check(approx(ov_after, base["overlap"]),
              f"overlap 写后读回 {ov_after} != 目标 {base['overlap']}")
        client.put_dimensions(box_id, base["length"], base["width"], base["height"])
        box0 = client.get_box(box_id)
        check(approx(box0["length"], base["length"]) and approx(box0["width"], base["width"])
              and approx(box0["height"], base["height"]),
              f"三边写后读回 {sides(box0)} != 基准 ({base['length']},{base['width']},{base['height']})")
        log.info(f"已复位：overlap={ov_after}, 三边={sides(box0)}")

        # ---------- 阶段 1：基准算纸（不传 overlap，走设置） ----------
        stage = "1-基准"
        log.stage(stage)
        r1 = client.estimate(box_id)
        last_area = r1["paper_m2"]
        check(approx(r1["overlap"], base["overlap"]),
              f"算纸回显 overlap {r1['overlap']} != {base['overlap']}")
        check(approx(last_area, base["paper_m2"]),
              f"基准面积 {last_area} != 清单期望 {base['paper_m2']}")
        check(approx(r1["box_surface"], base["box_surface"]),
              f"基准表面积 {r1['box_surface']} != {base['box_surface']}")
        baseline_area = last_area
        log.info(f"基准 paper_m2={baseline_area}")

        # ---------- 阶段 2：overlap 严格调大 ----------
        stage = "2-提高overlap"
        log.stage(stage)
        check(raised_ov["overlap"] > base["overlap"],
              f"清单设定未严格调大: {raised_ov['overlap']} <= {base['overlap']}")
        client.put_overlap(raised_ov["overlap"])
        ov2 = float(client.get_settings()["overlap"])  # 独立 GET 读回，不信本地变量
        check(approx(ov2, raised_ov["overlap"]),
              f"overlap 写后读回 {ov2} != 目标 {raised_ov['overlap']}")
        r2 = client.estimate(box_id)  # 不传 overlap，验证设置真正驱动算纸
        last_area = r2["paper_m2"]
        check(approx(r2["overlap"], raised_ov["overlap"]),
              f"算纸采用的 overlap {r2['overlap']} != 设置读回 {ov2}")
        check(approx(last_area, raised_ov["paper_m2"]),
              f"提高 overlap 后面积 {last_area} != 清单期望 {raised_ov['paper_m2']}")
        check(last_area > baseline_area + TOL,
              f"面积未上升: {last_area} <= 基准 {baseline_area}")
        log.info(f"overlap={ov2} 写成功且读回一致；paper_m2={last_area} > {baseline_area}")

        # ---------- 阶段 3：只增加盒高 ----------
        stage = "3-只增加高度"
        log.stage(stage)
        check(approx(raised_h["length"], base["length"]) and approx(raised_h["width"], base["width"]),
              "清单错误：本阶段必须只改高度，长/宽须与基准一致")
        check(raised_h["height"] > base["height"],
              f"清单设定高度未增加: {raised_h['height']} <= {base['height']}")
        client.put_dimensions(box_id, raised_h["length"], raised_h["width"], raised_h["height"])
        box3 = client.get_box(box_id)  # 独立 GET 读回三边
        check(approx(box3["length"], raised_h["length"]) and approx(box3["width"], raised_h["width"])
              and approx(box3["height"], raised_h["height"]),
              f"三边写后读回 {sides(box3)} != 目标 ({raised_h['length']},{raised_h['width']},{raised_h['height']})")
        r3 = client.estimate(box_id)
        last_area = r3["paper_m2"]
        check(approx(last_area, raised_h["paper_m2"]),
              f"加高后面积 {last_area} != 清单期望 {raised_h['paper_m2']}")
        check(last_area > r2["paper_m2"] + TOL,
              f"加高后面积未继续上升: {last_area} <= {r2['paper_m2']}")
        # 独立公式核对（表面积与用纸面积都对）
        formula_surface, formula_area = independent_paper_m2(
            raised_h["length"], raised_h["width"], raised_h["height"], raised_h["overlap"])
        check(approx(r3["box_surface"], formula_surface) and approx(r3["box_surface"], raised_h["box_surface"]),
              f"表面积与公式不符: 接口 {r3['box_surface']} != 公式 {formula_surface}")
        check(approx(last_area, formula_area),
              f"面积与独立公式核对失败: 接口 {last_area} != 公式 {formula_area}")
        log.info(f"三边读回={sides(box3)}；paper_m2={last_area} > {r2['paper_m2']}；公式核对 {formula_surface}×{ov2}={formula_area}")

        # ---------- 阶段 4：overlap 与三边全部复原 ----------
        stage = "4-复原"
        log.stage(stage)
        client.put_overlap(restored["overlap"])
        client.put_dimensions(box_id, restored["length"], restored["width"], restored["height"])
        # 全部用独立 GET 读回核对
        ov_final = float(client.get_settings()["overlap"])
        box_final = client.get_box(box_id)
        check(approx(ov_final, restored["overlap"]),
              f"复原后设置读回 overlap {ov_final} != 目标 {restored['overlap']}")
        check(approx(box_final["length"], restored["length"])
              and approx(box_final["width"], restored["width"])
              and approx(box_final["height"], restored["height"]),
              f"复原后礼盒详情三边 {sides(box_final)} != 目标 ({restored['length']},{restored['width']},{restored['height']})")
        r4 = client.estimate(box_id)
        last_area = r4["paper_m2"]
        check(approx(r4["overlap"], restored["overlap"]),
              f"复原后算纸 overlap {r4['overlap']} != {restored['overlap']}")
        check(approx(last_area, baseline_area),
              f"复原后面积 {last_area} 未回到基准 {baseline_area}")
        check(approx(last_area, restored["paper_m2"]),
              f"复原后面积 {last_area} != 清单期望 {restored['paper_m2']}")
        log.info(f"overlap 读回={ov_final}；三边读回={sides(box_final)}；paper_m2={last_area} 回到基准")

        log.info(f"门禁全部通过：{baseline_area} -> {r2['paper_m2']} -> {r3['paper_m2']} -> {last_area}")
        return 0

    except GateFailure as e:
        log.fail(stage, last_area, e.detail)
        return 1
    except GateClientError as e:
        detail = f"接口错误: {e} {('HTTP ' + str(e.status) + ' ' + e.body[:300]) if e.status else ''}"
        log.fail(stage, last_area, detail.strip())
        return 2
    except Exception as e:  # 网络抖动/JSON 异常等，同样带阶段名与当时面积非零退出
        log.fail(stage, last_area, f"未预期异常: {type(e).__name__}: {e}")
        return 3


def sides(box: dict) -> str:
    return f"(L={box['length']}, W={box['width']}, H={box['height']})"


if __name__ == "__main__":
    sys.exit(main())
