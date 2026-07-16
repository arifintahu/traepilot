import { esc, ICON, showErr, toLocalDT } from './util.js';
import { CONFIG_GROUPS_DEF, SENSITIVE, state } from './state.js';
import { api, showAuthOverlay } from './api.js';

const PENCIL = '<svg viewBox="0 0 24 24" fill="none"><path d="M4 20h4L18 10l-4-4L4 16v4z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M13.5 6.5l4 4" stroke="currentColor" stroke-width="1.7"/></svg>';

// Token row state: masked → revealed → editing. Value is only fetched on reveal
// or held while editing; it is never sent down with the /config payload.
const tokenState = { isSet: false, revealed: false, editing: false, value: '' };

export async function loadConfig() {
  showErr('config-err', false);
  const resp = await api('/config');
  if (resp.status === 401) { showAuthOverlay(); return; }
  if (!resp.ok) { showErr('config-err', true); return; }
  const data = await resp.json();
  renderConfig(data);
  loadHealth();
  return data;
}

export function renderConfig(data) {
  tokenState.isSet = !!data.TRAE_IDE_TOKEN && data.TRAE_IDE_TOKEN !== '(not set)';
  tokenState.revealed = false;
  tokenState.editing = false;
  tokenState.value = '';
  document.getElementById('config-body').innerHTML = CONFIG_GROUPS_DEF.map(g => `
    <div class="cfg-group">
      <div class="cfg-group-head">${ICON[g.icon] || ''}<span>${g.name}</span></div>
      <div class="cfg-rows">
        ${g.keys.map(k => k === 'TRAE_IDE_TOKEN' ? tokenRow() : staticRow(k, data[k])).join('')}
      </div>
    </div>`).join('');
}

function staticRow(k, v) {
  v = v ?? '—';
  const isEmpty = v === '(not set)' || v === '—' || v === '';
  const isMasked = SENSITIVE.has(k) && !isEmpty;
  const displayVal = isMasked
    ? `<span class="masked mono">••••••</span><button class="btn-reveal" data-reveal>${ICON.eye}Reveal</button>`
    : isEmpty
      ? `<span class="cfg-empty">${esc(v)}</span>`
      : `<span class="mono">${esc(String(v))}</span>`;
  return `<div class="cfg-row">
    <span class="cfg-key mono">${esc(k)}</span>
    <span class="cfg-val">${displayVal}</span>
  </div>`;
}

function tokenRow() {
  return `<div class="cfg-row">
    <span class="cfg-key mono">TRAE_IDE_TOKEN</span>
    <span class="cfg-val" data-token-val>${tokenValInner()}</span>
  </div>`;
}

function tokenValInner() {
  if (tokenState.editing) {
    return `<input class="token-input mono" type="text" spellcheck="false" autocomplete="off"
              placeholder="Paste new token…" value="${esc(tokenState.value)}" data-token-input>
      <button class="btn-reveal" data-token-save>${ICON.check}Save</button>
      <button class="btn-reveal" data-token-cancel>Cancel</button>`;
  }
  if (tokenState.revealed) {
    const v = tokenState.value || '';
    const shown = v.length > 43 ? `${v.slice(0, 20)}...${v.slice(-20)}` : (v || '(not set)');
    return `<span class="mono token-shown" title="showing first & last 20 chars">${esc(shown)}</span>
      <button class="btn-reveal" data-token-reveal>${ICON.eye}Hide</button>
      <button class="btn-reveal" data-token-edit>${PENCIL}Edit</button>`;
  }
  if (!tokenState.isSet) {
    return `<span class="cfg-empty">(not set)</span>
      <button class="btn-reveal" data-token-edit>${PENCIL}Set</button>`;
  }
  return `<span class="masked mono">••••••</span>
    <button class="btn-reveal" data-token-reveal>${ICON.eye}Reveal</button>
    <button class="btn-reveal" data-token-edit>${PENCIL}Edit</button>`;
}

function renderTokenVal() {
  const el = document.querySelector('[data-token-val]');
  if (el) el.innerHTML = tokenValInner();
}

// Generic reveal for secrets that are never sent to the browser (API_KEY, etc.)
export function reveal(btn) {
  const span = btn.parentElement.querySelector('.masked');
  span.textContent = '[stored in .env — not sent to browser]';
  span.classList.add('revealed');
  btn.remove();
}

async function fetchToken() {
  const resp = await api('/config/ide-token');
  if (resp.status === 401) { showAuthOverlay(); return null; }
  if (!resp.ok) return null;
  return (await resp.json()).token || '';
}

export async function saveToken() {
  const inp = document.querySelector('[data-token-input]');
  if (!inp) return;
  const token = inp.value.trim();
  const resp = await api('/config/ide-token', {
    method: 'PUT', body: JSON.stringify({ token }),
  });
  if (resp.status === 401) { showAuthOverlay(); return; }
  if (!resp.ok) return;
  tokenState.editing = false;
  tokenState.revealed = false;
  tokenState.value = '';
  tokenState.isSet = !!token;
  renderTokenVal();
  runHealthCheck();  // new token → re-validate immediately
}

