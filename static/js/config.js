import { esc, ICON, showErr } from './util.js';
import { CONFIG_GROUPS_DEF, SENSITIVE } from './state.js';
import { api, showAuthOverlay } from './api.js';

export async function loadConfig() {
  showErr('config-err', false);
  const resp = await api('/config');
  if (resp.status === 401) { showAuthOverlay(); return; }
  if (!resp.ok) { showErr('config-err', true); return; }
  const data = await resp.json();
  renderConfig(data);
  return data;
}

export function renderConfig(data) {
  document.getElementById('config-body').innerHTML = CONFIG_GROUPS_DEF.map(g => `
    <div class="cfg-group">
      <div class="cfg-group-head">${ICON[g.icon] || ''}<span>${g.name}</span></div>
      <div class="cfg-rows">
        ${g.keys.map(k => {
          const v = data[k] ?? '—';
          const isEmpty = v === '(not set)' || v === '—' || v === '';
          const isMasked = SENSITIVE.has(k) && !isEmpty;
          const displayVal = isMasked
            ? `<span class="masked mono">${esc(v === '(not set)' ? v : '••••••')}</span><button class="btn-reveal">${ICON.eye}Reveal</button>`
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

export function reveal(btn) {
  const span = btn.parentElement.querySelector('.masked');
  span.textContent = '[stored in .env — not sent to browser]';
  span.classList.add('revealed');
  btn.remove();
}
