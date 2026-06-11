import { esc, modelChip, showErr, toLocalDT } from './util.js';
import { state, HISTORY_LIMIT } from './state.js';
import { api } from './api.js';

const ROLE_COLOR = { system: '#f59e0b', user: '#60a5fa', assistant: '#34d399', tool: '#a78bfa' };

export async function loadHistory() {
  showErr('history-err', false);
  try {
    const resp = await api('/usage/history?limit=200&offset=0');
    if (!resp.ok) throw new Error();
    const d = await resp.json();
    state.allHistory = d.items || [];
    populateHistoryModels();
  } catch {
    showErr('history-err', true);
    state.allHistory = [];
  }
  renderHistory();
}

export function filteredHistory() {
  const q = state.historySearch.trim().toLowerCase();
  return state.allHistory.filter(r => {
    if (state.historyStatus !== 'all' && r.status !== state.historyStatus) return false;
    if (state.historyModel !== 'all' && r.model !== state.historyModel) return false;
    if (q && !((r.prompt_preview || '').toLowerCase().includes(q) || r.model.toLowerCase().includes(q))) return false;
    return true;
  });
}

export function renderHistory() {
  const list = filteredHistory();
  const total = list.length;
  if (state.historyOffset >= total && total > 0) state.historyOffset = 0;
  const items = list.slice(state.historyOffset, state.historyOffset + HISTORY_LIMIT);
  document.getElementById('history-table-body').innerHTML = items.length
    ? items.map(r => `<tr class="history-row" data-id="${r.id}">
        <td class="mono dim nowrap">${esc(toLocalDT(r.timestamp))}</td>
        <td>${modelChip(r.model)}</td>
        <td><div class="prompt-preview" title="${esc(r.prompt_preview || '')}">${esc(r.prompt_preview || '—')}</div></td>
        <td class="num">${(r.prompt_tokens || 0).toLocaleString()}</td>
        <td class="num">${(r.completion_tokens || 0).toLocaleString()}</td>
        <td class="num">${r.tps != null ? r.tps + ' t/s' : '—'}</td>
        <td>${_finishChip(r.finish_reason)}</td>
        <td>${r.status === 'ok' ? '<span class="badge badge-ok">ok</span>' : `<span class="badge badge-err">${esc(r.status)}</span>`}</td>
      </tr>`).join('')
    : '<tr class="empty-row"><td colspan="8">No requests match your filters.</td></tr>';
  document.getElementById('history-page-info').textContent = total
    ? `${state.historyOffset + 1}–${Math.min(state.historyOffset + items.length, total)} of ${total}`
    : '0 of 0';
  document.getElementById('history-prev').disabled = state.historyOffset === 0;
  document.getElementById('history-next').disabled = state.historyOffset + HISTORY_LIMIT >= total;
}

export async function showHistoryDetail(id) {
  const overlay = document.getElementById('req-detail-overlay');
  document.getElementById('req-detail-body').innerHTML = '<div class="detail-loading">Loading…</div>';
  overlay.classList.add('open');
  try {
    const resp = await api(`/usage/history/${id}`);
    if (!resp.ok) throw new Error(resp.status);
    _renderHistoryDetail(await resp.json());
  } catch {
    document.getElementById('req-detail-body').innerHTML =
      '<div class="detail-empty" style="color:var(--red)">Failed to load request detail.</div>';
  }
}

export function closeHistoryDetail() {
  document.getElementById('req-detail-overlay').classList.remove('open');
}

export function historyPage(dir) {
  const total = filteredHistory().length;
  state.historyOffset = Math.max(0, Math.min(state.historyOffset + dir * HISTORY_LIMIT, Math.max(0, total - 1)));
  renderHistory();
}

export function onHistoryFilter() {
  state.historySearch = document.getElementById('history-search').value;
  state.historyModel  = document.getElementById('history-model').value;
  state.historyOffset = 0;
  renderHistory();
}

export function setHistoryStatus(s) {
  state.historyStatus = s;
  document.querySelectorAll('.ftab').forEach(t => t.classList.toggle('active', t.dataset.status === s));
  state.historyOffset = 0;
  renderHistory();
}

