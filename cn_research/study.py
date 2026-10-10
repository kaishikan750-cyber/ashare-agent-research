"""Chronological research, with one continuous out-of-sample cash ledger."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from cn_research.backtest import Costs, _blocked, run_backtest
from cn_research.data import normalize_bars
from research_agent.schemas import StudyInput, UniverseSpec


def universe_filter(spec: UniverseSpec, observed_codes: list[str]):
    """Membership is checked at signal time, never from later price availability."""
    def at(day):
        if spec.memberships:
            return {m.code for m in spec.memberships if m.known_at.isoformat() <= day
                    and m.effective_from.isoformat() <= day
                    and (m.effective_to is None or day < m.effective_to.isoformat())}
        if spec.selector == "custom":
            return set(spec.codes)
        if spec.selector == "sh_main":
            return {c for c in observed_codes if c.startswith("60")}
        if spec.selector == "sz_main":
            return {c for c in observed_codes if c.startswith(("000", "001", "002"))}
        return set(observed_codes)
    return at


def curve_metrics(curve, initial):
    nav = np.array([initial] + [r["equity"] for r in curve], dtype=float)
    returns = nav[1:] / nav[:-1] - 1
    vol = returns.std(ddof=1) if len(returns) > 1 else 0
    return {"total_return": float(nav[-1] / initial - 1),
            "max_drawdown_daily": float((1 - nav / np.maximum.accumulate(nav)).max()),
            "sharpe_annualized_approx": float(returns.mean() / vol * np.sqrt(252)) if vol > 0 else 0.0}


def buy_and_hold(bars, dates, initial, costs, eligible):
    """One equal-cash allocation at first OOS open; no rebalance or forced exit.

    Missing/blocked entries leave cash. Stale closing marks follow strategy rules.
    The code pool must be declared in advance; current-index members are not PIT data.
    """
    by_day = {d: {r["code"]: r for r in rows.to_dict("records")} for d, rows in bars.groupby("date")}
    cash, holdings, marks, fills = float(initial), {}, {}, []
    codes = sorted(eligible(dates[0]))
    budget = cash / len(codes) if codes else 0
    for code in codes:
        row = by_day[dates[0]].get(code)
        if _blocked(row, "buy"):
            continue
        price = row["open"] * (1 + costs.slippage_bps / 10000)
        qty = int(budget / (price * (1 + costs.commission_bps / 10000)) / 100) * 100
        if not qty:
            continue
        fee = qty * price * costs.commission_bps / 10000
        cash -= qty * price + fee
        holdings[code], marks[code] = qty, row["open"]
        fills.append({"date": dates[0], "code": code, "quantity": qty, "price": price, "commission": fee})
    curve = []
    for day in dates:
        rows = by_day[day]
        stale = []
        for code in holdings:
            if code in rows:
                marks[code] = rows[code]["close"]
            else:
                stale.append(code)
        curve.append({"date": day, "equity": cash + sum(q * marks[c] for c, q in holdings.items()),
                      "cash": cash, "stale_marks": stale})
    return {"metrics": curve_metrics(curve, initial), "equity_curve": curve, "fills": fills,
            "fees_paid": sum(f["commission"] for f in fills),
            "note": "自定义同池等现金买入持有：首个样本外日开盘买入，100 股整手、相同佣金/滑点；不调仓、不卖出、不收卖出印花税，期末盯市。不是官方指数。"}


def fold_plan(dates, args):
    folds = []
    first = args.train_sessions + args.purge_sessions
    for start in range(first, len(dates), args.test_sessions):
        stop = min(start + args.test_sessions, len(dates))
        if stop - start < 4:
            break
        train_end = start - args.purge_sessions  # exclusive
        folds.append({"train_start": dates[train_end - args.train_sessions],
                      "train_end": dates[train_end - 1], "test_start": dates[start], "test_end": dates[stop - 1],
                      "purged_dates": dates[train_end:start], "test_dates": dates[start:stop]})
    if not folds:
        raise ValueError(f"need at least {first + 4} sessions for these walk-forward settings")
    if len(folds) > 20:
        raise ValueError("at most 20 folds; increase test_sessions or reduce date range")
    return folds


def run_study(bars: pd.DataFrame, args: StudyInput, emit=lambda event: None) -> dict:
    df = normalize_bars(bars)
    dates, codes = sorted(df.date.unique()), sorted(df.code.unique())
    if len(df) > 50_000 or len(codes) > 200:
        raise ValueError("stage-3 study budget: at most 50,000 rows / 200 symbols")
    plan = fold_plan(dates, args)
    costs = Costs(args.commission_bps, args.stamp_duty_bps, args.slippage_bps)
    pools = []
    for spec in args.universes:
        eligible = universe_filter(spec, codes)
        windows, schedule = [], {}
        for number, window in enumerate(plan, 1):
            # Physically remove all later bars before training or choosing q.
            prefix = df[df.date <= window["train_end"]]
            candidates = []
            for q in args.quantiles:
                train = run_backtest(prefix, quantile=q, costs=costs, initial_capital=args.initial_capital,
                                     start=window["train_start"], eligible_codes=eligible)
                candidates.append({"quantile": q, "metrics": train["metrics"]})
            best = max(candidates, key=lambda r: (r["metrics"]["total_return"], -r["quantile"]))
            schedule.update({day: best["quantile"] for day in window["test_dates"]})
            windows.append({**{k: v for k, v in window.items() if k != "test_dates"},
                            "fold": number, "selected_quantile": best["quantile"], "training_candidates": candidates})
            emit({"node": "walk_forward", "status": "running", "message": f"{spec.name}: fold {number}/{len(plan)}", "selected_quantile": best["quantile"]})
        start, end = plan[0]["test_start"], plan[-1]["test_end"]
        # Keep cash/positions across parameter changes; no per-fold reset.
        oos = run_backtest(df[df.date <= end], costs=costs, initial_capital=args.initial_capital,
                           start=start, end=end, quantile_schedule=schedule, eligible_codes=eligible)
        oos["config"]["declared_pool"] = spec.model_dump(mode="json")
        curve = oos["equity_curve"]
        for window in windows:
            rows = [r for r in curve if window["test_start"] <= r["date"] <= window["test_end"]]
            previous = [r for r in curve if r["date"] < window["test_start"]]
            base = previous[-1]["equity"] if previous else args.initial_capital
            window["oos_metrics"] = curve_metrics(rows, base)
        benchmark = buy_and_hold(df, [r["date"] for r in curve], args.initial_capital, costs, eligible)
        sensitivity = []
        for q in args.quantiles:
            for slip in args.slippages:
                result = run_backtest(df[df.date <= end], start=start, end=end, quantile=q,
                                     costs=Costs(args.commission_bps, args.stamp_duty_bps, slip),
                                     initial_capital=args.initial_capital, eligible_codes=eligible)
                sensitivity.append({"quantile": q, "slippage_bps": slip, "metrics": result["metrics"]})
        excess_curve = [{"date": r["date"], "strategy": r["equity"] / args.initial_capital,
                         "equal_weight": b["equity"] / args.initial_capital, "cash": 1.0}
                        for r, b in zip(curve, benchmark["equity_curve"])]
        pools.append({"universe": spec.model_dump(mode="json"), "folds": windows, "oos": oos,
                      "benchmark": benchmark, "comparison_curve": excess_curve,
                      "excess_total_return": oos["metrics"]["total_return"] - benchmark["metrics"]["total_return"],
                      "cash_benchmark_return": 0.0, "sensitivity": sensitivity})
    canonical = df.to_csv(index=False).encode()
    from importlib.metadata import version
    import platform
    root = Path(__file__).resolve().parents[1]
    sources = ["cn_research/data.py", "cn_research/backtest.py", "cn_research/study.py", "research_agent/schemas.py"]
    provenance = {"python": platform.python_version(), "packages": {n: version(n) for n in ("numpy", "pandas", "langchain", "langgraph", "mcp")},
                  "source_sha256": {s: hashlib.sha256((root / s).read_bytes()).hexdigest() for s in sources}}
    return {"study_version": "0.3.0", "config": args.model_dump(mode="json"),
            "provenance": provenance,
            "normalized_data_sha256": hashlib.sha256(canonical).hexdigest(), "n_sessions": len(dates),
            "selection_rule": "Rolling fixed train window; maximize cost-adjusted training total return, ties choose smaller quantile. Train marks open positions; no forced exit.",
            "protocol": "At least two purged sessions. Prior bars warm up factors only. First OOS signal after first OOS session; one continuous OOS cash ledger. Window metrics use prior window-end equity. Final <4-day tail is excluded.",
            "warnings": ["人工 sample_stage3 只用于验证链路，不是 A 股策略有效性证据。",
                         "敏感性网格是对同一测试区间的事后描述；不能按其最优值回写 walk-forward。",
                         "多个股票池用于稳健性检查；事后挑选赢家也会造成选择偏差。",
                         "默认 all/沪主板/深主板是文件内固定池，非历史指数成分；历史 membership 的 known_at 和生效区间由用户提供，程序不能验证来源。",
                         "净值盯市、未强制平仓；跨窗持仓按原退出规则继续。日线成交、公司行动、退市和官方日历仍有局限。",
                         "训练可使用当时已发生的历史测试数据；各测试窗对自身参数选择是样本外，但不是最终独立 holdout。"],
            "universes": pools}


def study_markdown(result):
    lines = ["# 第三阶段结构化研究报告", "", f"归一化行情 SHA256：`{result['normalized_data_sha256']}`", "",
             "## 协议", "", result["selection_rule"], "", result["protocol"], "",
             "## 股票池与基准比较", "", "|池|折数|样本外净收益|最大回撤|等权持有收益|收益差|", "|---|---:|---:|---:|---:|---:|"]
    if result.get("source_data_sha256"):
        lines[3:3] = [f"原始 CSV SHA256：`{result['source_data_sha256']}`", ""]
    for pool in result["universes"]:
        m, b = pool["oos"]["metrics"], pool["benchmark"]["metrics"]
        lines.append(f"|{pool['universe']['name']}|{len(pool['folds'])}|{m['total_return']:.2%}|{m['max_drawdown_daily']:.2%}|{b['total_return']:.2%}|{pool['excess_total_return']:.2%}|")
    for pool in result["universes"]:
        lines += ["", f"## {pool['universe']['name']}：walk-forward", "", "|折|训练日期|测试日期|选择分位|测试窗收益|", "|---|---|---|---:|---:|"]
        for f in pool["folds"]:
            lines.append(f"|{f['fold']}|{f['train_start']} ~ {f['train_end']}|{f['test_start']} ~ {f['test_end']}|{f['selected_quantile']}|{f['oos_metrics']['total_return']:.2%}|")
        lines += ["", "### 参数敏感性（事后描述，不用于选参）", "", "|分位|单边滑点 bps|净收益|最大回撤|", "|---:|---:|---:|---:|"]
        for s in pool["sensitivity"]:
            lines.append(f"|{s['quantile']}|{s['slippage_bps']}|{s['metrics']['total_return']:.2%}|{s['metrics']['max_drawdown_daily']:.2%}|")
        lines += ["", pool["benchmark"]["note"]]
    lines += ["", "## 结论与限制", "", "演示运行验证了工程功能。正负收益均不证明因子有效，应先换入可靠真实行情和历史股票池，再冻结协议做独立检验。", ""]
    lines += [f"- {w}" for w in result["warnings"]]
    lines += ["", "## 完整配置", "", "```json", json.dumps(result["config"], ensure_ascii=False, indent=2), "```", ""]
    lines += ["## 运行环境与源码指纹", "", "```json", json.dumps(result["provenance"], ensure_ascii=False, indent=2), "```", ""]
    return "\n".join(lines)


def save_study(result, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "study.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    (directory / "study.md").write_text(study_markdown(result), encoding="utf-8")
    grid = [{"universe": p["universe"]["name"], "quantile": s["quantile"], "slippage_bps": s["slippage_bps"], **s["metrics"]} for p in result["universes"] for s in p["sensitivity"]]
    pd.DataFrame(grid).to_csv(directory / "sensitivity.csv", index=False)
    for p in result["universes"]:
        pd.DataFrame(p["comparison_curve"]).to_csv(directory / f"comparison_{p['universe']['name']}.csv", index=False)
