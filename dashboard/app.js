/* Landing page — app.js */
const API_BASE = 'http://localhost:8000';

async function checkHealth() {
  const dot   = document.getElementById('strip-dot');
  const label = document.getElementById('strip-label');
  try {
    const r = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(4000) });
    if (r.ok) {
      dot.classList.add('online');
      label.textContent = 'API Online — ready to process tickets';
    } else throw new Error();
  } catch {
    dot.classList.remove('online');
    label.textContent = 'API Offline — start docker compose up';
  }
}

function goCustomer() {
  window.location.href = 'user.html';
}

function adminLogin() {
  const input = document.getElementById('admin-token-input');
  const err   = document.getElementById('token-error');
  const token = input.value.trim();
  if (!token) { err.textContent = 'Please enter your admin token.'; return; }

  // Store token for admin page
  sessionStorage.setItem('admin_token', token);

  // Quick verify: pre-check against API
  fetch(`${API_BASE}/admin/stats`, {
    headers: { 'x-admin-token': token },
    signal: AbortSignal.timeout(5000),
  }).then(r => {
    if (r.ok) {
      window.location.href = 'admin.html';
    } else if (r.status === 403) {
      err.textContent = '❌ Invalid token. Try: cartly-admin-2026';
      err.classList.add('token-error');
      sessionStorage.removeItem('admin_token');
    } else {
      // API error but token might be right — let admin page handle it
      window.location.href = 'admin.html';
    }
  }).catch(() => {
    // Offline — still navigate, admin page shows error
    window.location.href = 'admin.html';
  });
}

document.addEventListener('DOMContentLoaded', () => {
  checkHealth();
  setInterval(checkHealth, 30_000);
});
