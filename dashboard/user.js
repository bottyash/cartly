/* ──────────────────────────────────────────────────────────
   Cartly — Chat Engine + Shared Utilities (user.js)

   Exports to global scope (loaded before inline script):
     sendMessage()         — called by send button
     handleChatKey(event)  — called by textarea onkeydown
     addBubble(role, text, extraClass, trace) — shared by inline setupChat
     showToast(msg, type)  — shared toast notification
     esc(str)              — HTML escaping utility
────────────────────────────────────────────────────────── */
'use strict';

const API_BASE = 'http://localhost:8000';
let chatLocked   = false;
let bubbleCounter  = 0;
let typingCounter  = 0;
let _toastTimer;

/* ═══════════════════════════════════════════════════════════
   TOAST  (shared with inline script)
═══════════════════════════════════════════════════════════ */
function showToast(msg, type) {
  const t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg;
  t.className = `toast${type ? ' ' + type : ''}`;
  setTimeout(() => t.classList.add('show'), 10);
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => t.classList.remove('show'), 3400);
}

/* ═══════════════════════════════════════════════════════════
   HTML ESCAPE  (shared with inline script)
═══════════════════════════════════════════════════════════ */
function esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* ═══════════════════════════════════════════════════════════
   BUBBLE SYSTEM  (shared: setupChat in inline calls addBubble)
═══════════════════════════════════════════════════════════ */
function addBubble(role, text, extraClass, trace) {
  extraClass = extraClass || '';
  trace      = trace      || null;

  const container = document.getElementById('chat-messages');
  if (!container) {
    console.warn('[chat] chat-messages element not found');
    return '';
  }

  const id  = `bubble-${++bubbleCounter}`;
  const div = document.createElement('div');
  div.className = `chat-bubble bubble-${role}${extraClass ? ' ' + extraClass : ''}`;
  div.id = id;

  const now = new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
  const bodyHtml = renderMarkdown(text);

  let traceHtml = '';
  if (trace && trace.length > 0) {
    const traceId = `trace-${id}`;
    const ICONS = {
      hard_trigger_check: '🔴', triage: '🔍', threshold_gate: '⚖️',
      refund_agent_order_lookup: '📦', refund_agent_policy_retrieval: '📋',
      refund_agent_llm: '🤖', safety_critic: '🛡️', orchestrator_verdict: '📊',
      delivery_agent: '🚚', complaint_agent: '💬',
      product_agent_retrieval: '🛍️', product_agent_llm: '🤖',
    };
    const rows = trace.map(s =>
      `<div class="trace-row">
        <span class="tr-step">${ICONS[s.step] || '·'} ${esc(s.step)}</span>
        <span class="tr-dec" title="${esc(s.decision || '')}">${esc(s.decision || '')}</span>
        <span class="tr-lat">${(+s.latency_ms || 0).toFixed(0)}ms</span>
      </div>`
    ).join('');
    traceHtml = `
      <div class="trace-toggle" onclick="toggleTrace('${traceId}')">▸ View AI pipeline trace (${trace.length} steps)</div>
      <div class="trace-box hidden" id="${traceId}">${rows}</div>`;
  }

  div.innerHTML = `<div class="bubble-body">${bodyHtml}${traceHtml}</div><div class="bubble-time">${now}</div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return id;
}

function toggleTrace(id) {
  const el = document.getElementById(id);
  if (!el) return;
  const toggle = el.previousElementSibling;
  const hidden = el.classList.contains('hidden');
  el.classList.toggle('hidden');
  const n = el.querySelectorAll('.trace-row').length;
  toggle.textContent = hidden
    ? `▾ Hide AI pipeline trace (${n} steps)`
    : `▸ View AI pipeline trace (${n} steps)`;
}

function addTypingIndicator() {
  const id        = `typing-${++typingCounter}`;
  const container = document.getElementById('chat-messages');
  if (!container) return id;
  const div = document.createElement('div');
  div.className = 'chat-bubble bubble-bot';
  div.id = id;
  div.innerHTML = `<div class="bubble-body"><div class="typing-dots"><span></span><span></span><span></span></div></div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return id;
}

function removeTypingIndicator(id) {
  document.getElementById(id)?.remove();
}

/* ═══════════════════════════════════════════════════════════
   MARKDOWN RENDERER
═══════════════════════════════════════════════════════════ */
function renderMarkdown(text) {
  return esc(text)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code style="font-family:monospace;font-size:.82em;background:rgba(0,0,0,.06);padding:1px 5px;border-radius:3px">$1</code>')
    .replace(/\n/g, '<br>');
}

