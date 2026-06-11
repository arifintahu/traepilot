import { api, hideAuthOverlay, logout, setStatus, showAuthOverlay, submitLogin } from './api.js';
import { ICON } from './util.js';
import { state, REFRESH_INTERVAL } from './state.js';
import { renderUsage } from './usage.js';
import { closeHistoryDetail, historyPage, loadHistory, onHistoryFilter, renderHistory, setHistoryStatus, showHistoryDetail } from './history.js';
import { copyModel, loadModels, refreshModels, renderModels, populateTestSelect } from './models.js';
import { applyTestKey, runTest } from './chat.js';
import { loadConfig, renderConfig, reveal } from './config.js';

// One-time migration: remove legacy key storage
sessionStorage.removeItem('tp_key');

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
    ? `<button class="btn-ghost">${ICON.refresh}Refresh</button>`
    : liveSection
    ? `<span class="live-badge"><span class="live-dot"></span>Live</span>` : '';
  if (name === 'history') { state.historyOffset = 0; renderHistory(); }
  if (liveSection) startAutoRefresh(); else stopAutoRefresh();
}

function setPeriod(p) {
  state.period = p;
  document.querySelectorAll('.ptab').forEach(t => {
    const a = t.dataset.period === p;
    t.classList.toggle('active', a);
    t.setAttribute('aria-selected', String(a));
  });
  renderUsage();
}

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
        state.dailyData = (d.items || []).sort((a, b) => a.date < b.date ? -1 : 1).slice(-7);
      }
    } catch {}
    await renderUsage();
  } else if (s === 'history') {
    await loadHistory();
  }
}

function startAutoRefresh() {
  stopAutoRefresh();
  state.refreshTimer = setInterval(_doRefresh, REFRESH_INTERVAL);
}

function stopAutoRefresh() {
  if (state.refreshTimer) { clearInterval(state.refreshTimer); state.refreshTimer = null; }
}

async function boot() {
  const cfgResp = await api('/config');
  if (cfgResp.status === 401) { showAuthOverlay(); return; }
  setStatus(cfgResp.ok);
  if (cfgResp.ok) {
    const cfgData = await cfgResp.json();
    state.apiKeySet = cfgData.API_KEY !== '(not set)';
    renderConfig(cfgData);
  }

  try {
    const r = await api('/v1/models');
    if (r.ok) { state.models = (await r.json()).data || []; }
  } catch {}
  renderModels();
  populateTestSelect();

  try {
    const r = await api('/usage/daily?days=7');
    if (r.ok) {
      const d = await r.json();
      state.dailyData = (d.items || []).sort((a, b) => a.date < b.date ? -1 : 1).slice(-7);
    }
  } catch {}

  try {
    const r = await api('/usage/history?limit=200&offset=0');
    if (r.ok) {
      const { populateHistoryModels } = await import('./history.js');
      state.allHistory = (await r.json()).items || [];
      populateHistoryModels();
    }
  } catch {}

  renderUsage();
  showSection('usage');
}

function wireEvents() {
  // Navigation
  document.querySelectorAll('.nav-item').forEach(el => {
    el.addEventListener('click', () => showSection(el.dataset.section));
    el.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); showSection(el.dataset.section); }
    });
  });

  // Period tabs
  document.querySelectorAll('.ptab').forEach(el => {
    el.addEventListener('click', () => setPeriod(el.dataset.period));
  });

  // Auth overlay
  document.getElementById('auth-btn').addEventListener('click', () => submitLogin(boot));
  document.getElementById('auth-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') submitLogin(boot);
  });

  // Logout
  document.querySelector('.btn-logout').addEventListener('click', logout);

  // History filters
  document.getElementById('history-search').addEventListener('input', onHistoryFilter);
  document.getElementById('history-model').addEventListener('change', onHistoryFilter);
  document.querySelectorAll('.ftab').forEach(el => {
    el.addEventListener('click', () => setHistoryStatus(el.dataset.status));
  });
  document.getElementById('history-prev').addEventListener('click', () => historyPage(-1));
  document.getElementById('history-next').addEventListener('click', () => historyPage(1));

  // History rows (delegated — rows are dynamically rendered with data-id)
  document.getElementById('history-table-body').addEventListener('click', e => {
    const row = e.target.closest('.history-row');
    if (row) showHistoryDetail(Number(row.dataset.id));
  });

  // History modal
  document.getElementById('req-detail-overlay').addEventListener('click', closeHistoryDetail);
  document.getElementById('modal-close-btn').addEventListener('click', e => {
    e.stopPropagation();
    closeHistoryDetail();
  });

  // Topbar action: Refresh models button (dynamically injected by showSection)
  document.getElementById('topbar-action').addEventListener('click', e => {
    const btn = e.target.closest('.btn-ghost');
    if (btn) refreshModels(btn);
  });

  // Error retry buttons
  document.getElementById('usage-err').querySelector('button').addEventListener('click', renderUsage);
  document.getElementById('history-err').querySelector('button').addEventListener('click', loadHistory);
  document.getElementById('models-err').querySelector('button').addEventListener('click', loadModels);
  document.getElementById('config-err').querySelector('button').addEventListener('click', loadConfig);

  // Test chat
  document.getElementById('run-btn').addEventListener('click', runTest);
  document.getElementById('result-box').addEventListener('click', e => {
    if (e.target.matches('.tc-key-btn')) applyTestKey();
  });
  document.getElementById('result-box').addEventListener('keydown', e => {
    if (e.target.id === 'tc-apikey' && e.key === 'Enter') applyTestKey();
  });

  // Config reveal (delegated — injected by renderConfig)
  document.getElementById('config-body').addEventListener('click', e => {
    const btn = e.target.closest('.btn-reveal');
    if (btn) reveal(btn);
  });

  // Model copy (delegated)
  document.getElementById('model-grid').addEventListener('click', e => {
    const btn = e.target.closest('.btn-copy');
    if (btn) copyModel(btn);
  });

  // Global keyboard
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeHistoryDetail();
  });

  // Visibility
  document.addEventListener('visibilitychange', () => {
    const s = _activeSection();
    if (document.hidden) stopAutoRefresh();
    else if (s === 'usage' || s === 'history') startAutoRefresh();
  });
}

document.addEventListener('DOMContentLoaded', () => {
  wireEvents();
  boot();
});
