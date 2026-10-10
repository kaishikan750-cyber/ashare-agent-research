---
name: ashare-data-audit
description: Audit A-share daily-bar inputs, factor timing, price limits and historical stock pools before this repository's overnight-reversal research. Use for dataset reviews and backtest evidence checks.
---

# A 股数据与时间线审计

在本仓库使用 `validate_dataset` 和指定 `as_of` 的 `compute_factor` 核对数据。工具均只读，可通过 LangChain 注册表或 MCP 调用。输入使用 dataset_id，不接受任意路径。

对报告有实质影响的检查：

- 因子定义为 `-(open_t / close_{t-1} - 1)`；前收盘必须来自紧邻的数据集交易日。停牌缺口不沿用旧收盘生成信号。
- 该项目在 t 收盘形成信号，t+1 开盘买入，t+2 收盘尝试退出。不可描述成同日开盘套利。封板/缺行情的退出必须继续持仓，不能据未来能否退出过滤买入名单。
- 比较数据 SHA256、日期覆盖、股票/日期缺口、volume 和 limit_up/limit_down。缺完整涨跌停价格时，不得声称已完整处理涨跌停。
- `sample_ashare` 和 `sample_stage3` 都是人工演示数据。后者的工作日索引不是交易所日历；正负收益都不能用于 A 股经济结论。
- 默认股票池由文件内代码定义。沪主板/深主板是代码前缀规则，不是沪深 300/中证 500。当前指数成分不能替代历史股票池。自定义 memberships 必须核对 known_at 与生效区间的原始来源。
- 未处理公司行动、分红、最低佣金、成交量冲击、历史税制和退市。不要把收益差命名为显著 alpha。

输出可追溯的数据口径、检查结果及影响；数值来自工具，无法检查的来源问题明确保留。代码定位：`cn_research/data.py`、`cn_research/backtest.py`、`research_agent/tools.py`。
