/* ──────────────────────────────────────────────────────────────
   Cartly — Landing Page Logic (app.js)
────────────────────────────────────────────────────────────── */
'use strict';

const API_BASE = 'http://localhost:8000';

function goCustomer() {
  window.location.href = 'user.html';
}

function adminLogin() {
  const tokenEl = document.getElementById('admin-token-input');
  const errEl   = document.getElementById('token-error');
  const val     = tokenEl ? tokenEl.value.trim() : '';
  if (!val) {
    if (errEl) errEl.textContent = 'Please enter a token.';
    return;
  }
  // Store token and redirect
  sessionStorage.setItem('cartly_admin_token', val);
  window.location.href = `admin.html`;
}

// ── API health check ───────────────────────────────────────────
async function checkAPI() {
  const dot  = document.getElementById('strip-dot');
  const text = document.getElementById('strip-text');
  if (!dot || !text) return;
  try {
    const r = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(4000) });
    const d = await r.json();
    dot.className = 'status-dot online';
    text.textContent = `API Online · v${d.version || '1.0.0'}`;
  } catch {
    dot.className = 'status-dot offline';
    text.textContent = 'API Offline';
  }
}

document.addEventListener('DOMContentLoaded', checkAPI);
