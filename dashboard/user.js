/* ──────────────────────────────────────────────────────────────
   Cartly — User Chat Interface (user.js)
   Handles: order lookup → chat flow → ticket submission → result
────────────────────────────────────────────────────────────── */
'use strict';

const API_BASE = 'http://localhost:8000';

let currentOrder = null;
let chatLocked   = false;

// ── Step 1: Order Lookup ──────────────────────────────────────────────────

function fillAndLookup(orderId) {
  document.getElementById('lookup-input').value = orderId;
  lookupOrder();
}

async function lookupOrder() {
  const input = document.getElementById('lookup-input');
  const btn   = document.getElementById('lookup-btn');
  const txtEl = document.getElementById('lookup-text');
  const spn   = document.getElementById('lookup-spinner');
  const errEl = document.getElementById('lookup-error');
  const orderId = input.value.trim();

  if (!orderId) return;

  btn.disabled = true;
  txtEl.classList.add('hidden');
  spn.classList.remove('hidden');
  errEl.classList.add('hidden');

  try {
    const r = await fetch(`${API_BASE}/orders/${encodeURIComponent(orderId)}`);
    if (!r.ok) {
      const data = await r.json().catch(() => ({}));
      errEl.textContent = data.detail || `Order '${orderId}' not found. Try: 1042, 1077, 1090, 1099`;
      errEl.classList.remove('hidden');
      return;
    }
    currentOrder = await r.json();
    enterChatMode();
  } catch (err) {
    errEl.textContent = `Cannot reach API. Make sure docker compose is running.`;
    errEl.classList.remove('hidden');
  } finally {
    btn.disabled = false;
    txtEl.classList.remove('hidden');
    spn.classList.add('hidden');
  }
}

// ── Step 2: Enter Chat Mode ───────────────────────────────────────────────

function enterChatMode() {
  document.getElementById('screen-lookup').classList.add('hidden');
  const screen = document.getElementById('screen-chat');
  screen.classList.remove('hidden');

  // Order badge in header
  const badge = document.getElementById('order-badge');
  badge.textContent = `Order #${currentOrder.order_id}`;
  badge.classList.remove('hidden');

  // Render order card
  renderOrderCard(currentOrder);

  // First system greeting
  const buyer = currentOrder.buyer_name || 'there';
  const product = currentOrder.product_name || 'your item';
  const amount  = currentOrder.order_amount ? `₹${currentOrder.order_amount.toFixed(0)}` : '';
  addBubble('system', `Hi ${buyer.split(' ')[0]}! 👋 I found your order for **${product}** (${amount}). I'm Cartly's AI refund agent.\n\nHow can I help you today? Describe your issue and I'll resolve it right away.`);

  setTimeout(() => document.getElementById('chat-input').focus(), 300);
}

function renderOrderCard(order) {
  const card = document.getElementById('order-card');
  const isDelivered = order.delivery_status === 'delivered';
  const pillCls = isDelivered ? 'pill pill-g' : 'pill pill-a';
  card.innerHTML = `
    <div class="order-pname">${esc(order.product_name)}</div>
    <div class="order-row"><span class="order-key">Order ID</span><span class="order-val">#${esc(order.order_id)}</span></div>
    <div class="order-row"><span class="order-key">Category</span><span class="order-val">${esc(order.product_category)}</span></div>
    <div class="order-row"><span class="order-key">Status</span><span class="${pillCls}"><span class="pdot"></span>${esc(order.delivery_status)}</span></div>
    ${order.courier ? `<div class="order-row"><span class="order-key">Courier</span><span class="order-val">${esc(order.courier)}</span></div>` : ''}
    <div class="order-row" style="padding-top:14px;border:none"><span class="order-key">Order Value</span><span class="order-amt">₹${Number(order.order_amount).toFixed(2)}</span></div>
  `;
}


// ── Step 3: Chat ──────────────────────────────────────────────────────────

function handleChatKey(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
}

