from __future__ import annotations

import hashlib
from pathlib import Path

from cn_research.backtest import Costs, overnight_reversal, run_backtest
from cn_research.data import load_csv
from research_agent.schemas import DatasetInput, FactorInput, BacktestInput, SensitivityInput, StudyInput
from research_agent.settings import DATA_ROOT

MAX_ROWS = 200_000
MAX_BYTES = 30_000_000


class ResearchTools:
    """Shared allowlisted, read-only tool surface for graph, HTTP and MCP."""

    def __init__(self, data_root: Path = DATA_ROOT):
        self.data_root = Path(data_root).resolve()
        self.specs = {
            "validate_dataset": (DatasetInput, self.validate_dataset, "Inspect dataset dates, symbols, gaps and known limitations."),
            "compute_factor": (FactorInput, self.compute_factor, "Compute a bounded, point-in-time overnight reversal snapshot."),
            "run_backtest": (BacktestInput, self.run_backtest, "Run the deterministic T+1 cash-ledger backtest; returns metrics and counts."),
            "compare_costs": (BacktestInput, self.compare_costs, "Compare the same strategy with configured fees versus zero fees."),
            "parameter_sensitivity": (SensitivityInput, self.parameter_sensitivity, "Compare at most three quantiles; descriptive, not out-of-sample validation."),
            "run_validation_study": (StudyInput, self.validation_study, "Rolling walk-forward, descriptive sensitivity, declared stock pools and same-period benchmarks. Bounded to 20 folds."),
        }

    def path(self, dataset_id: str) -> Path:
        DatasetInput(dataset_id=dataset_id)
        path = (self.data_root / f"{dataset_id}.csv").resolve()
        if path.parent != self.data_root:
            raise ValueError("dataset must be a direct child of DATA_ROOT")
        if not path.is_file():
            raise FileNotFoundError(f"dataset not found: {dataset_id}")
        if path.stat().st_size > MAX_BYTES:
            raise ValueError("dataset exceeds 30 MB MVP limit")
        return path

    def frame(self, dataset_id):
        df = load_csv(self.path(dataset_id))
        if len(df) > MAX_ROWS:
            raise ValueError("dataset exceeds 200,000-row MVP limit")
        return df

    def list_datasets(self) -> list[dict]:
        result = []
        for p in sorted(self.data_root.glob("*.csv")):
            try:
                self.path(p.stem)
                result.append({"id": p.stem, "bytes": p.stat().st_size,
                               "is_demo": p.stem in {"sample_ashare", "sample_stage3"}})
            except (ValueError, FileNotFoundError):
                continue
        return result

    def validate_dataset(self, args: DatasetInput) -> dict:
        df = self.frame(args.dataset_id)
        n_days, n_codes = df.date.nunique(), df.code.nunique()
        warnings = [
            "股票池由当前文件定义，未重建历史成分和退市股票，可能有幸存者偏差。",
            "交易日由文件中日期的并集定义，未连接交易所官方日历。",
            "未处理公司行动、现金分红、最低佣金及成交量约束；成交价格为日线近似。",
            "固定印花税率应匹配研究时期；跨税制变更的历史研究需要分段处理。",
        ]
        if args.dataset_id in {"sample_ashare", "sample_stage3"}:
            warnings.insert(0, "这是人工演示数据，只用于验证工程链路，不能证明因子有效。")
        if n_days < 60:
            warnings.append("少于 60 个观测交易日，统计结果不稳定。")
        if n_codes < 10:
            warnings.append("股票池少于 10 只，分位组比较缺乏代表性。")
        gaps = int(n_days * n_codes - len(df))
        if gaps:
            warnings.append(f"存在 {gaps} 个股票/日期缺口；买单跳过，卖单延期，缺行情时沿用旧估值。")
        has_limits = all(c in df and df[c].notna().all() for c in ("limit_up", "limit_down"))
        if not has_limits:
            warnings.append("缺少完整涨跌停价格，无法完整模拟封板限制。")
        return {"dataset_id": args.dataset_id, "sha256": hashlib.sha256(self.path(args.dataset_id).read_bytes()).hexdigest(),
                "n_rows": len(df), "n_sessions": n_days, "n_symbols": n_codes,
                "start": df.date.min(), "end": df.date.max(), "symbols": sorted(df.code.unique()),
                "missing_stock_sessions": gaps, "has_limit_prices": has_limits, "warnings": warnings}

    def compute_factor(self, args: FactorInput) -> dict:
        df = self.frame(args.dataset_id)
        as_of = args.as_of.isoformat() if args.as_of else df.date.max()
        df = df[df.date <= as_of]
        if df.empty or as_of not in set(df.date):
            raise ValueError("as_of must be a session present in the dataset")
        factors = overnight_reversal(df)
        current = factors[(factors.date == as_of) & factors.factor.notna()]
        current = current.sort_values(["factor", "code"], ascending=[False, True])
        return {"as_of": as_of, "definition": "-(open_t / close_t-1 - 1)",
                "rows": current[["code", "prev_close", "open", "overnight_return", "factor", "factor_rank"]].head(args.limit).to_dict("records")}

    def full_backtest(self, args: BacktestInput) -> dict:
        return run_backtest(self.frame(args.dataset_id), quantile=args.quantile,
                            initial_capital=args.initial_capital,
                            costs=Costs(args.commission_bps, args.stamp_duty_bps, args.slippage_bps))

    def run_backtest(self, args: BacktestInput) -> dict:
        result = self.full_backtest(args)
        return {"config": result["config"], "metrics": result["metrics"],
                "engine_version": result["engine_version"], "n_fills": len(result["fills"]),
                "n_skipped_orders": len(result["skipped_orders"])}

    def compare_costs(self, args: BacktestInput) -> dict:
        net = self.full_backtest(args)["metrics"]
        free = self.full_backtest(args.model_copy(update={"commission_bps": 0, "stamp_duty_bps": 0, "slippage_bps": 0}))["metrics"]
        return {"configured": net, "zero_cost": free,
                "return_difference": net["total_return"] - free["total_return"],
                "note": "成本也会改变可买整手数量；该差值不是纯费用账单。"}

    def parameter_sensitivity(self, args: SensitivityInput) -> dict:
        base = args.model_dump(exclude={"quantiles"})
        return {"experiments": [{"quantile": q, "metrics": self.full_backtest(BacktestInput(**{**base, "quantile": q}))["metrics"]} for q in args.quantiles],
                "note": "同样本描述性比较，不构成样本外验证，不自动选择最优参数。"}

    def call(self, name: str, arguments: dict) -> dict:
        if name not in self.specs:
            raise ValueError(f"unknown tool: {name}")
        # Same validation and execution boundary for Agent, API and MCP.
        return self.langchain_tools()[name].invoke(arguments)

    def langchain_tools(self):
        from research_agent.langchain_runtime import structured_tools
        return structured_tools(self)

    def validation_study(self, args: StudyInput):
        from cn_research.study import run_study
        result = run_study(self.frame(args.dataset_id), args)
        result["source_data_sha256"] = hashlib.sha256(self.path(args.dataset_id).read_bytes()).hexdigest()
        if args.dataset_id != "sample_stage3":
            result["warnings"][0] = "工具运行成功不证明因子有效；真实数据来源和口径须核对。"
        return result

    def llm_definitions(self) -> list[dict]:
        from research_agent.langchain_runtime import tool_definitions
        # The full study is an explicit job configuration, not an unbounded LLM action.
        return [t for t in tool_definitions(self) if t["function"]["name"] != "run_validation_study"]