export function populateHistoryModels() {
  const unique = [...new Set(state.allHistory.map(r => r.model))].sort();
  document.getElementById('history-model').innerHTML =
    '<option value="all">All models</option>' +
    unique.map(m => `<option value="${esc(m)}">${esc(m)}</option>`).join('');
}

function _finishChip(f) {
  if (!f) return '<span class="mono dim">—</span>';
  if (f === 'stop')       return '<span class="pill pill-nostream">stop</span>';
  if (f === 'tool_calls') return '<span class="pill pill-stream">tool_calls</span>';
  if (f === 'length')     return '<span class="pill pill-length">length</span>';
  return `<span class="pill pill-nostream">${esc(f)}</span>`;
}

function _msgContent(m) {
  if (typeof m.content === 'string') return esc(m.content);
  if (Array.isArray(m.content)) {
    return m.content.map(p =>
      p.type === 'text'
        ? esc(p.text || '')
        : `<span class="content-type-tag">[${esc(p.type || 'part')}]</span>`
    ).join('');
  }
  if (m.tool_calls) {
    return `<span class="content-type-tag">[tool_calls]</span>\n` +
      esc(JSON.stringify(m.tool_calls, null, 2));
  }
  return '<span class="detail-empty">—</span>';
}

function _renderHistoryDetail(d) {
  const raw = d.completion_content || '';
  const thinkMatch = raw.match(/<think>([\s\S]*?)<\/think>/);
  const reasoning  = thinkMatch ? thinkMatch[1].trim() : '';
  const completion = raw.replace(/<think>[\s\S]*?<\/think>\n*/g, '').trim();

  const streamPill = d.stream
    ? '<span class="pill pill-stream">streaming</span>'
    : '<span class="pill pill-nostream">non-stream</span>';
  const statusBadge = d.status === 'ok'
    ? '<span class="badge badge-ok">ok</span>'
    : `<span class="badge badge-err">${esc(d.status)}</span>`;

  const messagesHtml = (d.prompt_messages || []).map(m => {
    const role  = m.role || 'unknown';
    const color = ROLE_COLOR[role] || '#7d8694';
    return `<div class="role-block" style="border-left-color:${color}">
      <span class="role-label" style="color:${color}">${esc(role)}</span>
      <pre class="role-content">${_msgContent(m)}</pre>
    </div>`;
  }).join('') || '<div class="detail-empty">No message data recorded</div>';

  let html = `
    <div class="detail-meta">
      ${modelChip(d.model)}
      ${statusBadge}
      ${streamPill}
      <span class="mono dim" style="font-size:0.78rem">${esc(toLocalDT(d.timestamp))}</span>
    </div>
    <div class="detail-metrics">
      <div class="metric-item"><span class="metric-label">Latency</span>
        <span class="metric-val">${d.duration_ms != null ? d.duration_ms.toLocaleString() + ' ms' : '—'}</span></div>
      <div class="metric-item"><span class="metric-label">Speed</span>
        <span class="metric-val">${d.tps != null ? d.tps + ' tok/s' : '—'}</span></div>
      <div class="metric-item"><span class="metric-label">Finish</span>
        <span class="metric-val">${esc(d.finish_reason || '—')}</span></div>
      <div class="metric-item"><span class="metric-label">Tokens</span>
        <span class="metric-val">${(d.prompt_tokens||0).toLocaleString()} + ${(d.completion_tokens||0).toLocaleString()} = ${(d.total_tokens||0).toLocaleString()}</span></div>
    </div>
    <div class="detail-section"><span class="detail-section-label">Prompt</span></div>
    <div class="detail-messages">${messagesHtml}</div>`;

  if (completion) {
    html += `<div class="detail-section"><span class="detail-section-label">Completion</span></div>
    <pre class="detail-pre">${esc(completion)}</pre>`;
  }
  if (reasoning) {
    html += `<div class="detail-section"><span class="detail-section-label">Reasoning</span></div>
    <pre class="detail-pre detail-reasoning">${esc(reasoning)}</pre>`;
  }
  if (d.status !== 'ok' && d.error_detail) {
    html += `<div class="detail-section"><span class="detail-section-label">Error</span></div>
    <pre class="detail-pre detail-error">${esc(d.error_detail)}</pre>`;
  }
  document.getElementById('req-detail-body').innerHTML = html;
}
