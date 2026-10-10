'use strict';
const $ = id => document.getElementById(id);
let timer = null, activeId = null, currentChart = null, resizeTimer = null;
const pct = v => `${(v * 100).toFixed(2)}%`;
async function api(path, options = {}) {
  const res = await fetch(path, options);
  const data = await res.json();
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  return data;
}
function fail(message) { $('error').textContent = message; $('error').hidden = false; }
function setStatus(message) { $('status').textContent = message; }
async function history() {
  const jobs = await api('/api/experiments');
  $('history').replaceChildren(new Option('选择已保存的实验', ''));
  for (const j of jobs) $('history').add(new Option(`${j.id.slice(0, 8)} · ${j.status}`, j.id));
}
function chart(points, capital) {
  currentChart = {points, capital};
  const ns = 'http://www.w3.org/2000/svg', w = Math.max(250, $('chart').clientWidth), h = 230, pad = 45;
  const svg = document.createElementNS(ns, 'svg'); svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
  const node = (tag, attrs, text) => { const el = document.createElementNS(ns, tag); for (const [k,v] of Object.entries(attrs)) el.setAttribute(k, v); if (text) el.textContent = text; svg.append(el); return el; };
  const vals = points.map(p => p.equity / capital * 100), low = Math.min(100, ...vals), high = Math.max(100, ...vals);
  const margin = Math.max((high - low) * .12, .5), min = low - margin, max = high + margin;
  const x = i => pad + i / Math.max(1, vals.length - 1) * (w - pad - 18);
  const y = v => 10 + (max - v) / (max - min) * (h - 45);
  for (let i = 0; i < 4; i++) { const v = min + (max - min) * i / 3; node('line', {x1:pad, x2:w-18, y1:y(v), y2:y(v), stroke:'#e6ede7'}); node('text', {x:pad-9, y:y(v)+4, 'text-anchor':'end', fill:'#7c8c86', 'font-size':10}, v.toFixed(1)); }
  node('line', {x1:pad, x2:w-18, y1:y(100), y2:y(100), stroke:'#a9bbb2', 'stroke-dasharray':'4 4'});
  node('polyline', {points:vals.map((v,i) => `${x(i)},${y(v)}`).join(' '), fill:'none', stroke:'#06766c', 'stroke-width':2.5});
  vals.forEach((v,i) => { const dot = node('circle', {cx:x(i), cy:y(v), r:3, fill:'#06766c'}); const title = document.createElementNS(ns,'title'); title.textContent = `${points[i].date}: ${v.toFixed(2)}`; dot.append(title); });
  if (points.length) { node('text', {x:pad, y:h-3, fill:'#7c8c86', 'font-size':10}, points[0].date); node('text', {x:w-18, y:h-3, 'text-anchor':'end', fill:'#7c8c86', 'font-size':10}, points.at(-1).date); }
  $('chart').replaceChildren(svg);
}
function render(result, id) {
  $('empty').hidden = true; $('output').hidden = false;
  const b = result.backtest, m = b.metrics;
  $('return').textContent = pct(m.total_return); $('return').className = m.total_return >= 0 ? 'positive' : 'negative';
  $('drawdown').textContent = pct(m.max_drawdown_daily); $('sharpe').textContent = m.sharpe_annualized_approx.toFixed(3);
  $('trade-count').textContent = m.n_trades; $('open-count').textContent = `期末 ${m.n_open_positions} 个持仓`;
  $('summary').textContent = result.summary; $('source').textContent = result.analysis_source === 'llm' ? '模型分析' : '规则报告';
  $('llm-warning').hidden = !result.llm_error; $('llm-warning').textContent = result.llm_error ? `模型未完成分析，已保留计算结果并使用规则报告：${result.llm_error}` : '';
  $('warnings').replaceChildren(); for (const text of result.quality.warnings) { const li = document.createElement('li'); li.textContent = text; $('warnings').append(li); }
  $('date-range').textContent = `${result.quality.start} — ${result.quality.end}`;
  $('fee').textContent = `手续费 ${m.fees_paid.toFixed(2)} 元`;
  $('skipped').textContent = `${b.skipped_orders.length} 个未成交指令`;
  $('md-download').href = `/api/experiments/${id}/report`;
  $('json-download').href = `/api/experiments/${id}/report?format=json`;
  $('trades').replaceChildren();
  const rows = [...b.trades.map(t => [t.code,t.entry_date,t.exit_date,t.quantity,pct(t.net_return)]), ...b.open_positions.map(p => [p.code,p.entry_date,'仍持有',p.quantity,'—'])];
  for (const row of rows.slice(0, 100)) { const tr = document.createElement('tr'); for (const val of row) { const td = document.createElement('td'); td.textContent = val; tr.append(td); } $('trades').append(tr); }
  $('table-note').textContent = rows.length ? `共 ${rows.length} 条记录，显示前 100 条；完整记录见 JSON。` : '当前参数下没有成交记录。';
  chart(b.equity_curve, b.config.initial_capital);
  renderStudy(result.study, id);
}
async function poll(id) {
  try {
    const job = await api(`/api/experiments/${id}`);
    if (id !== activeId) return;
    setStatus({queued:'等待执行',running:'研究中',completed:'已完成',failed:'执行失败'}[job.status] || job.status);
    const nodes = ['validate_data','compute_factor','run_backtest','compare_costs','finish'];
    [...$('steps').children].forEach((li,i) => li.classList.toggle('done',job.events.some(e => e.node === nodes[i] && e.status === 'completed')));
    $('trace').replaceChildren();
    for (const e of job.events.slice(-12)) { const line = document.createElement('div'); line.textContent = `${e.node}${e.tool ? ' / '+e.tool : ''} · ${e.status}${e.message ? ' · '+e.message : ''}`; $('trace').append(line); }
    if (job.status === 'completed') { render(job.result,id); $('run').disabled = false; await history(); }
    else if (job.status === 'failed') { fail(job.error); $('run').disabled = false; await history(); }
    else timer = setTimeout(() => poll(id), 650);
  } catch (error) { if (id === activeId) { fail(error.message); $('run').disabled = false; setStatus('连接失败'); } }
}
$('research-form').addEventListener('submit', async e => {
  e.preventDefault(); clearTimeout(timer); $('error').hidden = true; $('run').disabled = true;
  $('output').hidden = true; $('empty').hidden = false; setStatus('提交中');
  try {
    const form = Object.fromEntries(new FormData(e.target));
    for (const key of ['quantile','initial_capital','commission_bps','stamp_duty_bps','slippage_bps']) form[key] = Number(form[key]);
    if ($('enable-study').checked) form.study = {train_sessions: Number($('train-sessions').value), test_sessions: Number($('test-sessions').value)};
    const job = await api('/api/experiments', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(form)});
    activeId = job.id; location.hash = activeId; await poll(activeId);
  } catch(error) { fail(error.message); $('run').disabled = false; setStatus('提交失败'); }
});
$('history').addEventListener('change', () => { if (!$('history').value) return; clearTimeout(timer); activeId = $('history').value; location.hash = activeId; $('error').hidden = true; $('output').hidden = true; poll(activeId); });
$('dataset').addEventListener('change', () => { $('dataset-hint').textContent = $('dataset').value === 'sample_ashare' ? '演示数据只验证工程链路。' : '结果依赖文件质量与股票池，运行前请核对数据口径。'; });
window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (currentChart) chart(currentChart.points, currentChart.capital); }, 150); });
(async () => {
  try {
    const [health, datasets] = await Promise.all([api('/api/health'),api('/api/datasets')]);
    $('health').textContent = '本地服务已连接'; $('llm-option').disabled = !health.llm_available;
    $('dataset').replaceChildren(); for (const d of datasets) $('dataset').add(new Option(`${d.is_demo ? '演示数据 · ' : ''}${d.id}`,d.id));
    if (datasets.some(d => d.id === 'sample_stage3')) { $('dataset').value = 'sample_stage3'; $('enable-study').checked = true; }
    if (!datasets.length) { fail('data 目录内没有可用 CSV 数据集。'); $('run').disabled = true; }
    await history();
    const ident = location.hash.slice(1); if (/^[a-f0-9]{32}$/.test(ident)) { activeId = ident; await poll(ident); }
  } catch(error) { $('health').textContent = '服务不可用'; fail(error.message); }
})();
