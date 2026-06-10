import { esc, modelChip, ICON } from './util.js';
import { state } from './state.js';
import { api } from './api.js';

export async function runTest() {
  if (state.testing) return;
  const model = document.getElementById('model-select').value;
  if (!model) return;
  state.testing = true;
  const btn = document.getElementById('run-btn');
  const box = document.getElementById('result-box');
  btn.className = 'btn-run';
  btn.innerHTML = ICON.spinner + 'Testing…';
  btn.disabled = true;
  box.className = 'result-box';
  const t0 = Date.now();
  try {
    const extraHeaders = state.testApiKey ? { Authorization: 'Bearer ' + state.testApiKey } : {};
    const resp = await api('/v1/chat/completions', {
      method: 'POST',
      body: JSON.stringify({ model, messages: [{ role: 'user', content: 'Hello! Are you working?' }], stream: false }),
      headers: extraHeaders,
    });
    const elapsed = Date.now() - t0;
    if (resp.status === 401) {
      const msg = (state.testApiKey && state.apiKeySet)
        ? 'API key incorrect. Try a different key.'
        : 'Test chat requires the API key.';
      box.className = 'result-box visible';
      box.innerHTML = state.apiKeySet
        ? `<div class="result-bubble">
            <span class="result-role" style="color:var(--txt-m)">info</span>
            <p class="result-text" style="margin-bottom:10px">${msg}</p>
            <div class="tc-key-row">
              <input id="tc-apikey" type="password" class="tc-key-input" placeholder="Enter API key…" autocomplete="off">
              <button class="tc-key-btn">Apply &amp; Run</button>
            </div>
          </div>`
        : `<div class="result-bubble">
            <span class="result-role" style="color:var(--txt-m)">info</span>
            <p class="result-text">Test chat requires an API key — set <code>API_KEY</code> in your .env.</p>
          </div>`;
      if (state.apiKeySet) setTimeout(() => document.getElementById('tc-apikey')?.focus(), 60);
      btn.className = 'btn-run';
      btn.innerHTML = ICON.play + 'Run Test';
      btn.disabled = false;
      state.testing = false;
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
    setTimeout(() => {
      btn.className = 'btn-run';
      btn.innerHTML = ICON.play + 'Run Test';
      btn.disabled = false;
      state.testing = false;
    }, 2400);
  } catch (e) {
    box.className = 'result-box visible';
    box.innerHTML = `<div class="result-bubble">
      <span class="result-role" style="color:var(--red)">error</span>
      <p class="result-text" style="color:var(--red)">${esc(e.message)}</p>
    </div>`;
    btn.className = 'btn-run';
    btn.innerHTML = ICON.play + 'Run Test';
    btn.disabled = false;
    state.testing = false;
  }
}

export function applyTestKey() {
  const input = document.getElementById('tc-apikey');
  if (!input) return;
  const key = input.value.trim();
  if (!key) { input.focus(); return; }
  state.testApiKey = key;
  runTest();
}
