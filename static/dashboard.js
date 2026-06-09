'use strict';

/* ── SVG icon set ────────────────────────────────────────────── */
const ICON = {
  copy:    '<svg viewBox="0 0 24 24" fill="none"><rect x="9" y="9" width="11" height="11" rx="2.5" stroke="currentColor" stroke-width="1.8"/><path d="M5 15V5a2 2 0 012-2h10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  refresh: '<svg viewBox="0 0 24 24" fill="none"><path d="M20 11a8 8 0 10-1 5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><path d="M20 4v5h-5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  eye:     '<svg viewBox="0 0 24 24" fill="none"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z" stroke="currentColor" stroke-width="1.6"/><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.6"/></svg>',
  play:    '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 5l12 7-12 7z"/></svg>',
  check:   '<svg viewBox="0 0 24 24" fill="none"><path d="M4 12l5 5L20 6" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  spinner: '<svg class="spin" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="2.4" stroke-opacity=".25"/><path d="M21 12a9 9 0 00-9-9" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>',
  link:    '<svg viewBox="0 0 24 24" fill="none"><path d="M10 14a4 4 0 005.6 0l3-3a4 4 0 10-5.6-5.6l-1.5 1.5M14 10a4 4 0 00-5.6 0l-3 3a4 4 0 105.6 5.6l1.5-1.5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  chip:    '<svg viewBox="0 0 24 24" fill="none"><rect x="6" y="6" width="12" height="12" rx="2" stroke="currentColor" stroke-width="1.7"/><path d="M9 1v4M15 1v4M9 19v4M15 19v4M1 9h4M1 15h4M19 9h4M19 15h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
  box:     '<svg viewBox="0 0 24 24" fill="none"><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>',
};

/* ── Model family detection ──────────────────────────────────── */
const FAMILY = {
  Gemini:   { color: '#60a5fa', glyph: 'G' },
  OpenAI:   { color: '#34d399', glyph: 'O' },
  DeepSeek: { color: '#818cf8', glyph: 'D' },
  Claude:   { color: '#f59e0b', glyph: 'C' },
  Other:    { color: '#7d8694', glyph: '·' },
};
function familyOf(id) {
  const l = (id || '').toLowerCase();
  if (l.startsWith('gemini'))   return 'Gemini';
  if (l.startsWith('gpt') || l.startsWith('o1') || l.startsWith('o3') || l.startsWith('chatgpt')) return 'OpenAI';
  if (l.startsWith('deepseek')) return 'DeepSeek';
  if (l.startsWith('claude'))   return 'Claude';
  return 'Other';
}

/* ── Config groups ───────────────────────────────────────────── */
const CONFIG_GROUPS_DEF = [
  { name: 'Connection', icon: 'link', keys: ['TRAE_BASE_URL','BIND_HOST','BIND_PORT','API_KEY','DASHBOARD_PASSWORD','TRAE_EXCLUDE_MODELS'] },
  { name: 'Device',     icon: 'chip', keys: ['TRAE_DEVICE_BRAND','TRAE_DEVICE_CPU','TRAE_DEVICE_TYPE','TRAE_OS_VERSION','TRAE_DEVICE_ID','TRAE_MACHINE_ID'] },
  { name: 'IDE',        icon: 'box',  keys: ['TRAE_APP_ID','TRAE_IDE_VERSION_CODE','TRAE_IDE_VERSION','TRAE_PLUGIN_CHANNEL','TRAE_IDE_TOKEN'] },
];
const SENSITIVE = new Set(['API_KEY','DASHBOARD_PASSWORD','TRAE_IDE_TOKEN','TRAE_MACHINE_ID','TRAE_DEVICE_ID']);

/* ── One-time migration: remove legacy key storage ───────────── */
sessionStorage.removeItem('tp_key');

