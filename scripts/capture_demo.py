"""Capture actual local app views and run UI assertions; no external account."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:8001')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    directory=root/'docs/demo'
    directory.mkdir(parents=True,exist_ok=True)
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1600,'height':1000},device_scale_factor=1)
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(args.url,wait_until='networkidle')
        assert page.locator('#dataset').input_value()=='sample_stage3'
        assert page.locator('#enable-study').is_checked()
        page.screenshot(path=str(directory/'01-setup.png'))
        page.locator('#run').click()
        page.wait_for_function("document.getElementById('status').textContent === '已完成'",timeout=120000)
        assert page.locator('#study-panel').is_visible()
        ident=page.evaluate('location.hash.slice(1)')
        job=page.request.get(f'{args.url}/api/experiments/{ident}').json()
        assert job['status']=='completed'
        assert len(job['result']['study']['universes'])==3
        assert page.locator('#study-pools tr').count()==3
        page.screenshot(path=str(directory/'02-result.png'))
        page.locator('#study-panel').scroll_into_view_if_needed()
        page.screenshot(path=str(directory/'03-walk-forward.png'))
        page.locator('#study-pool').select_option('sz_main')
        assert page.locator('#study-folds tr').count()==6
        page.screenshot(path=str(directory/'04-pools.png'))
        page.locator('#study-panel details').nth(1).locator('summary').click()
        page.locator('#study-grid').scroll_into_view_if_needed()
        page.screenshot(path=str(directory/'05-sensitivity.png'))
        assert page.locator('#study-grid tr').count()==9
        report=page.request.get(f'{args.url}/api/experiments/{ident}/report').text()
        assert '第三阶段结构化研究报告' in report
        page.reload(wait_until='networkidle')
        page.wait_for_function("document.getElementById('status').textContent === '已完成'")
        assert page.locator('#study-pools tr').count()==3
        page.set_viewport_size({'width':390,'height':844})
        page.goto(args.url,wait_until='networkidle')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth+1')
        assert not errors,errors
        browser.close()
    (directory/'capture_metadata.json').write_text(json.dumps({'method':'Actual headless Chromium local page captures',
        'job_id':ident,'browser_errors':errors,'ui_checks':['submit','completed study','3 pool rows','6 folds','9 grid rows','report download','history reload','mobile no overflow']},ensure_ascii=False,indent=2),encoding='utf-8')
    print('UI checks passed; screenshots captured:',directory,flush=True)


if __name__=='__main__':
    main()
