# 第二阶段：A 股隔夜反转研究工作台

这是第二阶段交付时的历史说明。当前第三阶段请使用 `README_STAGE3.md` 和 `python start_stage3.py`；页面和依赖已有更新，不再以本页旧安装命令为当前版本的启动指南。

第二阶段包含真实 LangGraph 状态图、FastAPI 后台实验、轻量前端、MCP stdio 工具。默认离线模式运行确定性研究流程，**不调用 LLM**；配置模型后，可根据自然语言问题选择工具、读取返回证据并生成分析文字。量化结果由 Python 计算，模型不能覆盖回测结果。

## 启动

在本项目目录执行（Python 3.11+）：

```powershell
python start_stage2.py
```

首次自动建立 `.venv-stage2` 并安装验证时锁定的依赖。此环境与原上游 Poetry 环境分开，避免旧版 LangChain 冲突；无需 PowerShell 激活脚本。后续补装用 `python start_stage2.py --install`。端口占用时用 `--port 8001`。

页面：<http://127.0.0.1:8000>；API 文档：<http://127.0.0.1:8000/docs>。使用“演示数据 + 离线演示”，点击开始研究。默认样例是人工构造的 3 只股票、10 个日期，负收益是演示结果，不是实盘或策略有效性证据。

手动安装与启动也可以：

