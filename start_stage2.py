"""Portable local launcher: python start_stage2.py. No shell activation needed."""
import argparse
from pathlib import Path
import subprocess
import sys
import venv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--install", action="store_true", help="install/update the isolated stage-2 dependencies")
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11+ required")
    if not 1 <= args.port <= 65535:
        raise SystemExit("port must be between 1 and 65535")
    root = Path(__file__).resolve().parent
    env = root / ".venv-stage2"
    python = env / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not python.is_file():
        venv.create(env, with_pip=True)
        args.install = True
    if args.install:
        subprocess.run([str(python), "-m", "pip", "install", "-r", "requirements-stage2-lock.txt"], cwd=root, check=True)
    print(f"Research dashboard: http://127.0.0.1:{args.port}", flush=True)
    subprocess.run([str(python), "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", str(args.port)], cwd=root, check=True)


if __name__ == "__main__":
    main()
