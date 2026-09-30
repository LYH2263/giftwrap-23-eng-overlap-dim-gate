# 折边 × 盒高 可重复门禁

三个文件 + 一份期望数值清单：

| 文件 | 职责 |
| --- | --- |
| `run_gate.py` | 主执行脚本：读 `expected_values.json`，编排四阶段断言，失败非零退出 |
| `gate_client.py` | 客户端模块：**仅**经 HTTP 调用 设置 / 礼盒 / 算纸 接口（stdlib，无第三方依赖） |
| `stage_log.py` | 阶段日志模块：统一的开始 / 通过 / 失败打印，失败带阶段名与当时面积 |
| `expected_values.json` | 期望数值清单，供主脚本读取（不在代码里写死数值） |

## 四阶段（种子「书型盒」0.30×0.20×0.15）

1. **BASELINE**：三边/overlap 读回与种子一致，基准 `paper_m2 = 0.27 × 1.15 = 0.31`。
2. **RAISE_OVERLAP**：overlap 1.15 → 1.30（严格更大），`paper_m2 → 0.351`，必须上升。
3. **RAISE_HEIGHT**：仅 height 0.15 → 0.18，`paper_m2 → 0.39`，继续上升；
   用公式 `paper = 2(LW+LH+WH)·overlap` 复算，并核对增量
   `Δpaper = 2(L+W)·ΔH·overlap = 0.039`。
4. **RESTORE**：overlap 与三边全部复原，`paper_m2` 回到 `0.31`；
   且设置读回 overlap、礼盒详情三边都与复原目标一致。

## 观测源取舍

每步都是 **写接口 → 独立 GET 读回 → 再走算纸接口读数** 三重核对；
算纸阶段刻意**不**在请求里传 overlap，逼服务端用全局设置，
证明读到的是设置接口真正落库后的值，而不是本地变量或本地传参。
门禁不 import 后端代码、不直接读写数据库文件，也不改算纸公式。

## 运行

```bash
# 方式一：自动拉起一次性 uvicorn（临时数据目录，跑完全销毁，天然可重复）
python3 gate/run_gate.py

# 方式二：对接已在运行的服务（会在该库上改动并复原）
GATE_BASE_URL=http://127.0.0.1:9900 python3 gate/run_gate.py
```

任一步失败：退出码非 0，stderr 打出阶段名与当时 `paper_m2`；
连续运行两次都必须全部通过（持久服务模式下第二次的 BASELINE 即验证复原）。
