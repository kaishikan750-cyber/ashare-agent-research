import asyncio
import json
from pathlib import Path
import sys
import time

from fastapi.testclient import TestClient
import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from api.main import create_app
from research_agent.graph import run_research
from research_agent.llm import ModelClient
from research_agent.schemas import ExperimentInput, FactorInput
from research_agent.settings import PROJECT_ROOT
from research_agent.storage import JobStore
from research_agent.tools import ResearchTools


@pytest.fixture
def tools():
    return ResearchTools(PROJECT_ROOT / "data")


def wait_for_job(client, ident):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        job = client.get(f"/api/experiments/{ident}").json()
        if job["status"] in ("completed", "failed"):
            return job
        time.sleep(0.03)
    pytest.fail("job did not finish")


def test_offline_graph_calls_mandatory_tools_and_preserves_evidence(tools):
    events = []
    result = run_research(ExperimentInput(), tools, events.append)
    assert result["summary"]
    assert result["quality"]["n_symbols"] == 3
    assert result["rounds"] == 0
    assert [e["node"] for e in events if e["status"] == "completed"] == ["validate_data", "compute_factor", "run_backtest", "compare_costs", "finish"]


def test_api_background_job_report_persistence_and_static_frontend(tmp_path):
    out = tmp_path / "runs"
    with TestClient(create_app(output_root=out)) as client:
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").status_code == 200
        assert client.get("/api/health").json()["status"] == "ok"
        response = client.post("/api/experiments", json={"dataset_id": "sample_ashare"})
        assert response.status_code == 202
        ident = response.json()["id"]
        job = wait_for_job(client, ident)
        assert job["status"] == "completed", job["error"]
        assert job["result"]["analysis_source"] == "offline"
        assert client.get(f"/api/experiments/{ident}/report").status_code == 200
        report = client.get(f"/api/experiments/{ident}/report?format=json").json()
        assert report["quality"]["sha256"]
        assert client.get(f"/api/experiments/{ident}/report?format=bad").status_code == 422
        assert (out / ident / "research_report.md").is_file()
        assert (out / ident / "input" / "sample_ashare.csv").is_file()
    assert JobStore(out).get(ident)["status"] == "completed"
    with TestClient(create_app(output_root=out)) as client:
        assert client.get(f"/api/experiments/{ident}").json()["status"] == "completed"


def test_api_rejects_invalid_paths_parameters_and_missing_records(tmp_path, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with TestClient(create_app(output_root=tmp_path)) as client:
        assert client.post("/api/experiments", json={"dataset_id": "../../README"}).status_code == 422
        assert client.post("/api/experiments", json={"quantile": 0.8}).status_code == 422
        assert client.post("/api/experiments", json={"dataset_id": "not_there"}).status_code == 404
        assert client.post("/api/experiments", json={"mode": "llm"}).status_code == 400
        assert client.get("/api/experiments/missing").status_code == 404


def test_job_data_failure_is_explicit(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "bad.csv").write_text("date,code,close\n2025-01-02,000001,12\n", encoding="utf-8")
    with TestClient(create_app(data_root=data, output_root=tmp_path / "out")) as client:
        response = client.post("/api/experiments", json={"dataset_id": "bad"})
        job = wait_for_job(client, response.json()["id"])
        assert job["status"] == "failed"
        assert "missing required" in job["error"]
        assert client.get(f"/api/experiments/{job['id']}/report").status_code == 409


def test_factor_snapshot_rejects_non_session(tools):
    with pytest.raises(ValueError, match="session"):
        tools.compute_factor(FactorInput(as_of="2025-01-04"))


def test_dataset_path_rejects_directory_traversal(tmp_path):
    with pytest.raises(ValueError):
        ResearchTools(tmp_path).path("../escape")


class ToolCallingModel:
    def __init__(self):
        self.calls = 0

    def complete(self, messages, tools):
        self.calls += 1
        if self.calls == 1:
            return {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1", "type": "function", "function": {
                "name": "parameter_sensitivity", "arguments": json.dumps({"dataset_id": "untrusted", "quantiles": [0.2, 0.5]})}}]}
        assert messages[-1]["role"] == "tool"
        assert "experiments" in json.loads(messages[-1]["content"])
        return {"role": "assistant", "content": "演示数据的同样本参数比较不证明因子有效。"}


