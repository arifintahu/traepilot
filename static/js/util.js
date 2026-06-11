export const ICON = {
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

export const FAMILY = {
  Gemini:   { color: '#60a5fa', glyph: 'G' },
  OpenAI:   { color: '#34d399', glyph: 'O' },
  DeepSeek: { color: '#818cf8', glyph: 'D' },
  Claude:   { color: '#f59e0b', glyph: 'C' },
  Other:    { color: '#7d8694', glyph: '·' },
};

export function familyOf(id) {
  const l = (id || '').toLowerCase();
  if (l.startsWith('gemini'))   return 'Gemini';
  if (l.startsWith('gpt') || l.startsWith('o1') || l.startsWith('o3') || l.startsWith('chatgpt')) return 'OpenAI';
  if (l.startsWith('deepseek')) return 'DeepSeek';
  if (l.startsWith('claude'))   return 'Claude';
  return 'Other';
}

export function modelChip(id) {
  const fam = FAMILY[familyOf(id)] || FAMILY.Other;
  return `<span class="mchip"><span class="mdot" style="background:${fam.color}"></span>${esc(id)}</span>`;
}

export function fmt(n) {
  if (n == null || isNaN(n)) return '0';
  if (n >= 1e6) return (n / 1e6).toFixed(1) + '<i>M</i>';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + '<i>k</i>';
  return String(n);
}

export function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

export function toLocalDT(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return isNaN(d) ? iso : d.toLocaleString();
}

export function showErr(id, visible) {
  document.getElementById(id)?.classList.toggle('visible', visible);
}
