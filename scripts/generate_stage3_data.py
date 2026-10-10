"""Deterministic synthetic daily bars, not historical A-share market data."""
from pathlib import Path
import numpy as np
import pandas as pd


def generate(sessions=182, seed=20261010):
    rng = np.random.default_rng(seed)
    codes = [f"60000{i}" for i in range(1, 7)] + [f"00000{i}" for i in range(1, 7)]
    dates = pd.bdate_range("2025-01-02", periods=sessions).strftime("%Y-%m-%d")
    previous = {c: 10 + i * 2 for i, c in enumerate(codes)}
    records = []
    for day in dates:
        market = rng.normal(0, 0.003)
        for code in codes:
            prev = previous[code]
            gap = rng.normal(0, 0.008)
            op = prev * (1 + gap)
            close = op * (1 + market + rng.normal(0, 0.008))
            records.append(dict(date=day, code=code, open=round(op, 4), high=round(max(op, close) * 1.005, 4),
                                low=round(min(op, close) * .995, 4), close=round(close, 4), volume=1000000,
                                limit_up=round(prev * 1.1, 4), limit_down=round(prev * .9, 4)))
            previous[code] = round(close, 4)
    return pd.DataFrame(records)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    generate().to_csv(root / "data/sample_stage3.csv", index=False)
    print("Synthetic sample_stage3: 182 sessions x 12 symbols; fixed seed 20261010")
