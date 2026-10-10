from __future__ import annotations
from typing import Any

from mcp.server.fastmcp import FastMCP

from research_agent.settings import DATA_ROOT
from research_agent.tools import ResearchTools


def create_server(tools=None):
    tools = tools or ResearchTools(DATA_ROOT)
    server = FastMCP("A-share Research Tools", instructions="只读 A 股量化研究。样例不代表有效策略，不提供真实交易接口。")

    @server.tool()
    def list_datasets() -> list[dict[str, Any]]:
        """List allowed local datasets; never accepts arbitrary file paths."""
        return tools.list_datasets()

    @server.tool()
    def validate_dataset(dataset_id: str = "sample_ashare") -> dict[str, Any]:
        """Inspect dates, stocks, data gaps and research limitations."""
        return tools.call("validate_dataset", {"dataset_id": dataset_id})

    @server.tool()
    def compute_factor(dataset_id: str = "sample_ashare", as_of: str | None = None, limit: int = 10) -> dict[str, Any]:
        """Point-in-time overnight reversal snapshot for an observed session."""
        return tools.call("compute_factor", {"dataset_id": dataset_id, "as_of": as_of, "limit": limit})

    @server.tool()
    def run_backtest(dataset_id: str = "sample_ashare", quantile: float = 0.2,
                     initial_capital: float = 1_000_000, commission_bps: float = 3,
                     stamp_duty_bps: float = 5, slippage_bps: float = 5) -> dict[str, Any]:
        """Run the same deterministic cash-ledger T+1 backtest used by the API."""
        return tools.call("run_backtest", {"dataset_id": dataset_id, "quantile": quantile,
            "initial_capital": initial_capital, "commission_bps": commission_bps,
            "stamp_duty_bps": stamp_duty_bps, "slippage_bps": slippage_bps})

    @server.tool()
    def compare_costs(dataset_id: str = "sample_ashare", quantile: float = 0.2,
                      commission_bps: float = 3, stamp_duty_bps: float = 5, slippage_bps: float = 5) -> dict[str, Any]:
        """Compare configured execution costs against an otherwise identical zero-cost run."""
        return tools.call("compare_costs", {"dataset_id": dataset_id, "quantile": quantile,
            "commission_bps": commission_bps, "stamp_duty_bps": stamp_duty_bps, "slippage_bps": slippage_bps})

    @server.tool()
    def parameter_sensitivity(dataset_id: str = "sample_ashare", quantiles: list[float] | None = None) -> dict[str, Any]:
        """At most three quantiles on the same data; descriptive only, not validation."""
        return tools.call("parameter_sensitivity", {"dataset_id": dataset_id, "quantiles": quantiles or [0.1, 0.2, 0.5]})

    @server.tool()
    def run_validation_study(dataset_id: str = "sample_stage3", train_sessions: int = 60,
                             test_sessions: int = 20, purge_sessions: int = 2) -> dict[str, Any]:
        """Rolling walk-forward plus bounded sensitivity and same-period benchmarks."""
        return tools.call("run_validation_study", {"dataset_id": dataset_id, "train_sessions": train_sessions,
                          "test_sessions": test_sessions, "purge_sessions": purge_sessions})

    return server


if __name__ == "__main__":
    create_server().run(transport="stdio")