async function sendMessage() {
  if (chatLocked) return;
  const inputEl = document.getElementById('chat-input');
  const text    = inputEl.value.trim();
  if (!text) return;

  // Render user bubble
  addBubble('user', text);
  inputEl.value = '';
  resizeTextarea(inputEl);

  // Show typing indicator
  const typingId = addTypingIndicator();
  chatLocked = true;
  document.getElementById('chat-send-btn').disabled = true;

  try {
    const amount = currentOrder.order_amount || 0;
    const payload = {
      raw_ticket:     text,
      order_id:       currentOrder.order_id,
      buyer_id:       currentOrder.order_id,
      claimed_amount: parseFloat(amount),
      channel:        'web',
    };

    const r = await fetch(`${API_BASE}/tickets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    removeTypingIndicator(typingId);

    if (!r.ok) {
      const err = await r.text();
      addBubble('system', `⚠️ Something went wrong: ${err}`);
      return;
    }

    const data = await r.json();
    renderResult(data);
  } catch (err) {
    removeTypingIndicator(typingId);
    addBubble('system', `❌ Cannot reach the API. Check that docker compose is running.\n\n${err.message}`);
  } finally {
    chatLocked = false;
    document.getElementById('chat-send-btn').disabled = false;
    setTimeout(() => document.getElementById('chat-input').focus(), 100);
  }
}

// ── Step 4: Render result ─────────────────────────────────────────────────

function renderResult(data) {
  if (data.status === 'resolved') {
    const r = data.resolution;
    const fa = r.faithfulness_score != null ? ` · Faithfulness: ${r.faithfulness_score.toFixed(2)}` : '';
    const refs = (r.source_refs || []).join(', ');
    const msg  = `✅ **Good news!** Your request has been **${r.action_taken.replace('_', ' ')}**.\n\n${r.reason}\n\n📋 Policy refs: ${refs || 'N/A'}${r.transaction_ref ? `\n🔖 Ref: \`${r.transaction_ref}\`` : ''}${fa}`;
    addBubble('system', msg, 'resolved', data.trace);
  } else {
    const hb = data.handoff_brief;
    const triggerMsg = {
      threshold:        `⚖️ Your claimed amount exceeds our automated refund limit. A human agent will review this.`,
      critic_rejection: `🛡️ Our safety review found an issue with this decision. A human agent will verify.`,
      hard_trigger:     `🚨 Your message has been flagged for priority human review.`,
    }[hb.escalation_trigger] || `Your ticket has been escalated for human review.`;
    const msg = `⚠️ **This ticket needs human review.**\n\n${triggerMsg}\n\n${hb.reason}\n\n_Our team will contact you within 24 hours._`;
    addBubble('system', msg, 'escalated', data.trace);
  }
}

// ── Bubble helpers ────────────────────────────────────────────────────────

let bubbleCounter = 0;

function addBubble(role, text, variant = '', trace = null) {
  const container = document.getElementById('chat-messages');
  const id = `bubble-${++bubbleCounter}`;
  const div = document.createElement('div');
  div.className = `chat-bubble bubble-${role}${variant ? ` bubble-${variant}` : ''}`;
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
    };
    const stepsHtml = trace.map(s => `
      <div class="trace-row">
        <span class="tr-step">${ICONS[s.step] || '·'} ${s.step}</span>
        <span class="tr-dec" title="${esc(s.decision || '')}">${esc(s.decision || '')}</span>
        <span class="tr-lat">${s.latency_ms.toFixed(0)}ms</span>
      </div>`).join('');
    traceHtml = `
      <div class="trace-toggle" onclick="toggleTrace('${traceId}')">
        ▸ View pipeline trace (${trace.length} steps)
      </div>
      <div class="trace-box hidden" id="${traceId}">${stepsHtml}</div>`;
  }

  div.innerHTML = `
    <div class="bubble-body">${bodyHtml}${traceHtml}</div>
    <div class="bubble-time">${now}</div>
  `;
  container.appendChild(div);
  div.scrollIntoView({ behavior: 'smooth', block: 'end' });
  return id;
}

function toggleTrace(id) {
  const el = document.getElementById(id);
  const toggle = el.previousElementSibling;
  const hidden = el.classList.contains('hidden');
  el.classList.toggle('hidden');
  const n = el.querySelectorAll('.trace-row').length;
  toggle.textContent = hidden ? `▾ Hide pipeline trace (${n} steps)` : `▸ View pipeline trace (${n} steps)`;
}

let typingIdCounter = 0;

function addTypingIndicator() {
  const id = `typing-${++typingIdCounter}`;
  const container = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = 'chat-bubble bubble-system typing-bubble';
  div.id = id;
  div.innerHTML = `<div class="bubble-body"><div class="typing-dots"><span></span><span></span><span></span></div></div>`;
  container.appendChild(div);
  div.scrollIntoView({ behavior: 'smooth', block: 'end' });
  return id;
}

function removeTypingIndicator(id) {
  document.getElementById(id)?.remove();
}

// ── Markdown renderer (simple) ────────────────────────────────────────────

function renderMarkdown(text) {
  return esc(text)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code style="font-family:var(--mono);font-size:.8em;background:rgba(255,255,255,.08);padding:1px 4px;border-radius:3px">$1</code>')
    .replace(/\n/g, '<br>');
}

function esc(str) {
  return String(str ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function resizeTextarea(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

// ── Init ──────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('chat-input')?.addEventListener('input', function() { resizeTextarea(this); });
});
