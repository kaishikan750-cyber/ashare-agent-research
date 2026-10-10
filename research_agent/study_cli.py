import argparse
import json
from pathlib import Path

from cn_research.study import run_study, save_study
from research_agent.schemas import StudyInput
from research_agent.tools import ResearchTools


def main():
    parser = argparse.ArgumentParser(description="Reproducible stage-3 study")
    parser.add_argument("--dataset", default="sample_stage3")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path, default=Path("outputs/stage3_demo"))
    args = parser.parse_args()
    payload = json.loads(args.config.read_text(encoding="utf-8")) if args.config else {"dataset_id": args.dataset}
    config = StudyInput.model_validate(payload)
    tools = ResearchTools()
    result = run_study(tools.frame(config.dataset_id), config)
    result["source_data_sha256"] = tools.validate_dataset(config)["sha256"]
    if config.dataset_id != "sample_stage3":
        result["warnings"][0] = "真实数据口径须由使用者核对；工具运行成功不证明因子有效。"
    save_study(result, args.output)
    print(args.output.resolve())
    for pool in result["universes"]:
        print(pool["universe"]["name"], pool["oos"]["metrics"]["total_return"], len(pool["folds"]))


if __name__ == "__main__":
    main()
