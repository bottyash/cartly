/* ──────────────────────────────────────────────────────────────
   Cartly — Admin Dashboard (admin.js)
   Handles: stats cards, 4 charts, ticket table, trace modal
────────────────────────────────────────────────────────────── */
'use strict';

const API_BASE    = 'http://localhost:8000';
let ADMIN_TOKEN = sessionStorage.getItem('cartly_admin_token') || 'cartly-admin-2026';

let allTickets = [];
let charts     = {};

const CHART_COLORS = {
  green:  '#059669', amber: '#d97706',
  purple: '#7c3aed', red:   '#dc2626',
  blue:   '#1d4ed8', cyan:  '#0891b2',
};

Chart.defaults.color          = '#64748b';
Chart.defaults.borderColor    = '#e2e8f0';
Chart.defaults.font.family    = "'Inter', sans-serif";
Chart.defaults.font.size      = 12;

const adminHeaders = () => ({ 'x-admin-token': ADMIN_TOKEN });

function initDashboard(token) {
  ADMIN_TOKEN = token;
  sessionStorage.setItem('cartly_admin_token', token);
  loadDashboard();
}

// ── Utility ───────────────────────────────────────────────────────────────

function esc(str) {
  return String(str ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function formatMs(ms) {
  if (ms >= 1000) return (ms / 1000).toFixed(1) + 's';
  return Math.round(ms) + 'ms';
}

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('en-IN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// ── Health check ──────────────────────────────────────────────────────────

async function checkHealth() {
  // handled in admin.html inline script
}

// ── Load dashboard ────────────────────────────────────────────────────────

async function loadDashboard() {
  const label = document.getElementById('last-refresh-label');
  if (label) label.textContent = 'Loading…';
  await Promise.all([loadStats(), loadTickets()]);
  if (label) label.textContent = `Last updated: ${new Date().toLocaleTimeString('en-IN')}`;
}

async function refreshAll() { loadDashboard(); }

async function loadStats() {
  try {
    const r = await fetch(`${API_BASE}/admin/stats`, { headers: adminHeaders() });
    if (!r.ok) { showStatsError(r.status); return; }
    const data = await r.json();
    renderStats(data);
    renderCharts(data);
    renderFRCoverage(data.fr_coverage);
  } catch (err) {
    showStatsError(err.message);
  }
}

async function loadTickets() {
  try {
    const r = await fetch(`${API_BASE}/admin/tickets`, { headers: adminHeaders() });
    if (!r.ok) { renderTableError(r.status); return; }
    allTickets = await r.json();
    renderTable(allTickets);
  } catch (err) {
    renderTableError(err.message);
  }
}

// ── Stats cards ───────────────────────────────────────────────────────────

function renderStats(data) {
  const rate = data.resolution_rate != null
    ? (data.resolution_rate * 100).toFixed(1) + '%'
    : '—';

  document.getElementById('val-total').textContent     = data.total_tickets;
  document.getElementById('val-resolved').textContent  = rate;
  document.getElementById('sub-resolved').textContent  = `${data.resolved} resolved`;
  document.getElementById('val-escalated').textContent = data.escalated;
  document.getElementById('sub-escalated').textContent = `of ${data.total_tickets} tickets`;
  document.getElementById('val-latency').textContent   = formatMs(data.avg_latency_ms || 0);
  document.getElementById('val-tokens').textContent    = data.total_tokens
    ? (data.total_tokens >= 1000 ? (data.total_tokens / 1000).toFixed(1) + 'K' : data.total_tokens)
    : '—';
}

function showStatsError(detail) {
  ['val-total','val-resolved','val-escalated','val-latency','val-tokens']
    .forEach(id => document.getElementById(id).textContent = '—');
}

// ── Charts ────────────────────────────────────────────────────────────────

function renderCharts(data) {
  renderDonut(data);
  renderVolumeBar(data.tickets_by_day || {});
  renderLatencyLine(data.avg_latency_by_day || {});
  renderTriggersBar(data.escalation_triggers || {});
}

function mkChart(id, config) {
  const existing = charts[id];
  if (existing) existing.destroy();
  const ctx = document.getElementById(id)?.getContext('2d');
  if (!ctx) return;
  charts[id] = new Chart(ctx, config);
}

// Resolution donut
function renderDonut(data) {
  const resolved   = data.resolved   || 0;
  const escalated  = data.escalated  || 0;
  const total      = resolved + escalated;
  const pctR = total ? Math.round((resolved  / total) * 100) : 0;
  const pctE = total ? Math.round((escalated / total) * 100) : 0;

  mkChart('chart-resolution', {
    type: 'doughnut',
    data: {
      labels: ['Resolved', 'Escalated'],
      datasets: [{
        data: [resolved, escalated],
        backgroundColor: [CHART_COLORS.green + 'cc', CHART_COLORS.amber + 'cc'],
        borderColor:     [CHART_COLORS.green,          CHART_COLORS.amber],
        borderWidth: 2,
        hoverOffset: 6,
      }],
    },
    options: {
      cutout: '72%',
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.label}: ${ctx.raw} (${ctx.label==='Resolved'?pctR:pctE}%)`,
          },
        },
      },
      animation: { animateRotate: true, duration: 800 },
    },
  });

  // Legend
  document.getElementById('donut-legend').innerHTML = `
    <div class="legend-item"><div class="legend-dot" style="background:${CHART_COLORS.green}"></div>Resolved — ${pctR}%</div>
    <div class="legend-item"><div class="legend-dot" style="background:${CHART_COLORS.amber}"></div>Escalated — ${pctE}%</div>
  `;
}

// Daily volume bar
function renderVolumeBar(byDay) {
  const labels = Object.keys(byDay).slice(-7).map(d => {
    const dt = new Date(d);
    return dt.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' });
  });
  const values = Object.values(byDay).slice(-7);

  mkChart('chart-volume', {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Tickets',
        data: values,
        backgroundColor: CHART_COLORS.blue + '88',
        borderColor:     CHART_COLORS.blue,
        borderWidth: 1.5,
        borderRadius: 4,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false } },
        y: { beginAtZero: true, ticks: { precision: 0 } },
      },
    },
  });
}

// Avg latency line
function renderLatencyLine(byDay) {
  const labels = Object.keys(byDay).slice(-7).map(d => {
    const dt = new Date(d);
    return dt.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' });
  });
  const values = Object.values(byDay).slice(-7);

  mkChart('chart-latency', {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Avg Latency (ms)',
        data: values,
        borderColor:      CHART_COLORS.cyan,
        backgroundColor:  CHART_COLORS.cyan + '15',
        borderWidth: 2,
        pointBackgroundColor: CHART_COLORS.cyan,
        pointRadius: 4,
        tension: 0.4,
        fill: true,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false } },
        y: { beginAtZero: true },
      },
    },
  });
}

// Escalation triggers horizontal bar
function renderTriggersBar(triggers) {
  const TRIGGER_LABELS = {
    threshold:        'Threshold (>₹500)',
    critic_rejection: 'Critic Rejected',
    hard_trigger:     'Hard Trigger',
  };
  const TRIGGER_COLORS = {
    threshold:        CHART_COLORS.amber,
    critic_rejection: CHART_COLORS.red,
    hard_trigger:     CHART_COLORS.purple,
  };

  const labels = Object.keys(triggers).map(k => TRIGGER_LABELS[k] || k);
  const values = Object.values(triggers);
  const colors = Object.keys(triggers).map(k => (TRIGGER_COLORS[k] || CHART_COLORS.blue) + 'bb');

  mkChart('chart-triggers', {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Count',
        data: values,
        backgroundColor: colors,
        borderColor: colors.map(c => c.slice(0, -2)),
        borderWidth: 1.5,
        borderRadius: 4,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { beginAtZero: true, ticks: { precision: 0 } },
        y: { grid: { display: false } },
      },
    },
  });
}

// FR Coverage bars
function renderFRCoverage(frCoverage) {
  const container = document.getElementById('fr-coverage-row');
  if (!container) return;

  const FR_DESC = {
    FR1: 'Intent classification',
    FR2: 'Order lookup',
    FR3: 'Policy citation',
    FR4: 'Auto-resolve ≤₹500',
    FR5: 'Threshold gate',
    FR6: 'Safety critic',
    FR7: 'Policy trap → reject',
    FR8: 'Full observability',
  };

  const maxVal = Math.max(...Object.values(frCoverage), 1);

  container.innerHTML = Object.entries(frCoverage).map(([fr, count]) => {
    const pct = Math.round((count / maxVal) * 100);
    return `
      <div class="fr-bar" title="${FR_DESC[fr] || fr}">
        <div class="fr-bar-label">${fr}</div>
        <div class="fr-bar-track">
          <div class="fr-bar-fill" style="height:${pct}%"></div>
        </div>
        <div class="fr-bar-count">${count}</div>
      </div>`;
  }).join('');
}

// ── Ticket table ──────────────────────────────────────────────────────────

const STATUS_BADGE = {
  resolved:  '<span class="badge badge-green">✅ resolved</span>',
  escalated: '<span class="badge badge-amber">⚠️ escalated</span>',
  unknown:   '<span class="badge">— unknown</span>',
};

const TRIGGER_BADGE = {
  threshold:        '<span class="badge badge-amber">threshold</span>',
  critic_rejection: '<span class="badge badge-red">critic</span>',
  hard_trigger:     '<span class="badge badge-purple">hard-trigger</span>',
};

function renderTable(tickets) {
  const tbody = document.getElementById('ticket-tbody');
  if (!tickets.length) {
    tbody.innerHTML = '<tr><td colspan="9" class="table-loading">No tickets yet. Submit a ticket via the customer portal or run the demo CLI.</td></tr>';
    return;
  }
  tbody.innerHTML = tickets.map(t => `
    <tr>
      <td class="ticket-id-cell">${esc(t.ticket_id)}</td>
      <td>${STATUS_BADGE[t.status] || STATUS_BADGE.unknown}</td>
      <td><span class="badge badge-blue">#${esc(t.order_id || '—')}</span></td>
      <td>${t.claimed_amount != null ? '₹' + Number(t.claimed_amount).toFixed(0) : '—'}</td>
      <td>${t.escalation_trigger ? (TRIGGER_BADGE[t.escalation_trigger] || esc(t.escalation_trigger)) : '—'}</td>
      <td style="font-family:var(--mono)">${formatMs(t.total_latency_ms)}</td>
      <td style="font-family:var(--mono)">${t.total_cost_tokens.toLocaleString()}</td>
      <td>${formatDate(t.ts_created)}</td>
      <td><button class="trace-btn" onclick="openTrace('${esc(t.ticket_id)}')">Trace →</button></td>
    </tr>
  `).join('');
}

function filterTable() {
  const query   = document.getElementById('table-search').value.toLowerCase();
  const status  = document.getElementById('status-filter').value;
  const filtered = allTickets.filter(t => {
    const matchQ = !query || t.ticket_id.toLowerCase().includes(query) || (t.order_id || '').toLowerCase().includes(query);
    const matchS = !status || t.status === status;
    return matchQ && matchS;
  });
  renderTable(filtered);
}

function renderTableError(detail) {
  document.getElementById('ticket-tbody').innerHTML =
    `<tr><td colspan="9" class="table-loading">Error loading tickets: ${esc(String(detail))}</td></tr>`;
}

// ── Trace modal ───────────────────────────────────────────────────────────

const STEP_ICONS = {
  hard_trigger_check: '🔴', triage: '🔍', threshold_gate: '⚖️',
  refund_agent_order_lookup: '📦', refund_agent_policy_retrieval: '📋',
  refund_agent_llm: '🤖', safety_critic: '🛡️', orchestrator_verdict: '📊',
};

async function openTrace(ticketId) {
  const overlay = document.getElementById('modal-overlay');
  const title   = document.getElementById('modal-title');
  const subtitle= document.getElementById('modal-subtitle');
  const body    = document.getElementById('modal-body');

  title.textContent    = 'Ticket Trace';
  subtitle.textContent = ticketId;
  body.innerHTML       = '<div style="text-align:center;color:var(--text-3);padding:40px">Loading…</div>';
  overlay.classList.remove('hidden');

  try {
    const r = await fetch(`${API_BASE}/logs/${ticketId}`, { headers: adminHeaders() });
    if (!r.ok) { body.innerHTML = `<div style="color:var(--accent-red)">Error: ${r.status}</div>`; return; }
    const data = await r.json();
    const events = data.events || [];
    renderModalTrace(events, body, ticketId);
  } catch (err) {
    body.innerHTML = `<div style="color:var(--accent-red)">Failed: ${esc(err.message)}</div>`;
  }
}

function renderModalTrace(events, body, ticketId) {
  const totalLat = events.reduce((s, e) => s + (e.latency_ms || 0), 0);
  const totalTok = events.reduce((s, e) => s + (e.cost_tokens || 0), 0);
  const lastVerd = events.find(e => e.step === 'orchestrator_verdict');
  const verdict  = lastVerd?.decision || '';
  const isResolved = verdict.toUpperCase().includes('RESOLVED');

  const summaryBadge = isResolved
    ? '<span class="badge badge-green">✅ RESOLVED</span>'
    : '<span class="badge badge-amber">⚠️ ESCALATED</span>';

  body.innerHTML = `
    <div style="display:flex;gap:10px;align-items:center;margin-bottom:6px">
      ${summaryBadge}
      <span style="font-family:var(--mono);font-size:.75rem;color:var(--text-3)">
        ${events.length} steps · ${formatMs(totalLat)} · ${totalTok} tokens
      </span>
    </div>
    ${events.map(ev => `
      <div class="modal-step">
        <div class="modal-step-icon">${STEP_ICONS[ev.step] || '·'}</div>
        <div>
          <div class="modal-step-name">${esc(ev.step)}</div>
          <div class="modal-step-decision">${esc(ev.decision || '')}</div>
        </div>
        <div class="modal-step-meta">
          <div class="modal-step-lat">${formatMs(ev.latency_ms || 0)}</div>
          <div class="modal-step-tok">${ev.cost_tokens}tok</div>
        </div>
      </div>`).join('')}
  `;
}

function closeModal() {
  document.getElementById('modal-overlay').classList.add('hidden');
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeModal();
});

// ── Init ──────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  checkHealth();
  loadDashboard();
  setInterval(() => { checkHealth(); loadDashboard(); }, 30_000);
});
