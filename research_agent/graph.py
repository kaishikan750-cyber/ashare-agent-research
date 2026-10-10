from __future__ import annotations

import json
from research_agent.skills import skill_context
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from research_agent.llm import ModelClient, SYSTEM
from research_agent.schemas import DatasetInput, FactorInput, BacktestInput, ExperimentInput, StudyInput
from research_agent.tools import ResearchTools


class ResearchState(TypedDict, total=False):
    request: dict
    quality: dict
    factor: dict
    backtest: dict
    cost_comparison: dict
    messages: list[dict]
    rounds: int
    summary: str
    llm_error: str | None
    study: dict | None


def build_graph(tools: ResearchTools, emit=lambda event: None, model=None):
    """Mandatory evidence pipeline plus an optional bounded tool-calling loop.

    No model can edit the authoritative backtest/configuration. State snapshots
    contain research evidence only, never credentials or DataFrames.
    """
    if model is None:
        import os
        from research_agent.langchain_runtime import LangChainModelClient
        model = ModelClient() if os.environ.get("LLM_BACKEND") == "legacy" else LangChainModelClient()

    def base(state):
        return BacktestInput.model_validate({k: v for k, v in state["request"].items() if k not in ("question", "mode", "study")})

    def validate(state):
        emit({"node": "validate_data", "status": "running", "message": "检查数据结构、交易日和缺口"})
        result = tools.call("validate_dataset", {"dataset_id": state["request"]["dataset_id"]})
        emit({"node": "validate_data", "status": "completed", "output": result})
        return {"quality": result}

    def factor(state):
        result = tools.call("compute_factor", {"dataset_id": state["request"]["dataset_id"]})
        emit({"node": "compute_factor", "status": "completed", "output": result})
        return {"factor": result}

    def backtest(state):
        emit({"node": "run_backtest", "status": "running", "message": "执行 T+1 现金与持仓回测"})
        result = tools.full_backtest(base(state))
        emit({"node": "run_backtest", "status": "completed", "output": result["metrics"]})
        return {"backtest": result}

    def costs(state):
        args = base(state).model_copy(update={"commission_bps": 0, "stamp_duty_bps": 0, "slippage_bps": 0})
        free = tools.full_backtest(args)["metrics"]
        comparison = {"configured": state["backtest"]["metrics"], "zero_cost": free,
                      "return_difference": state["backtest"]["metrics"]["total_return"] - free["total_return"],
                      "note": "成本改变费用和整手数量；这不是样本外检验。"}
        emit({"node": "compare_costs", "status": "completed", "output": comparison})
        evidence = {"quality": state["quality"], "factor": state["factor"],
                    "config": state["backtest"]["config"], "metrics": state["backtest"]["metrics"],
                    "cost_comparison": comparison}
        return {"cost_comparison": comparison, "rounds": 0,
                "messages": [{"role": "system", "content": SYSTEM + "\n" + skill_context()},
                             {"role": "user", "content": state["request"]["question"] + "\n证据：" + json.dumps(evidence, ensure_ascii=False)}]}

    def analyst(state):
        if state["request"]["mode"] == "offline":
            return {}
        emit({"node": "analyst", "status": "running", "message": "模型根据证据分析并选择研究工具"})
        try:
            message = model.complete(state["messages"], tools.llm_definitions())
            if not message.get("tool_calls") and not message.get("content"):
                raise RuntimeError("empty model response")
            return {"messages": state["messages"] + [message], "rounds": state["rounds"] + 1}
        except (ValueError, RuntimeError) as exc:
            emit({"node": "analyst", "status": "failed", "message": str(exc)})
            return {"llm_error": str(exc)}

    def validate_study(state):
        config = state["request"].get("study")
        if config is None:
            return {"study": None}
        emit({"node": "validation_study", "status": "running", "message": "执行滚动样本外验证、敏感性与基准比较"})
        result = tools.validation_study(StudyInput(**base(state).model_dump(), **config))
        emit({"node": "validation_study", "status": "completed", "output": {
            p["universe"]["name"]: p["oos"]["metrics"] for p in result["universes"]}})
        # Send compact evidence, never all fills/curves, to a configured model.
        evidence = {"walk_forward": [{"pool": p["universe"]["name"], "metrics": p["oos"]["metrics"],
                    "benchmark": p["benchmark"]["metrics"], "folds": len(p["folds"])} for p in result["universes"]],
                    "warnings": result["warnings"]}
        messages = list(state["messages"])
        messages[-1] = {**messages[-1], "content": messages[-1]["content"] + "\n第三阶段证据：" + json.dumps(evidence, ensure_ascii=False)}
        return {"study": result, "messages": messages}

    def tool_node(state):
        messages = list(state["messages"])
        for call in messages[-1].get("tool_calls", []):
            name = "invalid_tool"
            try:
                name = call["function"]["name"]
                if name not in {d["function"]["name"] for d in tools.llm_definitions()}:
                    raise ValueError("tool is not available to model; studies require explicit job configuration")
                arguments = json.loads(call["function"]["arguments"])
                if not isinstance(arguments, dict):
                    raise ValueError("arguments must be an object")
                # Scope every tool to this job's snapshot; no LLM-chosen files.
                arguments["dataset_id"] = state["request"]["dataset_id"]
                output = tools.call(name, arguments)
                emit({"node": "agent_tool", "tool": name, "status": "completed", "output": output})
            except (KeyError, TypeError, ValueError, FileNotFoundError) as exc:
                output = {"error": str(exc)[:500]}
                emit({"node": "agent_tool", "tool": name, "status": "failed", "output": output})
            messages.append({"role": "tool", "tool_call_id": call.get("id", "invalid"),
                             "content": json.dumps(output, ensure_ascii=False)})
        return {"messages": messages}

    def route(state):
        if state["request"]["mode"] == "offline" or state.get("llm_error"):
            return "finish"
        if state["messages"][-1].get("tool_calls"):
            return "tools" if state["rounds"] <= 3 else "finish"
        return "finish"

    def finish(state):
        m = state["backtest"]["metrics"]
        last = state["messages"][-1]
        if state["request"]["mode"] == "llm" and last.get("role") == "assistant" and last.get("content") and not last.get("tool_calls"):
            summary = str(last["content"])
        else:
            summary = (f"已完成 {m['n_trades']} 笔退出交易，期末仍持有 {m['n_open_positions']} 个仓位。"
                       f"逐日盯市净收益 {m['total_return']:.2%}，最大回撤 {m['max_drawdown_daily']:.2%}。"
                       f"手续费合计 {m['fees_paid']:.2f} 元。信号收盘后形成，次日开盘买入，至少下一交易日才可卖出。"
                       "结果仅说明当前文件中的历史表现，不证明因子有效。建议补充真实数据、历史股票池和样本外验证。")
            if state.get("study"):
                pools = state["study"]["universes"]
                summary += "本实验已按预设协议执行 walk-forward：" + "；".join(
                    f"{p['universe']['name']} {len(p['folds'])} 折，样本外净收益 {p['oos']['metrics']['total_return']:.2%}"
                    for p in pools) + "。敏感性网格仅用于事后描述，不能据此重新选择样本外参数。"
        emit({"node": "finish", "status": "completed", "message": "研究报告已生成"})
        return {"summary": summary}

    graph = StateGraph(ResearchState)
    for name, fn in [("validate_data", validate), ("compute_factor", factor), ("run_backtest", backtest),
                     ("compare_costs", costs), ("validation_study", validate_study), ("analyst", analyst), ("tools", tool_node), ("finish", finish)]:
        graph.add_node(name, fn)
    graph.add_edge(START, "validate_data")
    for a, b in [("validate_data", "compute_factor"), ("compute_factor", "run_backtest"),
                 ("run_backtest", "compare_costs"), ("compare_costs", "validation_study"), ("validation_study", "analyst"), ("tools", "analyst"), ("finish", END)]:
        graph.add_edge(a, b)
    graph.add_conditional_edges("analyst", route, {"tools": "tools", "finish": "finish"})
    return graph.compile()


def run_research(request: ExperimentInput, tools: ResearchTools, emit=lambda event: None, model=None):
    return build_graph(tools, emit, model).invoke({"request": request.model_dump(mode="json")}, {"recursion_limit": 20})
