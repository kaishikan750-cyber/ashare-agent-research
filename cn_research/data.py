from __future__ import annotations

from pathlib import Path

import pandas as pd
import numpy as np

REQUIRED = {"date", "code", "open", "high", "low", "close", "volume"}


def normalize_bars(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize daily bars to a strict schema and reject ambiguous input."""
    df = frame.rename(columns={str(c): str(c).strip().lower() for c in frame.columns}).copy()
    aliases = {"日期": "date", "代码": "code", "开盘": "open", "最高": "high", "最低": "low", "收盘": "close", "成交量": "volume", "成交额": "amount", "涨停价": "limit_up", "跌停价": "limit_down"}
    df = df.rename(columns={c: aliases[c] for c in df.columns if c in aliases})
    missing = REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f"missing required columns: {', '.join(sorted(missing))}")
    df["date"] = pd.to_datetime(df["date"], errors="raise").dt.strftime("%Y-%m-%d")
    df["code"] = df["code"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
    if df.empty or df.date.isna().any() or not df.code.str.fullmatch(r"\d{6}").all():
        raise ValueError("dataset must contain valid dates and six-digit stock codes")
    for col in ("open", "high", "low", "close", "volume", "amount", "limit_up", "limit_down"):
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if df.duplicated(["date", "code"]).any():
        raise ValueError("duplicate (date, code) bars")
    px = df[["open", "high", "low", "close"]]
    if (not np.isfinite(px.to_numpy()).all() or (px <= 0).any(axis=None)):
        raise ValueError("OHLC values must be present and positive")
    if not np.isfinite(df.volume.to_numpy()).all() or (df.volume < 0).any():
        raise ValueError("volume must be finite and non-negative")
    for col in ("limit_up", "limit_down"):
        if col in df and (not np.isfinite(df[col].dropna().to_numpy()).all() or (df[col].dropna() <= 0).any()):
            raise ValueError(f"{col} must be positive where supplied")
    if ((df["high"] < df[["open", "close", "low"]].max(axis=1)) | (df["low"] > df[["open", "close", "high"]].min(axis=1))).any():
        raise ValueError("inconsistent OHLC bar")
    return df.sort_values(["date", "code"]).reset_index(drop=True)


def load_csv(path: str | Path) -> pd.DataFrame:
    return normalize_bars(pd.read_csv(path, dtype={"code": str}))


def download_akshare(symbols: list[str], start: str, end: str, output: str | Path) -> Path:
    """Download raw (unadjusted) daily bars with AKShare; requires optional dependency."""
    try:
        import akshare as ak
    except ImportError as exc:
        raise RuntimeError("AKShare is optional; install it with `pip install akshare`") from exc
    chunks = []
    for symbol in symbols:
        code = symbol.split(".")[0]
        df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start.replace("-", ""), end_date=end.replace("-", ""), adjust="")
        if df.empty:
            continue
        df["代码"] = code
        chunks.append(df)
    if not chunks:
        raise ValueError("AKShare returned no bars for the requested symbols/date range")
    result = normalize_bars(pd.concat(chunks, ignore_index=True))
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)
    return output
