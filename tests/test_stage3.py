import asyncio
import json
from pathlib import Path
import sys
import time

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import ValidationError

from api.main import create_app
from cn_research.backtest import Costs, run_backtest
from cn_research.study import run_study, universe_filter, buy_and_hold
from research_agent.graph import run_research
from research_agent.langchain_runtime import LangChainModelClient
from research_agent.schemas import BacktestInput, ExperimentInput, StudyInput, UniverseSpec
from research_agent.settings import PROJECT_ROOT
from research_agent.tools import ResearchTools
from scripts.generate_stage3_data import generate


def short_config(**kwargs):
    return StudyInput(train_sessions=12, test_sessions=8, quantiles=[.2,.5], slippages=[0,5],
                      universes=[UniverseSpec()], **kwargs)


def test_future_test_prices_cannot_change_first_fold_training_selection():
    bars = generate(38)
    first = run_study(bars, short_config())
    cutoff = first['universes'][0]['folds'][0]['test_start']
    changed = bars.copy()
    columns = ['open','high','low','close','limit_up','limit_down']
    changed.loc[changed.date >= cutoff, columns] *= 1.7
    second = run_study(changed, short_config())
    a,b = first['universes'][0]['folds'][0], second['universes'][0]['folds'][0]
    assert a['training_candidates'] == b['training_candidates']
    assert a['selected_quantile'] == b['selected_quantile']
    assert first['universes'][0]['oos']['metrics'] != second['universes'][0]['oos']['metrics']


def test_oos_equity_prefix_is_invariant_to_later_price_mutation():
    bars = generate(38)
    dates = sorted(bars.date.unique())
    original = run_study(bars, short_config())
    changed=bars.copy()
    changed.loc[changed.date >= dates[30], ['open','high','low','close','limit_up','limit_down']] *= .7
    altered = run_study(changed, short_config())
    a = original['universes'][0]['oos']['equity_curve']
    b = altered['universes'][0]['oos']['equity_curve']
    assert [r for r in a if r['date'] < dates[30]] == [r for r in b if r['date'] < dates[30]]


def test_fold_returns_reconcile_continuous_ledger_and_timing():
    bars = generate(38)
    pool = run_study(bars, short_config())['universes'][0]
    folds, out = pool['folds'], pool['oos']
    assert len(folds) == 3
    compounded = np.prod([1+f['oos_metrics']['total_return'] for f in folds])-1
    assert compounded == pytest.approx(out['metrics']['total_return'])
    assert len({r['date'] for r in out['equity_curve']}) == len(out['equity_curve'])
    for f in folds:
        assert f['train_end'] < min(f['purged_dates']) < f['test_start']
        assert len(f['purged_dates']) == 2
    sessions = {d:i for i,d in enumerate(sorted(bars.date.unique()))}
    for trade in out['trades']:
        assert trade['signal_date'] >= folds[0]['test_start']
        assert sessions[trade['exit_date']] > sessions[trade['entry_date']]
    for signal in out['signals']:
        f = next(f for f in folds if f['test_start'] <= signal['signal_date'] <= f['test_end'])
        assert signal['quantile'] == f['selected_quantile']


def test_blocked_exit_carries_across_parameter_window():
    bars=generate(22)
    dates=sorted(bars.date.unique())
    # Block all sells from a window boundary onward, preserving valid OHLC.
    bars.loc[bars.date >= dates[9], 'limit_down'] = bars.loc[bars.date >= dates[9], 'close']
    schedule={d:(.2 if i<10 else .5) for i,d in enumerate(dates)}
    result=run_backtest(bars, quantile_schedule=schedule)
    assert result['open_positions']
    assert any(p['entry_date'] < dates[10] for p in result['open_positions'])
    assert any(s['reason']=='already_held' for s in result['skipped_orders'])
    assert result['metrics']['ending_cash'] >= -1e-8


def test_sensitivity_cannot_modify_walk_forward_selection():
    a=short_config()
    b=a.model_copy(update={'slippages':[0,25]})
    first,second=run_study(generate(30),a),run_study(generate(30),b)
    p,q=first['universes'][0],second['universes'][0]
    assert p['folds']==q['folds'] and p['oos']==q['oos']
    assert p['sensitivity'] != q['sensitivity']


def test_empty_declared_pool_remains_cash_and_ties_choose_smallest_q():
    config=short_config().model_copy(update={'universes':[UniverseSpec(name='absent',selector='custom',codes=['999999'])]})
    pool=run_study(generate(22),config)['universes'][0]
    assert pool['oos']['metrics']['total_return']==0
    assert pool['benchmark']['metrics']['total_return']==0
    assert all(f['selected_quantile']==.2 for f in pool['folds'])


def test_membership_is_point_in_time_and_rejects_late_knowledge():
    spec=UniverseSpec(name='history',selector='custom',memberships=[
        {'code':'600001','known_at':'2025-01-01','effective_from':'2025-01-02','effective_to':'2025-01-10'},
        {'code':'000001','known_at':'2025-01-10','effective_from':'2025-01-11'}])
    at=universe_filter(spec,['600001','000001'])
    assert at('2025-01-09')=={'600001'}
    assert at('2025-01-10')==set()
    assert at('2025-01-11')=={'000001'}
    with pytest.raises(ValidationError):
        UniverseSpec(selector='custom',memberships=[{'code':'600001','known_at':'2025-02-01','effective_from':'2025-01-01'}])