/* ── State ───────────────────────────────────────────────────── */
let _period    = '24h';
let _models    = [];
let _apiKeySet  = false;  // true when /config reports API_KEY is configured
let _testApiKey = '';     // Bearer token entered by the user for test chat (in-memory only)
let _refreshTimer = null;
const REFRESH_INTERVAL = 5000;
let _dailyData = [];
let _allHistory = [];
let _historyOffset = 0;
let _historyStatus = 'all';
let _historySearch = '';
let _historyModel  = 'all';
let _testing = false;
const HISTORY_LIMIT = 12;

/* ── Auth ────────────────────────────────────────────────────── */
// Cookies are sent automatically by the browser on same-origin requests;
// no manual Authorization header management needed for dashboard users.
async function api(url, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  return fetch(url, { ...opts, headers });
}
function showAuthOverlay() {
  document.getElementById('auth-overlay').classList.add('visible');
  setTimeout(() => document.getElementById('auth-input').focus(), 60);
}
function hideAuthOverlay() { document.getElementById('auth-overlay').classList.remove('visible'); }
async function submitLogin() {
  const password = document.getElementById('auth-input').value;
  const err = document.getElementById('auth-error');
  err.textContent = '';
  if (!password) { err.textContent = 'Please enter a password.'; return; }
  const resp = await fetch('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  });
  if (resp.status === 204) {
    hideAuthOverlay();
    boot();
  } else if (resp.status === 429) {
    const retryAfter = resp.headers.get('Retry-After');
    err.textContent = retryAfter
      ? `Too many attempts. Try again in ${retryAfter}s.`
      : 'Too many attempts. Try again later.';
  } else {
    err.textContent = 'Wrong password. Try again.';
    document.getElementById('auth-input').value = '';
    document.getElementById('auth-input').focus();
  }
}
async function logout() {
  await fetch('/auth/logout', { method: 'POST' });
  location.reload();
}

/* ── Status dot ──────────────────────────────────────────────── */
function setStatus(ok) {
  const dot = document.getElementById('status-dot');
  const lbl = document.getElementById('status-label');
  dot.className = 'dot' + (ok ? '' : ' offline');
  lbl.textContent = ok ? 'Proxy running' : 'Proxy unreachable';
}

/* ── Helpers ─────────────────────────────────────────────────── */
function fmt(n) {
  if (n == null || isNaN(n)) return '0';
  if (n >= 1e6) return (n / 1e6).toFixed(1) + '<i>M</i>';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + '<i>k</i>';
  return String(n);
}
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}
function modelChip(id) {
  const fam = FAMILY[familyOf(id)] || FAMILY.Other;
  return `<span class="mchip"><span class="mdot" style="background:${fam.color}"></span>${esc(id)}</span>`;
}
function showErr(id, visible) {
  document.getElementById(id)?.classList.toggle('visible', visible);
}

/* ── Navigation ──────────────────────────────────────────────── */
const TITLES = {
  usage:    ['Usage',    'Token & request tracking · estimated via ÷4 heuristic'],
  history:  ['History',  'Full log of proxy requests · searchable & filterable'],
  models:   ['Models',   'Available models from the Trae API'],
  testchat: ['Test Chat','One-click connectivity check'],
  config:   ['Config',   'Environment variables · sensitive fields masked server-side'],
};
function showSection(name) {
  document.querySelectorAll('.section').forEach(s => s.classList.toggle('active', s.id === 'section-' + name));
  document.querySelectorAll('.nav-item').forEach(i => i.classList.toggle('active', i.dataset.section === name));
  const [title, sub] = TITLES[name] || [name, ''];
  document.getElementById('page-title').textContent = title;
  document.getElementById('page-subtitle').textContent = sub;
  document.getElementById('period-tabs').style.display = name === 'usage' ? 'inline-flex' : 'none';
  const liveSection = name === 'usage' || name === 'history';
  document.getElementById('topbar-action').innerHTML = name === 'models'
    ? `<button class="btn-ghost" onclick="refreshModels(this)">${ICON.refresh}Refresh</button>`
    : liveSection
    ? `<span class="live-badge"><span class="live-dot"></span>Live</span>` : '';
  if (name === 'history') { _historyOffset = 0; renderHistory(); }
  if (liveSection) startAutoRefresh(); else stopAutoRefresh();
}

