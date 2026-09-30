"""算纸门禁的 HTTP 客户端模块（仅标准库）。

只通过接口观测：设置(/api/settings)、礼盒(/api/boxes)、算纸(/api/estimate)。
所有写方法返回服务端读回的 JSON，绝不回显本地变量，调用方必须用返回值核对。
"""
import json as _json
import urllib.error
import urllib.parse
import urllib.request


class GateClientError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


class GateClient:
    def __init__(self, base_url: str = "http://127.0.0.1:9900", timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict | None = None,
                 query: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = _json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise GateClientError(f"{method} {path} -> HTTP {e.code}", e.code, body) from e
        except urllib.error.URLError as e:
            raise GateClientError(f"{method} {path} -> {e.reason}") from e
        return _json.loads(raw) if raw else {}

    # ---- 健康检查 ----
    def health(self) -> dict:
        return self._request("GET", "/api/health")

    # ---- 设置 ----
    def get_settings(self) -> dict:
        return self._request("GET", "/api/settings")

    def get_overlap(self) -> float:
        return float(self.get_settings()["overlap"])

    def put_overlap(self, overlap: float) -> dict:
        """写入 overlap 并返回服务端读回的 settings（值是字符串，需自行 float 解析）。"""
        return self._request("PUT", "/api/settings", {"overlap": overlap})

    # ---- 礼盒 ----
    def list_boxes(self) -> list[dict]:
        return self._request("GET", "/api/boxes")["items"]

    def find_box_by_name(self, name: str) -> dict:
        for box in self.list_boxes():
            if box.get("name") == name:
                return box
        raise GateClientError(f"未找到名为 {name!r} 的礼盒")

    def get_box(self, box_id: int) -> dict:
        return self._request("GET", f"/api/boxes/{box_id}")

    def put_dimensions(self, box_id: int, length: float, width: float, height: float) -> dict:
        """更新礼盒三边并返回服务端读回的礼盒详情。"""
        return self._request(
            "PUT", f"/api/boxes/{box_id}",
            {"length": length, "width": width, "height": height},
        )

    # ---- 算纸 ----
    def estimate(self, box_id: int, overlap: float | None = None,
                 wrap_style: str = "cross") -> dict:
        query = {"box_id": box_id, "wrap_style": wrap_style}
        if overlap is not None:
            query["overlap"] = overlap
        return self._request("GET", "/api/estimate", query=query)
