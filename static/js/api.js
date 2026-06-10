export async function api(url, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  return fetch(url, { ...opts, headers });
}

export function showAuthOverlay() {
  document.getElementById('auth-overlay').classList.add('visible');
  setTimeout(() => document.getElementById('auth-input').focus(), 60);
}

export function hideAuthOverlay() {
  document.getElementById('auth-overlay').classList.remove('visible');
}

export async function submitLogin(onSuccess) {
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
    onSuccess();
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

export async function logout() {
  await fetch('/auth/logout', { method: 'POST' });
  location.reload();
}

export function setStatus(ok) {
  const dot = document.getElementById('status-dot');
  const lbl = document.getElementById('status-label');
  dot.className = 'dot' + (ok ? '' : ' offline');
  lbl.textContent = ok ? 'Proxy running' : 'Proxy unreachable';
}