/* ═══════════════════════════════════════════════════════════
   CHAT INPUT HELPERS
═══════════════════════════════════════════════════════════ */
function handleChatKey(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
}

function resizeTextarea(el) {
  if (!el) return;
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

document.addEventListener('DOMContentLoaded', () => {
  const inp = document.getElementById('chat-inp');
  if (inp) inp.addEventListener('input', function () { resizeTextarea(this); });
});

/* ═══════════════════════════════════════════════════════════
   SEND MESSAGE  →  POST /tickets
═══════════════════════════════════════════════════════════ */
async function sendMessage() {
  if (chatLocked) return;

  const inputEl = document.getElementById('chat-inp');
  if (!inputEl) { console.error('[chat] #chat-inp not found'); return; }

  const text = (inputEl.value || '').trim();
  if (!text) return;

  // Show user bubble immediately
  addBubble('user', text);
  inputEl.value = '';
  resizeTextarea(inputEl);

  // Show typing indicator + lock UI
  const typingId = addTypingIndicator();
  chatLocked = true;
  const sendBtn = document.getElementById('send-btn');
  if (sendBtn) sendBtn.disabled = true;

  try {
    // Retrieve current order (set by setupChat via window._currentOrder)
    const order = window._currentOrder;
    if (!order) {
      removeTypingIndicator(typingId);
      addBubble('bot', '⚠️ No order selected. Please go back and choose an order first.');
      return;
    }

    const payload = {
      raw_ticket:     text,
      order_id:       String(order.order_id),
      buyer_id:       String(order.order_id),
      claimed_amount: parseFloat(order.order_amount) || 0,
      channel:        'web',
    };

    const r = await fetch(`${API_BASE}/tickets`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload),
    });

    removeTypingIndicator(typingId);

    if (!r.ok) {
      const errText = await r.text().catch(() => `HTTP ${r.status}`);
      let errMsg = errText;
      try { errMsg = JSON.parse(errText).detail || errText; } catch (_) {}
      addBubble('bot', `⚠️ Server error: ${errMsg}`);
      return;
    }

    const data = await r.json();
    renderResult(data);

  } catch (err) {
    removeTypingIndicator(typingId);
    console.error('[chat] sendMessage error:', err);
    addBubble('bot', `❌ Could not reach Cartly AI. Please check your connection and try again.\n\n_${err.message}_`);
  } finally {
    chatLocked = false;
    if (sendBtn) sendBtn.disabled = false;
    setTimeout(() => inputEl.focus(), 100);
  }
}

/* ═══════════════════════════════════════════════════════════
   RENDER API RESULT
═══════════════════════════════════════════════════════════ */
function renderResult(data) {
  if (!data) {
    addBubble('bot', '⚠️ Received an empty response. Please try again.');
    return;
  }

  if (data.status === 'resolved') {
    const r = data.resolution || {};
    const fa      = (r.faithfulness_score != null)
      ? ` · Faithfulness: ${Number(r.faithfulness_score).toFixed(2)}`
      : '';
    const refs    = (r.source_refs || []).join(', ');
    const action  = (r.action_taken || 'processed').replace(/_/g, ' ');
    const msg = [
      `✅ **Your request has been ${action}.**`,
      '',
      r.reason || '',
      '',
      `📋 Policy refs: ${refs || 'N/A'}`,
      r.transaction_ref ? `🔖 Ref: \`${r.transaction_ref}\`` : '',
      fa,
    ].filter(Boolean).join('\n');
    addBubble('bot', msg, 'bubble-resolved', data.trace);

  } else {
    const hb = data.handoff_brief || {};
    const TRIGGER_MSG = {
      threshold:        '⚖️ Your claimed amount exceeds our automated limit. A human agent will review this shortly.',
      critic_rejection: '🛡️ Our safety review flagged this decision for manual verification.',
      hard_trigger:     '🚨 Your message has been escalated for priority review.',
    };
    const triggerMsg = TRIGGER_MSG[hb.escalation_trigger] || 'Your request has been escalated for human review.';
    const msg = [
      '⚠️ **This ticket needs human review.**',
      '',
      triggerMsg,
      '',
      hb.reason || '',
      '',
      '_Our team will contact you within 24 hours._',
    ].filter(s => s !== undefined).join('\n');
    addBubble('bot', msg, 'bubble-escalated', data.trace);
  }
}