def test_model_tool_loop_is_real_and_scoped_to_current_dataset(tools):
    events, model = [], ToolCallingModel()
    result = run_research(ExperimentInput(mode="llm"), tools, events.append, model=model)
    assert model.calls == 2
    assert result["summary"] == "演示数据的同样本参数比较不证明因子有效。"
    assert any(e.get("tool") == "parameter_sensitivity" and e["status"] == "completed" for e in events)
    assert result["backtest"]["config"]["quantile"] == 0.2


def test_model_failure_preserves_evidence_and_falls_back(tools):
    class FailingModel:
        def complete(self, *_):
            raise RuntimeError("endpoint unavailable")
    result = run_research(ExperimentInput(mode="llm"), tools, model=FailingModel())
    assert result["llm_error"] == "endpoint unavailable"
    assert result["summary"] and result["backtest"]["metrics"]


def test_repeated_model_tools_stop_at_bounded_rounds(tools):
    class RepeatingModel:
        def complete(self, *_):
            return {"role": "assistant", "content": None, "tool_calls": [{"id": "again", "type": "function", "function": {
                "name": "validate_dataset", "arguments": "{}"}}]}
    result = run_research(ExperimentInput(mode="llm"), tools, model=RepeatingModel())
    assert result["rounds"] == 4
    assert result["summary"]


def test_model_http_request_sends_tool_schema_and_redacts_provider_failure(monkeypatch):
    for k, v in {"LLM_BASE_URL": "https://model.example/v1", "LLM_API_KEY": "test-secret", "LLM_MODEL": "test-model"}.items():
        monkeypatch.setenv(k, v)
    def handler(request):
        payload = json.loads(request.content)
        assert payload["tools"][0]["function"]["name"] == "validate_dataset"
        assert request.headers["Authorization"] == "Bearer test-secret"
        return httpx.Response(401, json={"error": "sensitive provider body"})
    original = httpx.Client
    monkeypatch.setattr("research_agent.llm.httpx.Client", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(RuntimeError, match="HTTP 401") as exc:
        ModelClient().complete([], ResearchTools().llm_definitions())
    assert "test-secret" not in str(exc.value) and "sensitive" not in str(exc.value)


def test_real_client_protocol_runs_graph_tool_roundtrip(tools, monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "legacy")
    for k, v in {"LLM_BASE_URL": "https://model.example/v1", "LLM_API_KEY": "test-secret", "LLM_MODEL": "test-model"}.items():
        monkeypatch.setenv(k, v)
    requests = []
    def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        if len(requests) == 1:
            message = {"role": "assistant", "content": None, "tool_calls": [{"id": "costs", "type": "function", "function": {"name": "compare_costs", "arguments": "{}"}}]}
        else:
            assert payload["messages"][-1]["role"] == "tool"
            assert "return_difference" in json.loads(payload["messages"][-1]["content"])
            message = {"role": "assistant", "content": "费用影响组合收益，演示数据不能作为有效性证据。"}
        return httpx.Response(200, json={"choices": [{"message": message}]})
    original = httpx.Client
    monkeypatch.setattr("research_agent.llm.httpx.Client", lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    result = run_research(ExperimentInput(mode="llm"), tools)
    assert len(requests) == 2
    assert result["summary"].startswith("费用影响")
    assert "test-secret" not in json.dumps(result, ensure_ascii=False)


def test_startup_marks_interrupted_experiment_as_failed(tmp_path):
    store = JobStore(tmp_path)
    ident = store.create(ExperimentInput().model_dump(mode="json"))
    store.mark_interrupted()
    job = store.get(ident)
    assert job["status"] == "failed"
    assert "重新提交" in job["error"]


def test_mcp_actual_stdio_discovery_call_and_error():
    async def exercise():
        params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"], cwd=str(PROJECT_ROOT))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                assert {"list_datasets", "validate_dataset", "compute_factor", "run_backtest", "compare_costs", "parameter_sensitivity", "run_validation_study"} == {t.name for t in listed.tools}
                result = await session.call_tool("run_backtest", {"dataset_id": "sample_ashare"})
                assert not result.isError
                data = result.structuredContent
                assert data["metrics"]["n_trades"] > 0
                error = await session.call_tool("compute_factor", {"dataset_id": "../bad"})
                assert error.isError
    asyncio.run(exercise())