/* ── Period ──────────────────────────────────────────────────── */
function setPeriod(p) {
  _period = p;
  document.querySelectorAll('.ptab').forEach(t => {
    const a = t.dataset.period === p;
    t.classList.toggle('active', a);
    t.setAttribute('aria-selected', String(a));
  });
  renderUsage();
}

/* ── Auto-refresh ────────────────────────────────────────────── */
function _activeSection() {
  const el = document.querySelector('.section.active');
  return el ? el.id.replace('section-', '') : null;
}

async function _doRefresh() {
  const s = _activeSection();
  if (s === 'usage') {
    try {
      const r = await api('/usage/daily?days=7');
      if (r.ok) {
        const d = await r.json();
        _dailyData = (d.items || []).sort((a, b) => a.date < b.date ? -1 : 1).slice(-7);
      }
    } catch {}
    await renderUsage();
  } else if (s === 'history') {
    await loadHistory();
  }
}

function startAutoRefresh() {
  stopAutoRefresh();
  _refreshTimer = setInterval(_doRefresh, REFRESH_INTERVAL);
}

function stopAutoRefresh() {
  if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null; }
}

/* ── Sparklines ──────────────────────────────────────────────── */
function sparkline(seed) {
  const base = _dailyData.length
    ? _dailyData.map(d => d.requests)
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

/* ── Usage ───────────────────────────────────────────────────── */
async function renderUsage() {
  showErr('usage-err', false);
  try {
    const resp = await api('/usage/stats?period=' + _period);
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
    document.getElementById('by-model-meta').textContent = 'last ' + _period;
  } catch {
    showErr('usage-err', true);
    document.getElementById('stat-grid').innerHTML = '';
  }
  renderChart();
}

function renderChart() {
  const data = _dailyData;
  if (!data.length) {
    document.getElementById('chart-plot').innerHTML =
      '<div style="color:var(--txt-m);padding:30px;text-align:center;width:100%">No data yet</div>';
    return;
  }
  const today = new Date().toISOString().slice(0, 10);
  const maxReq = Math.max(...data.map(d => d.requests), 1);
  const maxTok = Math.max(...data.map(d => d.total_tokens / 1000), 1);
  // Update y-axis
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
  bindChartTips();
}

function renderModelTable(byModel) {
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

/* ── History ─────────────────────────────────────────────────── */
async function loadHistory() {
  showErr('history-err', false);
  try {
    const resp = await api('/usage/history?limit=200&offset=0');
    if (!resp.ok) throw new Error();
    const d = await resp.json();
    _allHistory = d.items || [];
    populateHistoryModels();
  } catch {
    showErr('history-err', true);
    _allHistory = [];
  }
  renderHistory();
}

function filteredHistory() {
  const q = _historySearch.trim().toLowerCase();
  return _allHistory.filter(r => {
    if (_historyStatus !== 'all' && r.status !== _historyStatus) return false;
    if (_historyModel !== 'all' && r.model !== _historyModel) return false;
    if (q && !((r.prompt_preview || '').toLowerCase().includes(q) || r.model.toLowerCase().includes(q))) return false;
    return true;
  });
}

function renderHistory() {
  const list = filteredHistory();
  const total = list.length;
  if (_historyOffset >= total && total > 0) _historyOffset = 0;
  const items = list.slice(_historyOffset, _historyOffset + HISTORY_LIMIT);
  document.getElementById('history-table-body').innerHTML = items.length
    ? items.map(r => `<tr>
        <td class="mono dim nowrap">${esc((r.timestamp || '').replace('T', ' ').replace('Z', ''))}</td>
        <td>${modelChip(r.model)}</td>
        <td><div class="prompt-preview" title="${esc(r.prompt_preview || '')}">${esc(r.prompt_preview || '—')}</div></td>
        <td class="num">${(r.prompt_tokens || 0).toLocaleString()}</td>
        <td class="num">${(r.completion_tokens || 0).toLocaleString()}</td>
        <td>${r.status === 'ok' ? '<span class="badge badge-ok">ok</span>' : `<span class="badge badge-err">${esc(r.status)}</span>`}</td>
      </tr>`).join('')
    : '<tr class="empty-row"><td colspan="6">No requests match your filters.</td></tr>';
  document.getElementById('history-page-info').textContent = total
    ? `${_historyOffset + 1}–${Math.min(_historyOffset + items.length, total)} of ${total}`
    : '0 of 0';
  document.getElementById('history-prev').disabled = _historyOffset === 0;
  document.getElementById('history-next').disabled = _historyOffset + HISTORY_LIMIT >= total;
}

function historyPage(dir) {
  const total = filteredHistory().length;
  _historyOffset = Math.max(0, Math.min(_historyOffset + dir * HISTORY_LIMIT, Math.max(0, total - 1)));
  renderHistory();
}
function onHistoryFilter() {
  _historySearch = document.getElementById('history-search').value;
  _historyModel  = document.getElementById('history-model').value;
  _historyOffset = 0;
  renderHistory();
}
function setHistoryStatus(s) {
  _historyStatus = s;
  document.querySelectorAll('.ftab').forEach(t => t.classList.toggle('active', t.dataset.status === s));
  _historyOffset = 0;
  renderHistory();
}
function populateHistoryModels() {
  const unique = [...new Set(_allHistory.map(r => r.model))].sort();
  document.getElementById('history-model').innerHTML =
    '<option value="all">All models</option>' +
    unique.map(m => `<option value="${esc(m)}">${esc(m)}</option>`).join('');
}

/* ── Models ──────────────────────────────────────────────────── */
async function loadModels() {
  showErr('models-err', false);
  try {
    const resp = await api('/v1/models');
    if (!resp.ok) throw new Error();
    const d = await resp.json();
    _models = d.data || [];
  } catch {
    showErr('models-err', true);
  }
  renderModels();
  populateTestSelect();
}

function renderModels() {
  const grid = document.getElementById('model-grid');
  if (!_models.length) {
    grid.innerHTML = '<div style="color:var(--txt-m);padding:20px">No models available.</div>';
    return;
  }
  const CAP_LABEL = { tools: '⚙ tools', streaming: '⚡ stream', reasoning: '🧠 reasoning' };
  grid.innerHTML = _models.map(m => {
    const fam = FAMILY[familyOf(m.id)] || FAMILY.Other;
    const caps = (m.capabilities || [])
      .map(c => CAP_LABEL[c] ? `<span class="cap-chip">${CAP_LABEL[c]}</span>` : '')
      .join('');
    return `<div class="model-card">
      <div class="model-head">
        <span class="model-avatar" style="background:${fam.color}1a;color:${fam.color};border-color:${fam.color}40">${fam.glyph}</span>
        <span class="model-family">${esc(familyOf(m.id))}</span>
      </div>
      <div class="model-id mono">${esc(m.id)}</div>
      <div class="model-owner">owned by <b>${esc(m.owned_by || 'trae')}</b></div>
      ${caps ? `<div class="cap-chips">${caps}</div>` : ''}
      <button class="btn-copy" data-id="${esc(m.id)}" onclick="copyModel(this)">${ICON.copy}<span>Copy ID</span></button>
    </div>`;
  }).join('');
}

function copyModel(btn) {
  const id = btn.dataset.id;
  navigator.clipboard?.writeText(id).catch(() => {});
  btn.classList.add('copied');
  btn.querySelector('span').textContent = 'Copied';
  setTimeout(() => { btn.classList.remove('copied'); btn.querySelector('span').textContent = 'Copy ID'; }, 1600);
}

async function refreshModels(btn) {
  btn.classList.add('spinning');
  await loadModels();
  setTimeout(() => btn.classList.remove('spinning'), 650);
}

/* ── Test Chat ───────────────────────────────────────────────── */
function populateTestSelect() {
  const sel = document.getElementById('model-select');
  if (!_models.length) {
    sel.innerHTML = '<option value="">No models available</option>';
    document.getElementById('run-btn').disabled = true;
    return;
  }
  sel.innerHTML = _models.map(m => `<option value="${esc(m.id)}">${esc(m.id)}</option>`).join('');
  document.getElementById('run-btn').disabled = false;
}

async function runTest() {
  if (_testing) return;
  const model = document.getElementById('model-select').value;
  if (!model) return;
  _testing = true;
  const btn = document.getElementById('run-btn');
  const box = document.getElementById('result-box');
  btn.className = 'btn-run';
  btn.innerHTML = ICON.spinner + 'Testing…';
  btn.disabled = true;
  box.className = 'result-box';
  const t0 = Date.now();
  try {
    const extraHeaders = _testApiKey ? { Authorization: 'Bearer ' + _testApiKey } : {};
    const resp = await api('/v1/chat/completions', {
      method: 'POST',
      body: JSON.stringify({ model, messages: [{ role: 'user', content: 'Hello! Are you working?' }], stream: false }),
      headers: extraHeaders,
    });
    const elapsed = Date.now() - t0;
    if (resp.status === 401) {
      // Session cookie does not grant /v1/chat/completions — show an inline key entry form.
      const msg = (_testApiKey && _apiKeySet)
        ? 'API key incorrect. Try a different key.'
        : 'Test chat requires the API key.';
      box.className = 'result-box visible';
      box.innerHTML = _apiKeySet
        ? `<div class="result-bubble">
            <span class="result-role" style="color:var(--txt-m)">info</span>
            <p class="result-text" style="margin-bottom:10px">${msg}</p>
            <div class="tc-key-row">
              <input id="tc-apikey" type="password" class="tc-key-input" placeholder="Enter API key…" autocomplete="off"
                     onkeydown="if(event.key==='Enter')applyTestKey()">
              <button class="tc-key-btn" onclick="applyTestKey()">Apply &amp; Run</button>
            </div>
          </div>`
        : `<div class="result-bubble">
            <span class="result-role" style="color:var(--txt-m)">info</span>
            <p class="result-text">Test chat requires an API key — set <code>API_KEY</code> in your .env.</p>
          </div>`;
      if (_apiKeySet) setTimeout(() => document.getElementById('tc-apikey')?.focus(), 60);
      btn.className = 'btn-run';
      btn.innerHTML = ICON.play + 'Run Test';
      btn.disabled = false;
      _testing = false;
      return;
    }
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(err.detail || JSON.stringify(err));
    }
    const data = await resp.json();
    const text = data.choices?.[0]?.message?.content ?? '(empty response)';
    box.className = 'result-box visible';
    box.innerHTML = `
      <div class="result-head">
        <span class="badge badge-ok">200 OK</span>
        <span class="result-meta-item">${modelChip(model)}</span>
        <span class="result-meta-item mono">${elapsed} ms</span>
      </div>
      <div class="result-bubble">
        <span class="result-role">assistant</span>
        <p class="result-text">${esc(text)}</p>
      </div>`;
    btn.className = 'btn-run success';
    btn.innerHTML = ICON.check + 'Test passed';
    setTimeout(() => { btn.className = 'btn-run'; btn.innerHTML = ICON.play + 'Run Test'; btn.disabled = false; _testing = false; }, 2400);
  } catch (e) {
    box.className = 'result-box visible';
    box.innerHTML = `<div class="result-bubble">
      <span class="result-role" style="color:var(--red)">error</span>
      <p class="result-text" style="color:var(--red)">${esc(e.message)}</p>
    </div>`;
    btn.className = 'btn-run';
    btn.innerHTML = ICON.play + 'Run Test';
    btn.disabled = false;
    _testing = false;
  }
}

function applyTestKey() {
  const input = document.getElementById('tc-apikey');
  if (!input) return;
  const key = input.value.trim();
  if (!key) { input.focus(); return; }
  _testApiKey = key;
  runTest();
}

/* ── Config ──────────────────────────────────────────────────── */
async function loadConfig() {
  showErr('config-err', false);
  const resp = await api('/config');
  if (resp.status === 401) { showAuthOverlay(); return; }
  if (!resp.ok) { showErr('config-err', true); return; }
  const data = await resp.json();
  renderConfig(data);
  return data;
}

function renderConfig(data) {
  document.getElementById('config-body').innerHTML = CONFIG_GROUPS_DEF.map(g => `
    <div class="cfg-group">
      <div class="cfg-group-head">${ICON[g.icon] || ''}<span>${g.name}</span></div>
      <div class="cfg-rows">
        ${g.keys.map(k => {
          const v = data[k] ?? '—';
          const isEmpty = v === '(not set)' || v === '—' || v === '';
          const isMasked = SENSITIVE.has(k) && !isEmpty;
          const displayVal = isMasked
            ? `<span class="masked mono">${esc(v === '(not set)' ? v : '••••••')}</span><button class="btn-reveal" onclick="reveal(this)">${ICON.eye}Reveal</button>`
            : isEmpty
              ? `<span class="cfg-empty">${esc(v)}</span>`
              : `<span class="mono">${esc(String(v))}</span>`;
          return `<div class="cfg-row">
            <span class="cfg-key mono">${esc(k)}</span>
            <span class="cfg-val">${displayVal}</span>
          </div>`;
        }).join('')}
      </div>
    </div>`).join('');
}

function reveal(btn) {
  const span = btn.parentElement.querySelector('.masked');
  span.textContent = '[stored in .env — not sent to browser]';
  span.classList.add('revealed');
  btn.remove();
}

/* ── Chart tooltip ───────────────────────────────────────────── */
let _tip;
function bindChartTips() {
  if (!_tip) { _tip = document.createElement('div'); _tip.className = 'chart-tip'; document.body.appendChild(_tip); }
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

/* ── Boot ────────────────────────────────────────────────────── */
async function boot() {
  // 1. Auth + config
  const cfgResp = await api('/config');
  if (cfgResp.status === 401) { showAuthOverlay(); return; }
  setStatus(cfgResp.ok);
  if (cfgResp.ok) {
    const cfgData = await cfgResp.json();
    _apiKeySet = cfgData.API_KEY !== '(not set)';
    renderConfig(cfgData);
  }

  // 2. Models (needed for selects)
  try {
    const r = await api('/v1/models');
    if (r.ok) { _models = (await r.json()).data || []; }
  } catch {}
  renderModels();
  populateTestSelect();

  // 3. Daily data (chart + sparklines)
  try {
    const r = await api('/usage/daily?days=7');
    if (r.ok) {
      const d = await r.json();
      _dailyData = (d.items || []).sort((a, b) => a.date < b.date ? -1 : 1).slice(-7);
    }
  } catch {}

  // 4. History (for filter selects on History page)
  try {
    const r = await api('/usage/history?limit=200&offset=0');
    if (r.ok) { _allHistory = (await r.json()).items || []; populateHistoryModels(); }
  } catch {}

  // 5. Render default section
  renderUsage();
  showSection('usage');
}

document.addEventListener('visibilitychange', () => {
  const s = _activeSection();
  if (document.hidden) stopAutoRefresh();
  else if (s === 'usage' || s === 'history') startAutoRefresh();
});

document.addEventListener('DOMContentLoaded', boot);
