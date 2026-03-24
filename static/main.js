/* TrustMart — shared utilities (role management lives in base.html) */

// Global escapeHtml used by any inline script
function escapeHtml(s) {
  return String(s || '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

// Shared trust badge helper
function trustBadge(risk) {
  const map = {
    'Safe':      'bg-green-100 text-green-700',
    'Caution':   'bg-yellow-100 text-yellow-700',
    'High Risk': 'bg-red-100 text-red-700',
  };
  return `<span class="badge ${map[risk] || 'bg-gray-100 text-gray-500'}">${risk || '—'}</span>`;
}
