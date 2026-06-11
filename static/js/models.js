import { esc, familyOf, FAMILY, ICON, showErr } from './util.js';
import { state } from './state.js';
import { api } from './api.js';

export async function loadModels() {
  showErr('models-err', false);
  try {
    const resp = await api('/v1/models');
    if (!resp.ok) throw new Error();
    const d = await resp.json();
    state.models = d.data || [];
  } catch {
    showErr('models-err', true);
  }
  renderModels();
  populateTestSelect();
}

export function renderModels() {
  const grid = document.getElementById('model-grid');
  if (!state.models.length) {
    grid.innerHTML = '<div style="color:var(--txt-m);padding:20px">No models available.</div>';
    return;
  }
  const CAP_LABEL = { tools: '⚙ tools', streaming: '⚡ stream', reasoning: '🧠 reasoning' };
  grid.innerHTML = state.models.map(m => {
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
      <button class="btn-copy" data-id="${esc(m.id)}">${ICON.copy}<span>Copy ID</span></button>
    </div>`;
  }).join('');
}

export function copyModel(btn) {
  const id = btn.dataset.id;
  navigator.clipboard?.writeText(id).catch(() => {});
  btn.classList.add('copied');
  btn.querySelector('span').textContent = 'Copied';
  setTimeout(() => { btn.classList.remove('copied'); btn.querySelector('span').textContent = 'Copy ID'; }, 1600);
}

export async function refreshModels(btn) {
  btn.classList.add('spinning');
  await loadModels();
  setTimeout(() => btn.classList.remove('spinning'), 650);
}

export function populateTestSelect() {
  const sel = document.getElementById('model-select');
  if (!state.models.length) {
    sel.innerHTML = '<option value="">No models available</option>';
    document.getElementById('run-btn').disabled = true;
    return;
  }
  sel.innerHTML = state.models.map(m => `<option value="${esc(m.id)}">${esc(m.id)}</option>`).join('');
  document.getElementById('run-btn').disabled = false;
}
