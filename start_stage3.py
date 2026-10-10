"""python start_stage3.py: isolated install and local service."""
import argparse
from pathlib import Path
import subprocess
import sys
import venv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--study", action="store_true")
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11+ required")
    if not 1 <= args.port <= 65535:
        raise SystemExit("invalid port")
    root = Path(__file__).resolve().parent
    env = root / ".venv-stage3"
    python = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    marker = env / ".stage3-ready"
    if not python.is_file():
        venv.create(env, with_pip=True)
    if args.install or not marker.exists():
        subprocess.run([str(python), "-m", "pip", "install", "-r", "requirements-stage3-lock.txt"], cwd=root, check=True)
        subprocess.run([str(python), "-m", "pip", "check"], cwd=root, check=True)
        marker.write_text("0.3.0", encoding="utf-8")
    command = [str(python), "-m", "research_agent.study_cli"] if args.study else [str(python), "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", str(args.port)]
    if not args.study:
        print(f"Stage 3 dashboard: http://127.0.0.1:{args.port}", flush=True)
    subprocess.run(command, cwd=root, check=True)


if __name__ == "__main__":
    main()
