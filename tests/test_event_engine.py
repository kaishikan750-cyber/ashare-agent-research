import numpy as np
import pytest

from test_cn_research import bars
from cn_research.backtest import Costs, overnight_reversal, run_backtest
from cn_research.data import normalize_bars


def test_future_missing_exit_does_not_rewrite_past_selection_or_fills():
    original = bars()
    changed = original[~((original.date == "2025-01-07") & (original.code == "000001"))]
    a, b = run_backtest(original, quantile=0.5), run_backtest(changed, quantile=0.5)
    assert a["signals"][0] == b["signals"][0]
    assert [r for r in a["fills"] if r["date"] <= "2025-01-06"] == [r for r in b["fills"] if r["date"] <= "2025-01-06"]
    assert b["trades"][0]["exit_date"] == "2025-01-08"
    assert b["skipped_orders"][0]["reason"] == "missing_bar"


def test_future_price_mutation_cannot_affect_past_nav_or_signal():
    original = bars()
    altered = original.copy()
    altered.loc[altered.date > "2025-01-06", ["open", "high", "low", "close"]] *= 5
    a, b = run_backtest(original), run_backtest(altered)
    assert a["signals"][0] == b["signals"][0]
    assert a["equity_curve"][:3] == b["equity_curve"][:3]


def test_failed_buy_allocation_stays_cash_no_replacement():
    frame = bars()
    frame.loc[(frame.date == "2025-01-06") & (frame.code == "000001"), "volume"] = 0
    result = run_backtest(frame)
    assert not [r for r in result["fills"] if r["date"] == "2025-01-06"]
    assert result["equity_curve"][2]["cash"] == 1_000_000
    assert result["skipped_orders"][0]["reason"] == "suspended"


def test_sell_limit_checks_close_not_open_and_retains_position():
    frame = bars().query("date <= '2025-01-07'").copy()
    frame["limit_down"] = np.nan
    frame.loc[(frame.date == "2025-01-07") & (frame.code == "000001"), "limit_down"] = 12
    result = run_backtest(frame)
    assert result["metrics"]["n_open_positions"] == 1
    assert result["metrics"]["n_trades"] == 0
    assert result["skipped_orders"][-1]["reason"] == "price_limit"
    assert result["open_positions"][0]["market_value"] > 0


def test_cash_book_reconciles_and_fills_are_round_lots():
    result = run_backtest(bars())
    cash = result["config"]["initial_capital"]
    holdings = {}
    for fill in result["fills"]:
        assert fill["quantity"] % 100 == 0
        gross = fill["quantity"] * fill["price"]
        if fill["side"] == "buy":
            cash -= gross + fill["commission"]
            holdings[fill["code"]] = fill["date"]
        else:
            assert holdings[fill["code"]] < fill["date"]
            cash += gross - fill["commission"] - fill["stamp_duty"]
            del holdings[fill["code"]]
    assert cash == pytest.approx(result["metrics"]["ending_cash"])
    assert all(row["cash"] >= -1e-6 for row in result["equity_curve"])


def test_factor_does_not_use_stale_pre_halt_close():
    frame = bars()
    frame = frame[~((frame.date == "2025-01-03") & (frame.code == "000001"))]
    factor = overnight_reversal(frame)
    row = factor[(factor.date == "2025-01-06") & (factor.code == "000001")].iloc[0]
    assert np.isnan(row.factor)


@pytest.mark.parametrize("column,value", [("close", np.inf), ("volume", np.nan), ("volume", -1)])
def test_invalid_numeric_input_is_rejected(column, value):
    frame = bars()
    frame[column] = frame[column].astype(float)
    frame.loc[0, column] = value
    with pytest.raises(ValueError):
        normalize_bars(frame)


def test_nonfinite_costs_are_rejected():
    with pytest.raises(ValueError):
        Costs(slippage_bps=np.nan)
