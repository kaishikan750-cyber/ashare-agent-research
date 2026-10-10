from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
from threading import BoundedSemaphore

from research_agent.graph import run_research
from research_agent.schemas import ExperimentInput
from research_agent.storage import JobStore, now
from research_agent.tools import ResearchTools


def report_markdown(result: dict) -> str:
    from cn_research.study import study_markdown
    r, m = result["request"], result["backtest"]["metrics"]
    quality = result["quality"]
    return (f"# A 股隔夜反转研究报告\n\n实验：{result['id']}\n\n"
            f"数据：{r['dataset_id']} · {quality['start']} 至 {quality['end']} · {quality['n_symbols']} 只股票\n\n"
            f"SHA256：{quality['sha256']}\n\n"
            f"模式：{result['analysis_source']}\n\n问题：{r['question']}\n\n"
            f"## 研究结论\n\n{result['summary']}\n\n"
            f"## 确定性计算结果\n\n|指标|数值|\n|---|---:|\n"
            f"|净收益（含未退出持仓盯市）|{m['total_return']:.2%}|\n"
            f"|日收益近似年化 Sharpe|{m['sharpe_annualized_approx']:.3f}|\n"
            f"|每日最大回撤|{m['max_drawdown_daily']:.2%}|\n"
            f"|完成交易 / 期末持仓|{m['n_trades']} / {m['n_open_positions']}|\n"
            f"|佣金与印花税|{m['fees_paid']:.2f} 元|\n\n"
            "## 执行与假设\n\n"
            "t 收盘形成信号，t+1 开盘买入，t+2 收盘尝试卖出。禁止同日卖出、做空与杠杆。"
            "每次信号选择 top ceil(N×quantile)，并按 100 股整手买入；买入失败的资金留在现金中。"
            "卖出受阻则保留持仓并重试，期末不强制平仓；缺行情持仓沿用旧估值并记录。\n\n"
            f"参数：quantile={r['quantile']}，佣金={r['commission_bps']} bps，印花税={r['stamp_duty_bps']} bps，滑点={r['slippage_bps']} bps。\n\n"
            "## 成本对照\n\n"
            f"零成本净收益：{result['cost_comparison']['zero_cost']['total_return']:.2%}。"
            "成本会改变费用及可买整手数量，此差值不是纯费用清单。\n\n"
            "## 数据限制\n\n" + "\n".join(f"- {w}" for w in quality['warnings']) +
            "\n\n工具输出是事实来源；模型文字仅为分析，不代表策略有效性证据。\n" +
            ("\n\n" + study_markdown(result["study"]) if result.get("study") else ""))


class ResearchService:
    def __init__(self, tools: ResearchTools, store: JobStore):
        self.tools, self.store = tools, store
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cn-research")
        self.slots = BoundedSemaphore(8)

    def submit(self, request: ExperimentInput) -> str:
        # Reject invalid/missing datasets immediately rather than returning a broken job.
        self.tools.path(request.dataset_id)
        if not self.slots.acquire(blocking=False):
            raise RuntimeError("research queue full; retry later")
        try:
            ident = self.store.create(request.model_dump(mode="json"))
            self.pool.submit(self.execute, ident, request)
            return ident
        except Exception:
            self.slots.release()
            raise

    def execute(self, ident: str, request: ExperimentInput):
        self.store.update(ident, "running")
        try:
            # Snapshot data per job; later local CSV changes cannot alter its evidence.
            directory = self.store.root / ident
            inputs = directory / "input"
            inputs.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self.tools.path(request.dataset_id), inputs / f"{request.dataset_id}.csv")
            state = run_research(request, ResearchTools(inputs), emit=lambda event: self.store.event(ident, event))
            analysis_source = "llm" if request.mode == "llm" and not state.get("llm_error") and not state["messages"][-1].get("tool_calls") else "offline"
            result = {"id": ident, "generated_at": now(), "request": request.model_dump(mode="json"),
                      "skills": ["ashare-data-audit", "walk-forward-review"],
                      "tool_runtime": "LangChain StructuredTool", "model_backend": os.environ.get("LLM_BACKEND", "langchain"),
                      "analysis_source": analysis_source, "summary": state["summary"],
                      "llm_error": state.get("llm_error"), "llm_rounds": state["rounds"],
                      **{k: state[k] for k in ("quality", "factor", "backtest", "cost_comparison", "study")}}
            if request.mode == "llm" and analysis_source == "offline" and not result["llm_error"]:
                result["llm_error"] = "模型达到工具调用轮数上限，使用规则报告。"
            text = report_markdown(result)
            (directory / "research_report.md").write_text(text, encoding="utf-8")
            (directory / "research_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
            if result.get("study"):
                from cn_research.study import save_study
                save_study(result["study"], directory / "study")
            self.store.update(ident, "completed", result=result)
        except Exception as exc:
            # Infrastructure failures are explicit, never silently interpreted as no signal.
            error = str(exc)[:1000] if isinstance(exc, (ValueError, FileNotFoundError)) else f"research execution failed ({type(exc).__name__})"
            self.store.event(ident, {"node": "error", "status": "failed", "message": error})
            self.store.update(ident, "failed", error=error)
        finally:
            self.slots.release()

    def close(self):
        self.pool.shutdown(wait=True)
