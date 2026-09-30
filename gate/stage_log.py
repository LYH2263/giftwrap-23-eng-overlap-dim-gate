"""阶段日志模块：门禁每个阶段带阶段名打印；失败时固定格式打出阶段名与当时算纸面积。"""
import sys


class StageLogger:
    def __init__(self, out_stream=sys.stdout, err_stream=sys.stderr):
        self._out = out_stream
        self._err = err_stream
        self._stage = "-"

    @property
    def current(self) -> str:
        return self._stage

    def stage(self, name: str) -> None:
        self._stage = name
        self.info(f"== 阶段开始：{name} ==")

    def info(self, msg: str) -> None:
        print(f"[{self._stage}] {msg}", file=self._out, flush=True)

    def fail(self, stage: str, area, detail: str) -> None:
        area_text = "n/a" if area is None else f"{area}"
        print(
            f"[FAIL] 阶段={stage} | paper_m2={area_text} | 原因={detail}",
            file=self._err,
            flush=True,
        )
