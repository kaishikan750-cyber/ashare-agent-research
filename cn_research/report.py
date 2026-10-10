from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def write_report(result: dict, output_dir: str | Path) -> tuple[Path, Path]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    result = {**result, "generated_at_utc": datetime.now(timezone.utc).isoformat(), "limitations": [
        "仅用于教育与研究；样例为人工数据，不能证明策略有效。",
        "股票池和交易日历由输入文件定义，未重建历史成分、退市股和官方日历。",
        "未处理复权、公司行动和现金分红；涨跌停检测依赖提供 limit_up/limit_down。",
        "固定费用与滑点假设，未考虑最低佣金和市场冲击。印花税需要匹配研究时期。",
        "日线近似成交；缺行情估值沿用旧价格，退出受阻则持仓至可成交日。",
    ]}
    js = out / "research_report.json"
    js.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    m, cfg = result["metrics"], result["config"]
    text = (
        f"# A 股隔夜反转因子研究报告\n\n生成时间（UTC）：{result['generated_at_utc']}\n\n"
        f"引擎：{result['engine_version']}\n\n"
        f"## 研究设定\n\n股票池：{', '.join(cfg['universe'])}\n\n"
        f"范围：{cfg['start']} 至 {cfg['end']}\n\n因子：{cfg['signal']}\n\n执行：{cfg['execution']}\n\n"
        f"入选比例：{cfg['quantile']:.0%}，100 股整手；费用参数：{cfg['costs']}（bps）。\n\n"
        "## 结果\n\n|指标|数值|\n|---|---:|\n"
        f"|净收益（包含期末持仓盯市）|{m['total_return']:.2%}|\n"
        f"|每日最大回撤|{m['max_drawdown_daily']:.2%}|\n"
        f"|日收益近似年化 Sharpe|{m['sharpe_annualized_approx']:.3f}|\n"
        f"|完成交易数|{m['n_trades']}|\n|期末持仓数|{m['n_open_positions']}|\n"
        f"|已退出交易胜率|{m['win_rate_trade']:.2%}|\n"
        f"|平均毛收益 / 已退出交易|{m['avg_gross_return']:.2%}|\n"
        f"|平均净收益 / 已退出交易|{m['avg_net_return']:.2%}|\n"
        f"|佣金与印花税合计|{m['fees_paid']:.2f} 元|\n\n"
        "## 时点与交易约束\n\n"
        "t 收盘形成信号，t+1 开盘买入，t+2 收盘尝试卖出。"
        "买入只依据当前和过去信息，退出受阻不会改变过去的买入名单；买入当天不能卖出。"
        "期末未平仓仓位单列保存，净值含其最新已知估值。完整信号、成交和逐日净值见 JSON。\n\n"
        "## 局限性\n\n" + "\n".join(f"- {x}" for x in result["limitations"]) + "\n"
    )
    md = out / "research_report.md"
    md.write_text(text, encoding="utf-8")
    return md, js
