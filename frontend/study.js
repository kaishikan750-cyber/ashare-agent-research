// Use textContent so model/dataset text cannot become executable HTML.
let activeStudy = null;
function fillStudyRows(id, rows) {
  $(id).replaceChildren();
  for (const row of rows) {
    const tr = document.createElement('tr');
    for (const value of row) { const td = document.createElement('td'); td.textContent = value; tr.append(td); }
    $(id).append(tr);
  }
}
function drawComparison(points) {
  const ns = 'http://www.w3.org/2000/svg', width = 720, height = 250, pad = 40;
  const svg = document.createElementNS(ns, 'svg'); svg.setAttribute('viewBox', `0 0 ${width} ${height}`); svg.style.width = '100%';
  const values = points.flatMap(p => [p.strategy,p.equal_weight,p.cash]);
  const min = Math.min(...values) * .99, max = Math.max(...values) * 1.01;
  const y = v => height-pad-(v-min)/(max-min)*(height-2*pad);
  for (const [key,color,label,offset] of [['strategy','#14917b','策略',0],['equal_weight','#d18b33','等权持有',100],['cash','#7c8c86','现金',235]]) {
    const path = document.createElementNS(ns,'path');
    path.setAttribute('d', points.map((p,i)=>`${i?'L':'M'}${pad+i/Math.max(1,points.length-1)*(width-2*pad)},${y(p[key])}`).join(' '));
    path.setAttribute('stroke',color); path.setAttribute('fill','none'); path.setAttribute('stroke-width','2'); svg.append(path);
    const text = document.createElementNS(ns,'text'); text.setAttribute('x',pad+offset); text.setAttribute('y',18); text.setAttribute('fill',color); text.setAttribute('font-size',13); text.textContent=label; svg.append(text);
  }
  for (const [value,py] of [[max,pad],[min,height-pad]]) {
    const t=document.createElementNS(ns,'text');t.setAttribute('x',2);t.setAttribute('y',py);t.setAttribute('font-size',10);t.textContent=value.toFixed(2);svg.append(t);
  }
  $('study-chart').replaceChildren(svg);
}
function showStudyPool() {
  if (!activeStudy) return;
  const pool = activeStudy.universes.find(p => p.universe.name === $('study-pool').value);
  fillStudyRows('study-folds',pool.folds.map(f=>[`${f.train_start} ~ ${f.train_end}`,`${f.test_start} ~ ${f.test_end}`,f.selected_quantile,pct(f.oos_metrics.total_return)]));
  fillStudyRows('study-grid',pool.sensitivity.map(s=>[s.quantile,s.slippage_bps,pct(s.metrics.total_return),pct(s.metrics.max_drawdown_daily)]));
  drawComparison(pool.comparison_curve);
}
function renderStudy(study,id) {
  activeStudy=study; $('study-panel').hidden=!study;
  if (!study) return;
  $('study-download').href=`/api/experiments/${id}/study?format=md`;
  fillStudyRows('study-pools',study.universes.map(p=>[p.universe.name,p.folds.length,pct(p.oos.metrics.total_return),pct(p.oos.metrics.max_drawdown_daily),pct(p.benchmark.metrics.total_return),pct(p.excess_total_return)]));
  $('study-pool').replaceChildren(); for(const p of study.universes) $('study-pool').add(new Option(p.universe.name,p.universe.name));
  $('study-warnings').replaceChildren(); for(const w of study.warnings) {const li=document.createElement('li');li.textContent=w;$('study-warnings').append(li);}
  showStudyPool();
}
$('study-pool').addEventListener('change',showStudyPool);
