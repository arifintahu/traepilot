import { esc, fmt, modelChip, showErr } from './util.js';
import { state } from './state.js';
import { api } from './api.js';

export function sparkline(seed) {
  const base = state.dailyData.length
    ? state.dailyData.map(d => d.requests)
    : [10, 18, 14, 22, 17, 28, 24];
  const pts = base.map((v, i) => v * (1 + 0.1 * Math.sin(seed * 2 + i)));
  const max = Math.max(...pts), min = Math.min(...pts);
  const W = 64, H = 22;
  const path = pts.map((v, i) => {
    const x = (i / (pts.length - 1)) * W;
    const y = H - ((v - min) / (max - min || 1)) * (H - 3) - 1.5;
    return (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1);
  }).join(' ');
  return `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" fill="none" aria-hidden="true">
    <path d="${path}" stroke="var(--accent)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity=".85"/>
  </svg>`;
}

export async function renderUsage() {
  showErr('usage-err', false);
  try {
    const resp = await api('/usage/stats?period=' + state.period);
    if (!resp.ok) throw new Error();
    const s = await resp.json();
    const cards = [
      ['Requests',          s.total_requests,          0],
      ['Total Tokens',      s.total_tokens,             1],
      ['Prompt Tokens',     s.total_prompt_tokens,      2],
      ['Completion Tokens', s.total_completion_tokens,  3],
    ];
    document.getElementById('stat-grid').innerHTML = cards.map(([label, val, seed]) => `
      <div class="stat-card">
        <div class="stat-top">
          <span class="stat-label">${label}</span>
          <span class="stat-spark">${sparkline(seed)}</span>
        </div>
        <div class="stat-value num">${fmt(val)}</div>
        <div class="stat-foot"><span class="trend trend-flat">estimated</span><span class="stat-vs">÷4 heuristic</span></div>
      </div>`).join('');
    renderModelTable(s.by_model || {});
    document.getElementById('by-model-meta').textContent = 'last ' + state.period;
  } catch {
    showErr('usage-err', true);
    document.getElementById('stat-grid').innerHTML = '';
  }
  renderChart();
}

export function renderChart() {
  const data = state.dailyData;
  if (!data.length) {
    document.getElementById('chart-plot').innerHTML =
      '<div style="color:var(--txt-m);padding:30px;text-align:center;width:100%">No data yet</div>';
    return;
  }
  const today = new Date().toISOString().slice(0, 10);
  const maxReq = Math.max(...data.map(d => d.requests), 1);
  const maxTok = Math.max(...data.map(d => d.total_tokens / 1000), 1);
  document.getElementById('chart-yaxis').innerHTML =
    [maxReq, Math.round(maxReq * .75), Math.round(maxReq * .5), Math.round(maxReq * .25), 0]
      .map(v => `<span>${v}</span>`).join('');
  document.getElementById('chart-plot').innerHTML = data.map(d => {
    const rH = (d.requests / maxReq) * 100;
    const tH = ((d.total_tokens / 1000) / maxTok) * 100;
    const isToday = d.date === today;
    return `<div class="day-col${isToday ? ' today' : ''}"
      data-tip="${esc(d.date.slice(5))} · ${d.requests} reqs · ${(d.total_tokens / 1000).toFixed(0)}k tok">
      <div class="bars">
        <div class="bar bar-req" style="height:${rH}%"></div>
        <div class="bar bar-tok" style="height:${tH}%"></div>
      </div>
      <div class="day-label${isToday ? ' today' : ''}">${d.date.slice(5)}</div>
    </div>`;
  }).join('');
  _bindChartTips();
}

export function renderModelTable(byModel) {
  const entries = Object.entries(byModel).sort((a, b) => b[1].requests - a[1].requests);
  const totalReq = entries.reduce((s, [, v]) => s + v.requests, 0) || 1;
  document.getElementById('model-table-body').innerHTML = entries.length
    ? entries.map(([id, v]) => {
        const pct = Math.round((v.requests / totalReq) * 100);
        return `<tr>
          <td>${modelChip(id)}</td>
          <td class="num">${v.requests.toLocaleString()}</td>
          <td class="num">${(v.prompt_tokens || 0).toLocaleString()}</td>
          <td class="num">${(v.completion_tokens || 0).toLocaleString()}</td>
          <td><div class="share-wrap"><div class="share-track"><div class="share-fill" style="width:${pct}%"></div></div><span class="share-pct">${pct}%</span></div></td>
        </tr>`;
      }).join('')
    : '<tr class="empty-row"><td colspan="5">No data for this period.</td></tr>';
}

let _tip;
function _bindChartTips() {
  if (!_tip) {
    _tip = document.createElement('div');
    _tip.className = 'chart-tip';
    document.body.appendChild(_tip);
  }
  document.querySelectorAll('.day-col').forEach(col => {
    col.addEventListener('mousemove', e => {
      _tip.textContent = col.dataset.tip;
      _tip.style.opacity = '1';
      _tip.style.left = e.clientX + 'px';
      _tip.style.top = (e.clientY - 14) + 'px';
    });
    col.addEventListener('mouseleave', () => { _tip.style.opacity = '0'; });
  });
}
