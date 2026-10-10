from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from research_agent.schemas import ExperimentInput, FactorInput
from research_agent.service import ResearchService, report_markdown
from research_agent.settings import DATA_ROOT, OUTPUT_ROOT, PROJECT_ROOT, model_available
from research_agent.storage import JobStore
from research_agent.tools import ResearchTools


def create_app(data_root: Path = DATA_ROOT, output_root: Path = OUTPUT_ROOT):
    @asynccontextmanager
    async def lifespan(app):
        app.state.service = ResearchService(ResearchTools(data_root), JobStore(output_root))
        app.state.service.store.mark_interrupted()
        yield
        app.state.service.close()

    app = FastAPI(title="A-share Research Lab", version="0.3.0", lifespan=lifespan)

    def service(req: Request):
        return req.app.state.service

    def job(req: Request, ident: str):
        try:
            return service(req).store.get(ident)
        except KeyError:
            raise HTTPException(404, "experiment not found") from None

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "0.3.0", "llm_available": model_available(),
                "mode": "local-research"}

    @app.get("/api/datasets")
    def datasets(req: Request):
        return service(req).tools.list_datasets()

    @app.get("/api/datasets/{dataset_id}")
    def dataset(req: Request, dataset_id: str):
        try:
            return service(req).tools.call("validate_dataset", {"dataset_id": dataset_id})
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post("/api/factors")
    def factor(req: Request, payload: FactorInput):
        try:
            return service(req).tools.compute_factor(payload)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post("/api/experiments", status_code=202)
    def submit(req: Request, payload: ExperimentInput):
        if payload.mode == "llm" and not model_available():
            raise HTTPException(400, "Configure LLM_BASE_URL, LLM_API_KEY and LLM_MODEL in .stage2.env first")
        try:
            ident = service(req).submit(payload)
            return {"id": ident, "status": "queued", "url": f"/api/experiments/{ident}"}
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        except RuntimeError as exc:
            raise HTTPException(429, str(exc)) from None

    @app.get("/api/experiments")
    def list_experiments(req: Request):
        return service(req).store.list()

    @app.get("/api/experiments/{ident}")
    def get_experiment(req: Request, ident: str):
        return job(req, ident)

    @app.get("/api/experiments/{ident}/report")
    def report(req: Request, ident: str, format: str = "md"):
        record = job(req, ident)
        if record["status"] != "completed":
            raise HTTPException(409, "report is not ready")
        if format == "json":
            return record["result"]
        if format != "md":
            raise HTTPException(422, "format must be md or json")
        return PlainTextResponse(report_markdown(record["result"]),
                                 headers={"Content-Disposition": f'attachment; filename="research-{ident}.md"'})

    @app.get("/api/experiments/{ident}/study")
    def get_study(req: Request, ident: str, format: str = "json"):
        from cn_research.study import study_markdown
        record = job(req, ident)
        result = (record.get("result") or {}).get("study")
        if not result:
            raise HTTPException(409, "study not requested or not ready")
        if format == "json":
            return result
        if format == "md":
            return PlainTextResponse(study_markdown(result))
        raise HTTPException(422, "format must be md or json")

    @app.get("/")
    def index():
        return FileResponse(PROJECT_ROOT / "frontend" / "index.html")

    app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "frontend"), name="static")
    return app


app = create_app()
