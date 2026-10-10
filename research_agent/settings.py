from pathlib import Path
import os

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".stage3.env", override=False)
load_dotenv(PROJECT_ROOT / ".stage2.env", override=False)
DATA_ROOT = Path(os.environ.get("CN_DATA_ROOT", str(PROJECT_ROOT / "data"))).resolve()
OUTPUT_ROOT = Path(os.environ.get("CN_OUTPUT_ROOT", str(PROJECT_ROOT / "outputs" / "stage3"))).resolve()


def model_available() -> bool:
    return all(os.environ.get(key) for key in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"))
