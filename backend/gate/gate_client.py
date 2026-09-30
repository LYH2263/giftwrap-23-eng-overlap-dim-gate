"""门禁客户端模块：只通过 HTTP 接口读写设置 / 礼盒 / 算纸。

不 import 任何后端代码、不直接碰数据库文件——保证观测源就是线上接口：
写成功与否看接口返回，最终状态再用独立的 GET 读回核对。
仅依赖 Python 标准库，便于在最小环境里运行。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


class GateAPIError(RuntimeError):
    def __init__(self, method: str, path: str, status: int, body: str):
        super().__init__(f"{method} {path} -> {status}: {body[:300]}")
        self.method = method
        self.path = path
        self.status = status
        self.body = body


class GateClient:
    def __init__(self, base_url: str = "http://127.0.0.1:9900", timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ---- 底层 HTTP ----
    def _request(self, method: str, path: str, query: dict | None = None,
                 payload: dict | None = None) -> dict:
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise GateAPIError(method, path, exc.code,
                               exc.read().decode("utf-8", "replace")) from exc
        except urllib.error.URLError as exc:
            raise GateAPIError(method, path, 0, str(exc.reason)) from exc
        return json.loads(raw) if raw else {}

    # ---- 健康检查 ----
    def health(self) -> dict:
        return self._request("GET", "/api/health")

    # ---- 设置：折边系数 ----
    def get_settings(self) -> dict:
        return self._request("GET", "/api/settings")

    def get_overlap(self) -> float:
        return float(self.get_settings()["overlap"])

    def set_overlap(self, value: float) -> float:
        return float(self._request("PUT", "/api/settings/overlap",
                                   payload={"overlap": float(value)})["value"])

    # ---- 礼盒 ----
    def get_box(self, box_id: int) -> dict:
        return self._request("GET", f"/api/boxes/{int(box_id)}")

    def update_box(self, box_id: int, length: float, width: float,
                   height: float) -> dict:
        return self._request("PUT", f"/api/boxes/{int(box_id)}", payload={
            "length": float(length),
            "width": float(width),
            "height": float(height),
        })

    def find_box_by_name(self, name: str) -> dict:
        items = self._request("GET", "/api/boxes")["items"]
        for box in items:
            if box.get("name") == name:
                return box
        raise GateAPIError("GET", "/api/boxes", 404,
                           f"未找到种子礼盒 {name!r}，现有：{[b.get('name') for b in items]}")

    # ---- 算纸 ----
    def estimate(self, box_id: int, overlap: float | None = None) -> dict:
        """overlap=None 时不传该参数，强制走服务端当前全局设置——

        这样读到的 paper_m2 才真正反映设置接口写入后的服务端状态，
        而不是门禁本地传参算出的数。
        """
        query: dict = {"box_id": int(box_id), "save": "false"}
        if overlap is not None:
            query["overlap"] = float(overlap)
        return self._request("GET", "/api/estimate", query=query)
