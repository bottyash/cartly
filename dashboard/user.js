/* ──────────────────────────────────────────────────────────
   Cartly — Chat Engine (user.js)
   Handles: sendMessage → ticket API → render result
   All view/auth/nav logic lives in user.html inline script.
────────────────────────────────────────────────────────── */
'use strict';

const API_BASE = 'http://localhost:8000';
let chatLocked = false;
let bubbleCounter = 0;
let typingIdCounter = 0;

// ── Input helpers ──────────────────────────────────────────

function handleChatKey(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
}

function resizeTextarea(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

document.addEventListener('DOMContentLoaded', () => {
  const inp = document.getElementById('chat-inp');
  if (inp) inp.addEventListener('input', function () { resizeTextarea(this); });
});

// ── Send message → API ─────────────────────────────────────

async function sendMessage() {
  if (chatLocked) return;
  const inputEl = document.getElementById('chat-inp');
  const text = inputEl?.value.trim();
  if (!text) return;

  addBubble('user', text);
  inputEl.value = '';
  resizeTextarea(inputEl);

  const typingId = addTypingIndicator();
  chatLocked = true;
  const sendBtn = document.getElementById('send-btn');
  if (sendBtn) sendBtn.disabled = true;

  try {
    const order = window._currentOrder;
    if (!order) { removeTypingIndicator(typingId); addBubble('bot', '⚠️ No order loaded. Please go back and select an order.'); return; }

    const payload = {
      raw_ticket:     text,
      order_id:       order.order_id,
      buyer_id:       order.order_id,
      claimed_amount: parseFloat(order.order_amount || 0),
      channel:        'web',
    };

    const r = await fetch(`${API_BASE}/tickets`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(payload),
    });

    removeTypingIndicator(typingId);

    if (!r.ok) {
      const err = await r.text();
      addBubble('bot', `⚠️ Something went wrong: ${err}`);
      return;
    }

    renderResult(await r.json());
  } catch (err) {
    removeTypingIndicator(typingId);
    addBubble('bot', `❌ Cannot reach the API. Make sure the server is running.\n\n${err.message}`);
  } finally {
    chatLocked = false;
    if (sendBtn) sendBtn.disabled = false;
    setTimeout(() => inputEl?.focus(), 100);
  }
}

// ── Render API response ────────────────────────────────────

function renderResult(data) {
  if (data.status === 'resolved') {
    const r = data.resolution;
    const fa = r.faithfulness_score != null ? ` · Faithfulness: ${r.faithfulness_score.toFixed(2)}` : '';
    const refs = (r.source_refs || []).join(', ');
    const actionLabel = (r.action_taken || '').replace(/_/g, ' ');
    const msg = `✅ **Your request has been ${actionLabel}.**\n\n${r.reason}\n\n📋 Policy refs: ${refs || 'N/A'}${r.transaction_ref ? `\n🔖 Ref: \`${r.transaction_ref}\`` : ''}${fa}`;
    addBubble('bot', msg, 'bubble-resolved', data.trace);
  } else {
    const hb = data.handoff_brief || {};
    const triggerMsg = ({
      threshold:        `⚖️ Your claimed amount exceeds our automated limit. A human agent will review this shortly.`,
      critic_rejection: `🛡️ Our safety review flagged this decision for manual verification.`,
      hard_trigger:     `🚨 Your message has been escalated for priority review.`,
    })[hb.escalation_trigger] || `Your request has been escalated for human review.`;
    const msg = `⚠️ **This ticket needs human review.**\n\n${triggerMsg}\n\n${hb.reason || ''}\n\n_Our team will contact you within 24 hours._`;
    addBubble('bot', msg, 'bubble-escalated', data.trace);
  }
}

// ── Bubble system ──────────────────────────────────────────

function addBubble(role, text, extraClass = '', trace = null) {
  const container = document.getElementById('chat-messages');
  if (!container) return;
  const id = `bubble-${++bubbleCounter}`;
  const div = document.createElement('div');
  // role: 'user' | 'bot'
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
      delivery_agent: '🚚', complaint_agent: '💬', product_agent_retrieval: '🛍️',
      product_agent_llm: '🤖',
    };
    const stepsHtml = trace.map(s => `
      <div class="trace-row">
        <span class="tr-step">${ICONS[s.step] || '·'} ${s.step}</span>
        <span class="tr-dec" title="${esc(s.decision || '')}">${esc(s.decision || '')}</span>
        <span class="tr-lat">${s.latency_ms.toFixed(0)}ms</span>
      </div>`).join('');
    traceHtml = `
      <div class="trace-toggle" onclick="toggleTrace('${traceId}')">▸ View AI pipeline trace (${trace.length} steps)</div>
      <div class="trace-box hidden" id="${traceId}">${stepsHtml}</div>`;
  }

  div.innerHTML = `
    <div class="bubble-body">${bodyHtml}${traceHtml}</div>
    <div class="bubble-time">${now}</div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return id;
}

function toggleTrace(id) {
  const el = document.getElementById(id);
  const toggle = el.previousElementSibling;
  const hidden = el.classList.contains('hidden');
  el.classList.toggle('hidden');
  const n = el.querySelectorAll('.trace-row').length;
  toggle.textContent = hidden
    ? `▾ Hide AI pipeline trace (${n} steps)`
    : `▸ View AI pipeline trace (${n} steps)`;
}

function addTypingIndicator() {
  const id = `typing-${++typingIdCounter}`;
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

// ── Markdown renderer ──────────────────────────────────────

function renderMarkdown(text) {
  return esc(text)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code style="font-family:monospace;font-size:.8em;background:rgba(0,0,0,.06);padding:1px 5px;border-radius:3px">$1</code>')
    .replace(/\n/g, '<br>');
}

function esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
