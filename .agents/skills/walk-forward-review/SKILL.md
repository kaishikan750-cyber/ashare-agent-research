---
name: walk-forward-review
description: Run and interpret this repository's rolling walk-forward, sensitivity grids and stock-pool benchmark comparisons. Use for reproducible out-of-sample research and checking parameter-selection leakage.
---

# 滚动验证与结果解释

执行 `python -m research_agent.study_cli --config configs/study.example.json`，或提交带 `study` 的 `/api/experiments` 请求。MCP `run_validation_study` 提供有界默认协议。仓库内计算实现为 `cn_research/study.py`。

实验参数需在检验前声明。默认固定 60 日训练、20 日测试、2 日间隔、3 个分位、3 个滑点、3 个股票池。实际日期以报告为准。少于 66 日的默认实验会失败；不要通过缩短窗口来冒称统计证据。

读取完整配置、输入哈希和每折 training_candidates：

- 每折选参只使用 train_end 及以前行情，以含成本的训练净收益最大化选择分位，平局取较小分位。训练期末持仓盯市，不强制未来平仓。
- 测试窗不能参与本折选参。后续折使用过去已发生的测试日期作为新的训练历史是合法滚动；这仍不是最终独立 holdout。
- 样本外现金/持仓连续跨窗，不能将独立初始化各折的收益相加。跨窗延期退出继续使用原交易规则，后续参数仅影响新信号。
- sensitivity 是同一测试区间的事后描述。按网格赢家重新包装样本外表现会泄漏；多个股票池事后挑选赢家也有偏差。
- 同池等权基准从样本外首日开盘一次买入，使用相同买入佣金、滑点和 100 股整手；无卖出所以没有卖出印花税。现金基准零利息。比较相同日期的净值和收益差，不冒称风险调整 alpha 或官方指数。
- 读期末未退出仓位、stale_marks 和 skipped_orders；测试尾段不足 4 日会被排除。自动测试和人工数据仅说明工程协议可验证。

报告应保留池与基准总表、每折日期和选择参数、敏感性网格、输入与配置、限制和后续独立验证方案。不得从演示数据推导投资推荐。