```powershell
python -m venv .venv-stage2
.venv-stage2\Scripts\python.exe -m pip install -r requirements-stage2-lock.txt
.venv-stage2\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Unix 使用 `.venv-stage2/bin/python`。锁定依赖快照来自 Windows / Python 3.13.9；`pywin32` 带 Windows 条件。未在其他操作系统实测，可使用范围依赖 `requirements-stage2.txt` 重新解析。

## 数据

CSV 放在 `data` 目录，文件名只支持英文字母、数字、下划线和连字符，例如 `ashare.csv` 对应 `dataset_id=ashare`。页面刷新后可选择。CSV 规范和 AKShare 下载见第一阶段 README；AKShare 是可选依赖，第二阶段不会在实验中自动下载数据。

必需列：`date,code,open,high,low,close,volume`；可选 `limit_up,limit_down`。价格必须有限且正、成交量非负、日期和六位股票代码有效，不得有重复日线。单文件最多 30 MB / 200,000 行。数据检查会报告缺口和已知不足；它不能自动判断复权或历史股票池是否可靠。

每个实验在 `outputs/stage2/<id>/input/` 保存实际使用的 CSV，在报告保存 SHA256。后续修改源文件不改变已完成实验。默认存储根和数据根可用 `.stage2.env` 中的 `CN_OUTPUT_ROOT`、`CN_DATA_ROOT` 设置。

## 自然语言与模型工具调用

复制 `.stage2.env.example` 为 `.stage2.env`，设置：

```dotenv
LLM_BASE_URL=https://你的服务地址/v1
LLM_MODEL=支持工具调用的模型名称
LLM_API_KEY=你的密钥
```

服务需要支持 `/chat/completions` 的 `tools` / `tool_calls` 协议。重启服务，页面会启用“模型分析”。研究问题决定模型的分析方向和附加工具查询；基础回测的股票池、成本和分位由显式表单参数决定，模型不修改这份权威结果。

基础流程必跑：数据检查 → 因子快照 → 回测 → 零成本对照。模型随后可以进行最多 3 轮附加工具调用，每轮最多 3 个调用；连同最终回答，最多 4 次模型请求。模型调用失败或达到上限时保留计算结果，报告明确标示回退为规则分析。

模型模式会将研究问题、数据摘要和工具结果发送到所配置的模型服务。密钥仅从服务端环境读取，不写入实验数据库、报告或前端。当前没有配置真实密钥，已用模拟模型和 HTTP stub 测试工具调用与失败处理，**未验证外部模型的真实返回效果**。

离线模式的研究问题仅作为实验记录，结论是规则生成，不能冒称 LLM 推理。无需密钥的命令行运行：

```powershell
.venv-stage2\Scripts\python.exe -m research_agent --dataset sample_ashare --mode offline
```

## HTTP API

| 方法 / 路径 | 用途 |
|---|---|
| GET `/api/health` | 服务和模型配置状态 |
| GET `/api/datasets` | 白名单数据集 |
| GET `/api/datasets/{id}` | 数据质量摘要 |
| POST `/api/factors` | 指定 as_of 的因子快照 |
| POST `/api/experiments` | 返回 202 和实验 ID，后台执行 |
| GET `/api/experiments` | 最近 50 个实验 |
| GET `/api/experiments/{id}` | 状态、工具事件和完整结果 |
| GET `/api/experiments/{id}/report` | Markdown 报告 |
| GET `/api/experiments/{id}/report?format=json` | 结构化报告 |

提交示例（可粘贴到 `/docs` 的 Try it out）：

```json
{"dataset_id":"sample_ashare","mode":"offline","question":"评估成本和数据限制。","quantile":0.2,"initial_capital":1000000,"commission_bps":3,"stamp_duty_bps":5,"slippage_bps":5}
```

状态：`queued → running → completed / failed`。2 个线程执行、最多 8 个在途任务；满额返回 429。SQLite 保存参数、事件、结果和失败原因。此 MVP 使用单个 API 进程；不要开多个 uvicorn worker 或同时运行 CLI 写入相同任务存储。重启会将被中断的任务标记失败，保留事件，需要重新提交；没有宣称具备分布式队列或断点续跑。

## MCP

MCP 服务使用标准 stdio，通过同一套 `ResearchTools` 提供：

- `list_datasets`
- `validate_dataset`
- `compute_factor`
- `run_backtest`
- `compare_costs`
- `parameter_sensitivity`

启动命令：

```powershell
.venv-stage2\Scripts\python.exe -m mcp_server.server
```

这是给 MCP 客户端启动的子进程，不是浏览器页面；stdout 保留给 JSON-RPC，不要在终端期待交互提示。客户端配置参考 `mcp_server/client.example.json`，把两个路径换成自己的绝对路径。无需启动 FastAPI 即可使用 MCP。

每个工具有类型化输入、参数边界和结构化 JSON 输出；只允许 `data` 下的数据集 ID，不接受任意路径。没有真实下单工具。参数敏感性只做至多 3 个分位的同样本描述性比较，不是样本外验证。

## 回测修正与边界

第二阶段修正第一阶段“用未来退出日可成交性过滤买入名单”的问题。现在逐日执行，信号在 t 收盘形成、t+1 开盘尝试买入，t+2 收盘尝试卖出；无法退出时继续持有和重试。买单不根据未来价格决定是否成交，未成交的分配资金留在现金中。按 100 股整手买入，无杠杆、无做空、无买入当日卖出。

净值逐日计算，期末仍持有的仓位按最新已知收盘价估值，未强制平仓；缺行情沿用旧估值并记录 `stale_marks`。每日最大回撤和日收益 Sharpe 取代第一阶段的批次近似。仍保留旧键 `max_drawdown_cohort`、`win_rate_cohort` 作为兼容别名，但数值分别表示每日回撤和已完成个股交易胜率。新的调用请使用 `max_drawdown_daily`、`win_rate_trade`。

限制仍包括：数据并集交易日历、固定股票池、未处理公司行动和股息、固定印花税率、未模拟最低佣金和市场冲击、仅在提供限制价时判断封板、日线开收盘成交假设。100 股整手模型只覆盖相应规则的 A 股研究场景，不能直接用于不同最小申报量的板块。包装成 Agent 不会消除这些限制。

## 验证

```powershell
.venv-stage2\Scripts\python.exe -m pytest tests -q
.venv-stage2\Scripts\python.exe -m pip check
```

覆盖：第一阶段因子、未来退出缺行情不影响过去买入、未来价格变更不影响过去净值、卖出封跌停延期、T+1、现金与费用对账、坏数据、路径限制、LangGraph 必跑流程、模型附加工具调用和上限、模型失败回退、API 异步任务和历史读取、报告导出、MCP 真实 stdio 握手与调用。

上游 `hedge_fund` 的原测试需要其 Poetry 环境，本阶段没有声称在新环境验证整个上游项目。
