from __future__ import annotations

import argparse
import json

from cn_research.backtest import Costs, run_backtest
from cn_research.data import download_akshare, load_csv
from cn_research.report import write_report


def main() -> None:
    parser = argparse.ArgumentParser(description="A-share overnight reversal research MVP")
    sub = parser.add_subparsers(dest="command", required=True)
    dl = sub.add_parser("download", help="download raw daily bars with optional AKShare")
    dl.add_argument("--symbols", required=True, help="comma-separated six-digit codes")
    dl.add_argument("--start", required=True, help="YYYY-MM-DD")
    dl.add_argument("--end", required=True, help="YYYY-MM-DD")
    dl.add_argument("--output", default="data/ashare.csv")
    bt = sub.add_parser("backtest", help="run the factor backtest from normalized CSV")
    bt.add_argument("--data", default="data/sample_ashare.csv")
    bt.add_argument("--output", default="outputs/sample")
    bt.add_argument("--quantile", type=float, default=0.2)
    bt.add_argument("--commission-bps", type=float, default=3.0)
    bt.add_argument("--stamp-duty-bps", type=float, default=5.0)
    bt.add_argument("--slippage-bps", type=float, default=5.0)
    args = parser.parse_args()
    if args.command == "download":
        path = download_akshare([s.strip() for s in args.symbols.split(",") if s.strip()], args.start, args.end, args.output)
        print(f"saved {path}")
        return
    result = run_backtest(load_csv(args.data), quantile=args.quantile, costs=Costs(args.commission_bps, args.stamp_duty_bps, args.slippage_bps))
    md, js = write_report(result, args.output)
    print(json.dumps(result["metrics"], ensure_ascii=False, indent=2))
    print(f"report: {md}\njson: {js}")


if __name__ == "__main__":
    main()