def test_benchmark_ledger_lots_fees_and_same_dates():
    bars=generate(10)
    dates=sorted(bars.date.unique())
    eligible=universe_filter(UniverseSpec(),sorted(bars.code.unique()))
    result=buy_and_hold(bars,dates,1_000_000,Costs(),eligible)
    spent=sum(f['quantity']*f['price']+f['commission'] for f in result['fills'])
    assert result['equity_curve'][0]['cash']==pytest.approx(1_000_000-spent)
    assert result['fees_paid']>0
    assert all(f['quantity']%100==0 for f in result['fills'])
    assert [r['date'] for r in result['equity_curve']]==dates


@pytest.mark.parametrize('overrides', [{'purge_sessions':0},{'quantiles':[float('nan')]},{'slippages':[-1]},{'universes':[{'name':'same'},{'name':'same'}]}])
def test_invalid_study_config_is_rejected(overrides):
    with pytest.raises(ValidationError):
        StudyInput(**overrides)


def test_insufficient_history_and_resource_budget_are_explicit():
    with pytest.raises(ValueError,match='at least'):
        run_study(generate(10),StudyInput())
    config=short_config().model_copy(update={'test_sessions':4})
    with pytest.raises(ValueError,match='20 folds'):
        run_study(generate(110),config)


def test_langchain_structured_tool_matches_core_and_validates_input():
    tools=ResearchTools()
    registered=tools.langchain_tools()['run_backtest']
    assert registered.invoke({})==tools.run_backtest(BacktestInput())
    with pytest.raises(ValidationError):
        registered.invoke({'quantile':.9})


def test_langchain_actual_http_tool_roundtrip(monkeypatch):
    for key,value in {'LLM_BASE_URL':'https://model.example/v1','LLM_MODEL':'stub','LLM_API_KEY':'private-test-token'}.items():
        monkeypatch.setenv(key,value)
    requests=[]
    def handler(request):
        payload=json.loads(request.content)
        requests.append(payload)
        if len(requests)==1:
            assert any(t['function']['name']=='compare_costs' for t in payload['tools'])
            assert '项目研究 Skill' in payload['messages'][0]['content']
            message={'role':'assistant','content':None,'tool_calls':[{'id':'lc_call','type':'function','function':{'name':'compare_costs','arguments':'{}'}}]}
        else:
            assert payload['messages'][-1]['role']=='tool'
            assert 'return_difference' in json.loads(payload['messages'][-1]['content'])
            message={'role':'assistant','content':'已使用工具核对，人工数据不能证明因子有效。'}
        return httpx.Response(200,json={'id':'chat-test','object':'chat.completion','created':0,'model':'stub',
            'choices':[{'index':0,'finish_reason':'tool_calls' if len(requests)==1 else 'stop','message':message}],
            'usage':{'prompt_tokens':20,'completion_tokens':10,'total_tokens':30}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        model=LangChainModelClient(http_client=http)
        result=run_research(ExperimentInput(mode='llm'),ResearchTools(),model=model)
    assert len(requests)==2 and result['rounds']==2
    assert result['summary'].startswith('已使用工具')
    assert 'private-test-token' not in json.dumps(result,ensure_ascii=False)


def test_langchain_error_redacts_provider_body_and_preserves_backtest(monkeypatch):
    for key,value in {'LLM_BASE_URL':'https://model.example/v1','LLM_MODEL':'stub','LLM_API_KEY':'private-test-token'}.items():
        monkeypatch.setenv(key,value)
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(401,json={'error':'private-test-token secret response'}))) as http:
        result=run_research(ExperimentInput(mode='llm'),ResearchTools(),model=LangChainModelClient(http_client=http))
    assert result['llm_error']=='LangChain model request failed or invalid tool response'
    assert result['backtest']['metrics']['n_trades']>0
    assert 'private-test-token' not in json.dumps(result)


def test_api_study_background_persistence_snapshot_and_downloads(tmp_path):
    data=tmp_path/'data'; data.mkdir()
    bars=generate(30); bars.to_csv(data/'short.csv',index=False)
    config=short_config().model_dump(exclude={'dataset_id','quantile','initial_capital','commission_bps','stamp_duty_bps','slippage_bps'})
    with TestClient(create_app(data_root=data,output_root=tmp_path/'out')) as client:
        assert client.get('/static/study.js').status_code==200
        response=client.post('/api/experiments',json={'dataset_id':'short','study':config})
        assert response.status_code==202
        ident=response.json()['id']
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            job=client.get(f'/api/experiments/{ident}').json()
            if job['status'] in {'completed','failed'}: break
            time.sleep(.05)
        assert job['status']=='completed',job['error']
        study=client.get(f'/api/experiments/{ident}/study').json()
        assert len(study['universes'][0]['folds'])==2
        assert client.get(f'/api/experiments/{ident}/study?format=md').text.startswith('# 第三阶段')
        assert '第三阶段' in client.get(f'/api/experiments/{ident}/report').text
        assert client.get(f'/api/experiments/{ident}/study?format=bad').status_code==422
        assert (tmp_path/'out'/ident/'study/sensitivity.csv').exists()
        (data/'short.csv').write_text('changed',encoding='utf-8')
        assert client.get(f'/api/experiments/{ident}/study').json()==study


def test_stage3_mcp_real_stdio_validation_study():
    async def exercise():
        params=StdioServerParameters(command=sys.executable,args=['-m','mcp_server.server'],cwd=str(PROJECT_ROOT))
        async with stdio_client(params) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                result=await session.call_tool('run_validation_study',{'dataset_id':'sample_stage3','train_sessions':160,'test_sessions':20})
                assert not result.isError
                assert len(result.structuredContent['universes'])==3
                assert len(result.structuredContent['universes'][0]['folds'])==1
    asyncio.run(exercise())