export async function onTokenClick(e) {
  if (e.target.closest('[data-token-reveal]')) {
    if (tokenState.revealed) { tokenState.revealed = false; tokenState.value = ''; renderTokenVal(); return; }
    const v = await fetchToken();
    if (v === null) return;
    tokenState.value = v;
    tokenState.revealed = true;
    renderTokenVal();
  } else if (e.target.closest('[data-token-edit]')) {
    tokenState.value = tokenState.revealed ? tokenState.value : '';
    tokenState.editing = true;
    renderTokenVal();
    document.querySelector('[data-token-input]')?.focus();
  } else if (e.target.closest('[data-token-save]')) {
    await saveToken();
  } else if (e.target.closest('[data-token-cancel]')) {
    tokenState.editing = false;
    tokenState.revealed = false;
    tokenState.value = '';
    renderTokenVal();
  }
}

// ── Token health ─────────────────────────────────────────────────────────────

const HEALTH_STATUS = {
  ok:      { cls: 'badge-ok',      label: 'Healthy' },
  error:   { cls: 'badge-err',     label: 'Failing' },
  unknown: { cls: 'badge-unknown', label: 'Unknown' },
};

export async function fetchHealth() {
  const resp = await api('/trae-health');
  if (resp.status === 401) { showAuthOverlay(); return null; }
  if (!resp.ok) return null;
  const s = await resp.json();
  state.health = { status: s.status, detail: s.detail };
  return s;
}

export async function loadHealth() {
  const s = await fetchHealth();
  if (!s) {
    document.getElementById('health-body').innerHTML =
      '<div class="cfg-empty" style="padding:16px 22px">Failed to load health status</div>';
    return;
  }
  renderHealth(s);
}

// Topbar status badge (replaces the old "Live" indicator).
export function healthBadgeHTML() {
  const s = state.health.status || 'unknown';
  const st = HEALTH_STATUS[s] || HEALTH_STATUS.unknown;
  return `<span class="health-badge ${s}" title="${esc(state.health.detail || '')}"><span class="health-dot health-dot-${s}"></span>${st.label}</span>`;
}

function syncTopbarBadge() {
  const el = document.getElementById('topbar-action');
  if (el && el.querySelector('.health-badge')) el.innerHTML = healthBadgeHTML();
}

export async function refreshHealthBadge() {
  await fetchHealth();
  syncTopbarBadge();
}

function epochToLocal(sec) {
  return sec ? toLocalDT(new Date(sec * 1000).toISOString()) : '—';
}

export function renderHealth(s) {
  state.health = { status: s.status, detail: s.detail };
  syncTopbarBadge();
  const st = HEALTH_STATUS[s.status] || HEALTH_STATUS.unknown;
  document.getElementById('health-body').innerHTML = `
    <div class="health-status-row">
      <span class="health-dot health-dot-${s.status || 'unknown'}"></span>
      <span class="badge ${st.cls}">${st.label}</span>
      <span class="health-detail mono">${esc(s.detail || '')}</span>
    </div>
    <div class="cfg-row"><span class="cfg-key mono">Last check</span><span class="cfg-val mono">${esc(epochToLocal(s.checked_at))}</span></div>
    <div class="cfg-row"><span class="cfg-key mono">Next check</span><span class="cfg-val mono">${esc(epochToLocal(s.next_check_at))}</span></div>
    <div class="cfg-row">
      <span class="cfg-key mono">Interval (hours)</span>
      <span class="cfg-val">
        <input class="interval-input mono" type="number" min="0.1" step="0.5"
               value="${esc(String(s.interval_hours))}" data-interval-input>
        <button class="btn-reveal" data-interval-save>${ICON.check}Save</button>
      </span>
    </div>
    <div class="health-actions">
      <button class="btn-ghost" data-health-check>${ICON.refresh}Check now</button>
    </div>`;
}

export async function runHealthCheck(btn) {
  if (btn) btn.classList.add('spinning');
  const resp = await api('/trae-health/check', { method: 'POST' });
  if (btn) btn.classList.remove('spinning');
  if (resp.status === 401) { showAuthOverlay(); return; }
  if (resp.ok) renderHealth(await resp.json());
}

export async function saveInterval() {
  const inp = document.querySelector('[data-interval-input]');
  if (!inp) return;
  const hours = parseFloat(inp.value);
  if (!(hours > 0)) return;
  const resp = await api('/trae-health/interval', {
    method: 'PUT', body: JSON.stringify({ hours }),
  });
  if (resp.status === 401) { showAuthOverlay(); return; }
  if (resp.ok) renderHealth(await resp.json());
}

export function onHealthClick(e) {
  const check = e.target.closest('[data-health-check]');
  if (check) { runHealthCheck(check); return; }
  if (e.target.closest('[data-interval-save]')) saveInterval();
}
