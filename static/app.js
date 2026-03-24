/**
 * app.js — TrustGuard shared frontend utilities
 * Role system, API helpers, reusable UI components
 */

// ── Role System ───────────────────────────────────────────────────────────────

const ROLES = ['buyer', 'seller', 'admin'];

function getRole() {
  return localStorage.getItem('tg_role') || 'buyer';
}

function setRole(role) {
  localStorage.setItem('tg_role', role);
  applyRoleUI();
  window.location.reload();
}

function applyRoleUI() {
  const role = getRole();
  document.querySelectorAll('[data-role]').forEach(el => {
    const allowed = el.dataset.role.split(',').map(r => r.trim());
    el.style.display = allowed.includes(role) ? '' : 'none';
  });
  document.querySelectorAll('.role-btn').forEach(btn => {
    btn.classList.toggle('role-btn-active', btn.dataset.setRole === role);
  });
}

// ── API Helpers ───────────────────────────────────────────────────────────────

async function apiFetch(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function apiPost(url, data) {
  return apiFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}

async function apiPut(url, data) {
  return apiFetch(url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}

async function apiFormPost(url, formData) {
  return apiFetch(url, { method: 'POST', body: formData });
}

// ── Trust Score Helpers ───────────────────────────────────────────────────────

function trustColor(score) {
  if (score >= 70) return { bg: 'bg-emerald-100', text: 'text-emerald-700', border: 'border-emerald-300', bar: 'bg-emerald-500', hex: '#10b981' };
  if (score >= 40) return { bg: 'bg-amber-100',   text: 'text-amber-700',   border: 'border-amber-300',   bar: 'bg-amber-500',   hex: '#f59e0b' };
  return               { bg: 'bg-red-100',         text: 'text-red-700',     border: 'border-red-300',     bar: 'bg-red-500',     hex: '#ef4444' };
}

function riskIcon(level) {
  if (level === 'Safe')      return '✅';
  if (level === 'Caution')   return '⚠️';
  if (level === 'High Risk') return '🚫';
  return '❓';
}

function trustBadge(score, riskLevel) {
  const c = trustColor(score);
  const icon = riskIcon(riskLevel);
  return `<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold ${c.bg} ${c.text} border ${c.border}">
    ${icon} ${riskLevel}
  </span>`;
}

function trustBar(score) {
  const c = trustColor(score);
  return `
    <div class="w-full bg-gray-200 rounded-full h-2.5">
      <div class="${c.bar} h-2.5 rounded-full transition-all duration-700" style="width:${score}%"></div>
    </div>`;
}

// ── Status Badge ──────────────────────────────────────────────────────────────

function statusBadge(status) {
  const map = {
    queued:    'bg-slate-100 text-slate-600 border-slate-300',
    done:      'bg-emerald-100 text-emerald-700 border-emerald-300',
    open:      'bg-blue-100 text-blue-700 border-blue-300',
    resolved:  'bg-gray-100 text-gray-600 border-gray-300',
    pending:   'bg-amber-100 text-amber-700 border-amber-300',
    approved:  'bg-emerald-100 text-emerald-700 border-emerald-300',
    rejected:  'bg-red-100 text-red-700 border-red-300',
    spam:      'bg-orange-100 text-orange-700 border-orange-300',
  };
  const cls = map[status] || 'bg-gray-100 text-gray-600 border-gray-300';
  const spinner = status === 'queued'
    ? `<svg class="animate-spin h-3 w-3 mr-1" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"></path>
       </svg>` : '';
  return `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${cls}">
    ${spinner}${status}
  </span>`;
}

function adminStatusBadge(s) { return statusBadge(s); }

// ── Signal Card ───────────────────────────────────────────────────────────────

function signalCard(label, value, unit = '', icon = '📊', colorFn = null) {
  const displayVal = typeof value === 'number' ? (Number.isInteger(value) ? value : value.toFixed(3)) : value;
  const color = colorFn ? colorFn(value) : 'text-slate-700';
  return `
    <div class="bg-white rounded-xl border border-slate-200 p-4 flex items-start gap-3 hover:shadow-md transition-shadow">
      <span class="text-2xl">${icon}</span>
      <div class="min-w-0">
        <p class="text-xs text-slate-500 uppercase tracking-wide font-medium">${label}</p>
        <p class="text-xl font-bold mt-0.5 ${color}">${displayVal}<span class="text-sm font-normal text-slate-400 ml-1">${unit}</span></p>
      </div>
    </div>`;
}

// ── Warning Banner ────────────────────────────────────────────────────────────

function warningBanner(msg, type = 'warn') {
  const map = {
    warn:  'bg-amber-50 border-amber-400 text-amber-800',
    error: 'bg-red-50 border-red-400 text-red-800',
    info:  'bg-blue-50 border-blue-400 text-blue-800',
    ok:    'bg-emerald-50 border-emerald-400 text-emerald-800',
  };
  const icons = { warn: '⚠️', error: '🚫', info: 'ℹ️', ok: '✅' };
  return `<div class="border-l-4 p-4 rounded-r-xl ${map[type]} flex items-start gap-2">
    <span>${icons[type]}</span>
    <p class="text-sm font-medium">${msg}</p>
  </div>`;
}

// ── Loading Skeleton ──────────────────────────────────────────────────────────

function skeleton(lines = 3) {
  return Array.from({ length: lines }, () =>
    `<div class="h-4 bg-slate-200 rounded animate-pulse mb-2"></div>`
  ).join('');
}

function loadingCard(msg = 'Loading…') {
  return `<div class="flex items-center justify-center gap-3 py-12 text-slate-400">
    <svg class="animate-spin h-6 w-6" fill="none" viewBox="0 0 24 24">
      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"></path>
    </svg>
    <span class="text-sm">${msg}</span>
  </div>`;
}

// ── Escape HTML ───────────────────────────────────────────────────────────────

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );
}

// ── Format helpers ────────────────────────────────────────────────────────────

function fmtPrice(v) { return `$${parseFloat(v).toFixed(2)}`; }
function fmtScore(v) { return Math.round(v); }
function fmtDate(d)  { return d ? new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'; }
function mismatchBar(score) {
  const pct = Math.round(score * 100);
  const col = pct >= 60 ? 'bg-red-500' : pct >= 30 ? 'bg-amber-500' : 'bg-emerald-500';
  return `<div class="flex items-center gap-2">
    <div class="flex-1 bg-gray-200 rounded-full h-1.5">
      <div class="${col} h-1.5 rounded-full" style="width:${pct}%"></div>
    </div>
    <span class="text-xs font-mono text-slate-600 w-8">${pct}%</span>
  </div>`;
}

// ── Init on DOM ready ─────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  applyRoleUI();
});

window.TG = {
  getRole, setRole, applyRoleUI,
  apiFetch, apiPost, apiPut, apiFormPost,
  trustColor, riskIcon, trustBadge, trustBar,
  statusBadge, adminStatusBadge, signalCard,
  warningBanner, skeleton, loadingCard,
  esc, fmtPrice, fmtScore, fmtDate, mismatchBar,
};
