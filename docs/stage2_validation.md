# 第二阶段本地验证记录

日期：2026-10-09（Asia/Shanghai）。平台：Windows，Python 3.13.9，独立 `.venv-stage2`，依赖版本见 `requirements-stage2-lock.txt`。

## 完成的检查

- `python -m pytest tests -q`：29 passed。
- `python -m pip check`：No broken requirements found。
- `python -m research_agent`：LangGraph 离线流程完成，保存报告和事件。
- 第一阶段 CLI `python -m cn_research backtest ...`：修正后的引擎生成 Markdown 和 JSON。
- 浏览器实际操作：点击开始研究，看到已完成状态、4 笔成交、每日净值、数据限制和报告链接；刷新后从实验 ID 恢复结果。
- MCP：标准客户端启动真实 stdio 子进程，initialize、list_tools、run_backtest 成功，非法路径调用返回错误。
- 模型：模拟模型和 MockTransport 验证完整请求、工具调用返回、下一轮分析，以及 401/网络错误的回退和密钥不进入结果。

## 演示结果

人工样例 `sample_ashare`：3 只股票、10 个日期，默认 20% 入选比例，初始资金 100 万元。

|指标|结果|
|---|---:|
|扣成本净收益|−4.30%|
|每日最大回撤|5.19%|
|完成交易|4|
|期末持仓|0|
|佣金及印花税|4,326.90 元|

打包交付包含 `outputs/stage2_demo/research_report.md`、JSON 和工具事件。演示文件只证明工程链路能跑通。尚未验证真实 A 股大样本因子表现、外部真实模型、上游全部测试和生产部署。
