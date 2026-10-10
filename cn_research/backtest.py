from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import numpy as np
import pandas as pd

from cn_research.data import normalize_bars


@dataclass(frozen=True)
class Costs:
    commission_bps: float = 3.0
    stamp_duty_bps: float = 5.0
    slippage_bps: float = 5.0

    def __post_init__(self):
        if any(not math.isfinite(v) or v < 0 for v in asdict(self).values()):
            raise ValueError("costs must be finite and non-negative")
        if self.commission_bps + self.stamp_duty_bps + self.slippage_bps >= 10000:
            raise ValueError("combined costs must be below 10000 bps")


def overnight_reversal(bars: pd.DataFrame) -> pd.DataFrame:
    """Use the preceding dataset session's close, never a stale pre-halt close."""
    df = normalize_bars(bars).sort_values(["code", "date"]).copy()
    sessions = sorted(df.date.unique())
    previous = dict(zip(sessions[1:], sessions[:-1]))
    df["prev_close"] = df.groupby("code")["close"].shift(1)
    prev_dates = df.groupby("code")["date"].shift(1)
    df.loc[prev_dates != df.date.map(previous), "prev_close"] = np.nan
    df["overnight_return"] = df.open / df.prev_close - 1
    df["factor"] = -df.overnight_return
    df.loc[df.volume <= 0, "factor"] = np.nan
    df["factor_rank"] = df.groupby("date")["factor"].rank(method="average", pct=True)
    return df.sort_values(["date", "code"]).reset_index(drop=True)


def _blocked(row: dict | None, side: str) -> str | None:
    if row is None:
        return "missing_bar"
    if row["volume"] <= 0:
        return "suspended"
    limit = row.get("limit_up" if side == "buy" else "limit_down")
    price = row["open"] if side == "buy" else row["close"]
    if limit is not None and pd.notna(limit) and (
        price >= limit * 0.999 if side == "buy" else price <= limit * 1.001
    ):
        return "price_limit"
    return None


