"""Bundle runnable source and a verified demo, without Git, secrets or virtualenvs."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]


def package():
    output = ROOT.parent / "ai-hedge-fund-cn-stage2.zip"
    folders = ["cn_research", "research_agent", "api", "frontend", "mcp_server", "tests", "data", "docs", "hedge_fund", "assets", "scripts", ".github"]
    files = ["README.md", "README_STAGE2.md", "README_CN_RESEARCH.md", "LICENSE", "pyproject.toml", "poetry.lock", "requirements-research.txt", "requirements-stage2.txt", "requirements-stage2-lock.txt", "start_stage2.py", ".stage2.env.example", ".env.example", ".gitignore"]
    paths = [ROOT / name for name in files]
    for name in folders:
        paths.extend(p for p in (ROOT / name).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    # Only public demo bars are shipped; local real datasets are not added to the archive.
    paths = [p for p in paths if p.relative_to(ROOT).parts[0] != "data" or p == ROOT / "data" / "sample_ashare.csv"]
    demo = ROOT / "outputs" / "stage2_demo"
    if demo.exists():
        paths.extend(p for p in demo.rglob("*") if p.is_file())
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in sorted(set(paths)):
            if path.is_file():
                archive.write(path, Path("ai-hedge-fund-cn") / path.relative_to(ROOT))
    print(output)
    print(f"{output.stat().st_size:,} bytes")


if __name__ == "__main__":
    package()
