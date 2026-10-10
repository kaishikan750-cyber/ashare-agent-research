"""Allowlisted source release, with content hashes; no local user datasets or secrets."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
FOLDERS=['cn_research','research_agent','api','frontend','mcp_server','tests','docs','configs','hedge_fund','assets','scripts','.github','.agents']
FILES=['README.md','README_STAGE3.md','README_STAGE2.md','README_CN_RESEARCH.md','LICENSE','pyproject.toml','poetry.lock',
       'requirements-research.txt','requirements-stage2.txt','requirements-stage2-lock.txt','requirements-stage3.txt',
       'requirements-stage3-lock.txt','requirements-demo.txt','start_stage2.py','start_stage3.py',
       '.env.example','.stage2.env.example','.stage3.env.example','.gitignore','.dockerignore','Dockerfile','compose.yaml']


def package():
    paths=[ROOT/n for n in FILES if (ROOT/n).is_file()]
    for folder in FOLDERS:
        paths.extend(p for p in (ROOT/folder).rglob('*') if p.is_file()
                     and not any(part in {'__pycache__','.pytest_cache'} for part in p.parts)
                     and p.suffix not in {'.pyc','.db','.sqlite','.sqlite3'}
                     and p.name not in {'.env','.stage2.env','.stage3.env'})
    paths.extend(ROOT/'data'/name for name in ['sample_ashare.csv','sample_stage3.csv'])
    paths.extend(p for p in (ROOT/'outputs/stage3_demo').glob('*') if p.suffix in {'.json','.md','.csv'})
    paths.append(ROOT/'output/pdf/Agent项目实战学习手册_LangGraph_FastAPI_MCP.pdf')
    paths=sorted(set(p for p in paths if p.is_file()))
    mandatory=[ROOT/'docs/demo/stage3-demo.mp4',ROOT/'outputs/stage3_demo/study.json',ROOT/'requirements-stage3-lock.txt']
    assert all(p in paths for p in mandatory),'missing deliverable'
    entries={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    manifest={'release':'0.3.0','date':'2026-10-10','verified':'Windows Python 3.13.9; 47 research tests; new-env launcher; Chromium UI',
              'limits':'Docker/remote GitHub Actions/real external model not executed; synthetic demo only','files':entries}
    (ROOT/'DELIVERY_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    paths.append(ROOT/'DELIVERY_MANIFEST.json')
    output=ROOT.parent/'ai-hedge-fund-cn-stage3.zip'
    with ZipFile(output,'w',ZIP_DEFLATED) as z:
        for path in paths:z.write(path,Path('ai-hedge-fund-cn')/path.relative_to(ROOT))
    with ZipFile(output) as z:
        assert z.testzip() is None
        for name,digest in entries.items():
            assert hashlib.sha256(z.read('ai-hedge-fund-cn/'+name)).hexdigest()==digest
        assert all('.venv' not in name and '/.git/' not in name for name in z.namelist())
    print('Verified archive:',output,flush=True)
    print('Files:',len(paths),'bytes:',output.stat().st_size,flush=True)


if __name__=='__main__':package()
