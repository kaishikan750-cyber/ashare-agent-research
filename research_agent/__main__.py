import argparse
import json
import time

from research_agent.schemas import ExperimentInput
from research_agent.service import ResearchService
from research_agent.settings import DATA_ROOT, OUTPUT_ROOT
from research_agent.storage import JobStore
from research_agent.tools import ResearchTools


def main():
    parser = argparse.ArgumentParser(description="Run the LangGraph research pipeline")
    parser.add_argument("--dataset", default="sample_ashare")
    parser.add_argument("--question", default="评估隔夜反转的成本、收益及数据限制。")
    parser.add_argument("--mode", choices=["offline", "llm"], default="offline")
    parser.add_argument("--quantile", type=float, default=0.2)
    args = parser.parse_args()
    svc = ResearchService(ResearchTools(DATA_ROOT), JobStore(OUTPUT_ROOT))
    try:
        ident = svc.submit(ExperimentInput(dataset_id=args.dataset, question=args.question, mode=args.mode, quantile=args.quantile))
        while True:
            job = svc.store.get(ident)
            if job["status"] in ("completed", "failed"):
                break
            time.sleep(0.2)
        if job["status"] == "failed":
            raise SystemExit(job["error"])
        print(json.dumps({"id": ident, "analysis_source": job["result"]["analysis_source"],
              "llm_error": job["result"]["llm_error"], "metrics": job["result"]["backtest"]["metrics"]}, ensure_ascii=False, indent=2))
        print("report:", OUTPUT_ROOT / ident / "research_report.md")
    finally:
        svc.close()


if __name__ == "__main__":
    main()
