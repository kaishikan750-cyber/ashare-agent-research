# A 股隔夜反转研究 MVP

这是在 `virattt/ai-hedge-fund` checkout 中新增的独立研究模块。核心回测只依赖 pandas 和 numpy，可独立运行，无需上游模型和行情 API Key。原上游命令仍按其 README 配置数据和模型密钥。数据默认采用原始未复权日线，AKShare 下载是可选功能。

第二阶段已提供浏览器、API、LangGraph 和 MCP，参见 [README_STAGE2.md](README_STAGE2.md)。同时修正了第一阶段用未来退出可成交性过滤买入的缺陷，以下命令默认使用修正后的逐日账本。

## 快速运行

需要 Python 3.11 或更新版本。

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-research.txt
python -m cn_research backtest --data data/sample_ashare.csv --output outputs/sample
```

完成后查看 `outputs/sample/research_report.md` 和 `outputs/sample/research_report.json`。样例数据是演示数据，不能用于判断策略是否有效。

## 获取 A 股日线数据

安装可选数据源并下载：

```powershell
python -m pip install akshare
python -m cn_research download --symbols 000001,600000,600519 --start 2024-01-01 --end 2025-12-31 --output data/ashare.csv
python -m cn_research backtest --data data/ashare.csv --output outputs/ashare
```

数据格式接受 `date,code,open,high,low,close,volume`；也能读取 AKShare 常见中文列名。若数据源提供 `limit_up` 和 `limit_down`，回测会过滤开盘即封涨跌停、无法成交的买卖单。代码内部保留六位股票代码。

## 因子与时点

隔夜收益为 `open_t / close_(t-1) - 1`，反转因子为其相反数，并在每天对股票做横截面百分位排序。当前原型做多因子排名最高的分位组。

因子在 t 日开盘后才完整可知，因此回测在 t 日形成信号、t+1 日开盘买入、t+2 日收盘卖出。买入日至少跨过一个交易日后才退出，满足 A 股 T+1；没有假设使用信号日开盘成交。

成本默认：买卖佣金各 3 bps、卖出印花税 5 bps、每边滑点 5 bps。可用命令行参数调整。按 100 股整手买入，每次信号分配当前现金。退出受阻时继续持有，不根据未来退出行情改变买入名单。

## 测试

```powershell
python -m pytest tests/test_cn_research.py -q
```

## 研究限制

- 默认样例只验证工程链路；请用足够长的真实行情和事先定义的股票池重新评估。
- AKShare 返回字段和可用性会变化，下载结果需审计并缓存。
- 需要使用点时点股票池和退市股票数据，避免幸存者偏差。
- 复权口径、分红送转、ST、停牌、涨跌停、退市处理会显著影响结论。
- 涨跌停过滤依赖数据源提供的当日限制价格字段；当前 AKShare 下载接口未自动拼接该字段。
- Sharpe 使用每日净值收益近似年化，报告没有声称统计显著。
- 项目仅用于教育与研究，不构成投资建议。

## 上游项目

原项目：<https://github.com/virattt/ai-hedge-fund>，采用 MIT License。本目录中的 A 股研究代码作为附加模块，原上游代码和署名保留。