def run_backtest(bars: pd.DataFrame, *, quantile: float = 0.2,
                 costs: Costs = Costs(), initial_capital: float = 1_000_000,
                 start: str | None = None, end: str | None = None,
                 quantile_schedule: dict[str, float] | None = None,
                 eligible_codes=None) -> dict:
    """t close signal -> t+1 open buy -> t+2 close sell. Future exits never
    determine entry weights. Blocked sells stay held and retry later; unfilled
    buy slots remain cash. No shorting, leverage or same-day selling.
    """
    if not math.isfinite(quantile) or not 0 < quantile <= 0.5:
        raise ValueError("quantile must be in (0, 0.5]")
    if not math.isfinite(initial_capital) or initial_capital <= 0:
        raise ValueError("initial_capital must be finite and positive")
    df = overnight_reversal(bars)
    sessions = sorted(df.date.unique())
    if start or end:
        sessions = [d for d in sessions if (not start or d >= start) and (not end or d <= end)]
    if quantile_schedule is not None:
        if set(sessions) - set(quantile_schedule):
            raise ValueError("quantile schedule must cover every evaluation session")
        if any(not math.isfinite(q) or not 0 < q <= 0.5 for q in quantile_schedule.values()):
            raise ValueError("invalid scheduled quantile")
    if len(sessions) < 4:
        raise ValueError("at least four sessions are required for signal, entry, and exit")
    by_day = {d: {r["code"]: r for r in rows.to_dict("records")}
              for d, rows in df.groupby("date")}
    positions, marks = {}, {}
    pending = None
    cash = float(initial_capital)
    signals, fills, trades, equity_curve, skipped = [], [], [], [], []
    slip = costs.slippage_bps / 10000
    commission = costs.commission_bps / 10000
    stamp = costs.stamp_duty_bps / 10000

    for i, day in enumerate(sessions):
        rows = by_day[day]
        if pending:
            budget = cash / len(pending["codes"]) if pending["codes"] else 0
            for code in pending["codes"]:
                row = rows.get(code)
                reason = "already_held" if code in positions else _blocked(row, "buy")
                if reason:
                    skipped.append({"date": day, "code": code, "side": "buy", "reason": reason})
                    continue
                price = row["open"] * (1 + slip)
                qty = int(min(budget, cash) / (price * (1 + commission)) / 100) * 100
                if qty == 0:
                    skipped.append({"date": day, "code": code, "side": "buy", "reason": "insufficient_cash_for_lot"})
                    continue
                fee = qty * price * commission
                debit = qty * price + fee
                cash -= debit
                sig = pending["evidence"][code]
                positions[code] = {"code": code, "quantity": qty, "entry_date": day,
                    "entry_index": i, "due_index": i + 1, "entry_open": row["open"],
                    "entry_fill": price, "entry_cost": debit, "signal_date": pending["signal_date"], **sig}
                marks[code] = row["open"]
                fills.append({"date": day, "signal_date": pending["signal_date"], "code": code,
                              "side": "buy", "quantity": qty, "price": price, "commission": fee, "stamp_duty": 0.0})
            pending = None

        for code, pos in list(positions.items()):
            if i < pos["due_index"]:
                continue
            row = rows.get(code)
            reason = _blocked(row, "sell")
            if reason:
                skipped.append({"date": day, "code": code, "side": "sell", "reason": reason})
                continue
            price = row["close"] * (1 - slip)
            turnover = pos["quantity"] * price
            fee, tax = turnover * commission, turnover * stamp
            credit = turnover - fee - tax
            cash += credit
            fills.append({"date": day, "code": code, "side": "sell", "quantity": pos["quantity"],
                          "price": price, "commission": fee, "stamp_duty": tax})
            trades.append({**{k: v for k, v in pos.items() if k not in ("due_index", "entry_index")},
                           "exit_date": day, "exit_close": row["close"], "exit_fill": price,
                           "holding_sessions": i - pos["entry_index"] + 1,
                           "gross_return": row["close"] / pos["entry_open"] - 1,
                           "net_return": credit / pos["entry_cost"] - 1, "pnl": credit - pos["entry_cost"]})
            del positions[code]

        stale = []
        for code in positions:
            if code in rows:
                marks[code] = rows[code]["close"]
            else:
                stale.append(code)
        nav = cash + sum(p["quantity"] * marks[c] for c, p in positions.items())
        equity_curve.append({"date": day, "equity": nav, "cash": cash,
                             "n_positions": len(positions), "stale_marks": stale})
        # Never consult next day's bars when selecting stocks or weights.
        if i >= 1 and i % 2 == 1:
            allowed = eligible_codes(day) if eligible_codes else None
            eligible = [r for r in rows.values() if pd.notna(r["factor"]) and (allowed is None or r["code"] in allowed)]
            eligible.sort(key=lambda r: (-r["factor"], r["code"]))
            active_quantile = quantile_schedule[day] if quantile_schedule is not None else quantile
            selected = eligible[:math.ceil(len(eligible) * active_quantile)]
            pending = {"signal_date": day, "quantile": active_quantile, "codes": [r["code"] for r in selected],
                       "evidence": {r["code"]: {k: r[k] for k in ("factor", "factor_rank", "overnight_return")} for r in selected}}
            signals.append(pending.copy())

    navs = np.array([initial_capital] + [r["equity"] for r in equity_curve])
    daily_returns = navs[1:] / navs[:-1] - 1
    volatility = float(daily_returns.std(ddof=1))
    dd = 1 - navs / np.maximum.accumulate(navs)
    open_positions = [{**{k: v for k, v in p.items() if k not in ("due_index", "entry_index")},
                       "last_mark": marks[c], "market_value": p["quantity"] * marks[c]}
                      for c, p in positions.items()]
    return {
        "engine_version": "0.3.0-event-driven",
        "config": {"quantile": quantile, "initial_capital": initial_capital, "costs": asdict(costs),
                   "signal": "negative(open_t / close_t-1 - 1), top quantile by descending factor",
                   "execution": "signal at t close; buy at t+1 open; sell at t+2 close or retry if blocked",
                   "universe": sorted(df.code.unique()), "lot_size": 100, "start": sessions[0], "end": sessions[-1]},
        "metrics": {"n_cohorts": len({r["signal_date"] for r in trades}), "n_trades": len(trades),
                    "n_open_positions": len(positions), "total_return": navs[-1] / initial_capital - 1,
                    "sharpe_annualized_approx": float(daily_returns.mean() / volatility * np.sqrt(252)) if volatility > 0 else 0.0,
                    "max_drawdown_cohort": float(dd.max()), "max_drawdown_daily": float(dd.max()),
                    "win_rate_cohort": float(np.mean([r["pnl"] > 0 for r in trades])) if trades else 0.0,
                    "win_rate_trade": float(np.mean([r["pnl"] > 0 for r in trades])) if trades else 0.0,
                    "avg_gross_return": float(np.mean([r["gross_return"] for r in trades])) if trades else 0.0,
                    "avg_net_return": float(np.mean([r["net_return"] for r in trades])) if trades else 0.0,
                    "fees_paid": sum(r["commission"] + r["stamp_duty"] for r in fills), "ending_cash": cash},
        "equity_curve": equity_curve, "signals": signals, "fills": fills, "trades": trades,
        "open_positions": open_positions, "skipped_orders": skipped, "cohorts": [],
    }
