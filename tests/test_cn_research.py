from __future__ import annotations

import pandas as pd
import pytest

from cn_research.backtest import Costs, overnight_reversal, run_backtest
from cn_research.data import normalize_bars


def bars() -> pd.DataFrame:
    return pd.DataFrame([
        {"date": day, "code": code, "open": op, "high": max(op, cl) + 0.1, "low": min(op, cl) - 0.1, "close": cl, "volume": 1000}
        for day, rows in [
            ("2025-01-02", [("000001", 10, 10), ("600000", 20, 20)]),
            ("2025-01-03", [("000001", 9, 9), ("600000", 22, 22)]),
            ("2025-01-06", [("000001", 9, 10), ("600000", 22, 22)]),
            ("2025-01-07", [("000001", 11, 12), ("600000", 22, 22)]),
            ("2025-01-08", [("000001", 12, 12), ("600000", 22, 22)]),
            ("2025-01-09", [("000001", 12, 12), ("600000", 22, 22)]),
        ] for code, op, cl in rows
    ])


def test_factor_uses_prior_close_and_reverses_overnight_return():
    result = overnight_reversal(bars())
    row = result[(result.date == "2025-01-03") & (result.code == "000001")].iloc[0]
    assert row.prev_close == 10
    assert row.overnight_return == pytest.approx(-0.1)
    assert row.factor == pytest.approx(0.1)


def test_backtest_delays_entry_and_observes_t_plus_one():
    result = run_backtest(bars(), quantile=0.5)
    assert result["trades"]
    for trade in result["trades"]:
        assert trade["signal_date"] < trade["entry_date"] < trade["exit_date"]
        assert trade["holding_sessions"] >= 2


def test_costs_reduce_net_return():
    no_cost = run_backtest(bars(), quantile=0.5, costs=Costs(0, 0, 0))
    with_cost = run_backtest(bars(), quantile=0.5, costs=Costs(3, 5, 5))
    assert with_cost["metrics"]["total_return"] < no_cost["metrics"]["total_return"]


def test_normalization_rejects_duplicate_daily_bars():
    frame = bars()
    with pytest.raises(ValueError, match="duplicate"):
        normalize_bars(pd.concat([frame, frame.iloc[[0]]], ignore_index=True))


def test_download_columns_are_normalized():
    frame = bars().rename(columns={"date": "日期", "code": "代码", "open": "开盘", "high": "最高", "low": "最低", "close": "收盘", "volume": "成交量"})
    result = normalize_bars(frame)
    assert {"date", "code", "open", "close"}.issubset(result.columns)


def test_minimum_history_is_enforced():
    with pytest.raises(ValueError, match="four sessions"):
        run_backtest(bars().query("date <= '2025-01-06'"))
