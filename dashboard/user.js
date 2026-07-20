/* ──────────────────────────────────────────────────────────
   Cartly — Chat Engine + Shared Utilities (user.js)
   Exports to global scope (loaded before inline script):
     sendMessage, handleChatKey, addBubble, showToast, esc
────────────────────────────────────────────────────────── */
'use strict';

const API_BASE = 'http://localhost:8000';
let chatLocked    = false;
let bubbleCounter = 0;
let typingCounter = 0;
let _toastTimer;

// ── Live chat state ────────────────────────────────────────
let _liveTicketId   = null;   // current live ticket ID
let _livePolling    = null;   // setInterval handle
let _lastMsgCount   = 0;      // deduplicate poll results

/* ═══ TOAST ═══════════════════════════════════════════════ */
function showToast(msg, type) {
  const t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg;
  t.className = `toast${type ? ' ' + type : ''}`;
  setTimeout(() => t.classList.add('show'), 10);
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => t.classList.remove('show'), 3400);
}

/* ═══ HTML ESCAPE ══════════════════════════════════════════ */
function esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/* ═══ MARKDOWN RENDERER ════════════════════════════════════ */
function renderMarkdown(text) {
  return esc(text)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g,
      '<code style="font-family:monospace;font-size:.82em;background:rgba(0,0,0,.06);padding:1px 5px;border-radius:3px">$1</code>')
    .replace(/\n/g, '<br>');
}

/* ═══ BUBBLE SYSTEM ════════════════════════════════════════ */
function addBubble(role, text, extraClass, _trace) {
  extraClass = extraClass || '';
  const container = document.getElementById('chat-messages');
  if (!container) return '';
  const id  = `bubble-${++bubbleCounter}`;
  const div = document.createElement('div');
  div.className = `chat-bubble bubble-${role}${extraClass ? ' ' + extraClass : ''}`;
  div.id = id;
  const now = new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
  div.innerHTML = `<div class="bubble-body">${renderMarkdown(text)}</div><div class="bubble-time">${now}</div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return id;
}

function addTypingIndicator() {
  const id = `typing-${++typingCounter}`;
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
function removeTypingIndicator(id) { document.getElementById(id)?.remove(); }

/* ═══ KEYBOARD / RESIZE ════════════════════════════════════ */
function handleChatKey(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
}
function handleLiveChatKey(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendLiveMessage();
  }
}
function resizeTextarea(el) {
  if (!el) return;
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('chat-inp')?.addEventListener('input', function () { resizeTextarea(this); });
  document.getElementById('live-inp')?.addEventListener('input', function () { resizeTextarea(this); });
});

/* ═══ AI CHAT — SEND MESSAGE ═══════════════════════════════ */
async function sendMessage() {
  if (chatLocked) return;
  const inputEl = document.getElementById('chat-inp');
  if (!inputEl) return;
  const text = (inputEl.value || '').trim();
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
    if (!order) {
      removeTypingIndicator(typingId);
      addBubble('bot', '⚠️ No order selected. Please go back and choose an order first.');
      return;
    }
    const r = await fetch(`${API_BASE}/tickets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        raw_ticket:     text,
        order_id:       String(order.order_id),
        buyer_id:       String(order.order_id),
        claimed_amount: parseFloat(order.order_amount) || 0,
        channel:        'web',
      }),
    });
    removeTypingIndicator(typingId);
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      addBubble('bot', `⚠️ ${e.detail || 'Something went wrong. Please try again.'}`);
      return;
    }
    renderResult(await r.json());
  } catch (err) {
    removeTypingIndicator(typingId);
    addBubble('bot', `❌ Could not reach Cartly AI. Please check your connection.\n\n_${err.message}_`);
  } finally {
    chatLocked = false;
    if (sendBtn) sendBtn.disabled = false;
    setTimeout(() => inputEl.focus(), 100);
  }
}

/* ═══ AI CHAT — RENDER RESULT (USER-FRIENDLY, NO TECH DETAILS) */
function renderResult(data) {
  if (!data) { addBubble('bot', '⚠️ Empty response. Please try again.'); return; }

  if (data.status === 'resolved') {
    const r      = data.resolution || {};
    const action = (r.action_taken || 'processed').replace(/_/g, ' ');
    // Simple, clean message — no policy refs, no faithfulness scores, no transaction IDs
    const msg = `✅ **Great news!** ${r.reason || `Your request has been ${action}.`}`;
    addBubble('bot', msg, 'bubble-resolved');
  } else {
    // Escalation: don't show technical details — show human connect CTA instead
    showConnectHumanCTA(data);
  }
}

/* ═══ CONNECT TO HUMAN — CTA BUBBLE ═══════════════════════ */
function showConnectHumanCTA(data) {
  const order = window._currentOrder || {};
  const hb    = data?.handoff_brief || {};

  // User-friendly reason (not the raw escalation_trigger)
  const reasonMap = {
    threshold:        "Our AI couldn't auto-approve this — a human agent can help.",
    critic_rejection: "This needs a bit more attention from our team.",
    hard_trigger:     "We've flagged this for priority review.",
  };
  const reason = reasonMap[hb.escalation_trigger] || "Our AI wants to connect you with a human agent for the best resolution.";

  const container = document.getElementById('chat-messages');
  if (!container) return;

  const id  = `bubble-${++bubbleCounter}`;
  const div = document.createElement('div');
  div.className = 'chat-bubble bubble-bot bubble-human-cta';
  div.id = id;
  const now = new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
  div.innerHTML = `
    <div class="bubble-body">
      <div class="hcta-icon">👤</div>
      <div class="hcta-title">Connect with a Human Agent</div>
      <div class="hcta-reason">${esc(reason)}</div>
      <button class="hcta-btn" onclick="connectToHuman('${esc(hb.escalation_trigger||'')}')">
        Connect to Human Support →
      </button>
    </div>
    <div class="bubble-time">${now}</div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;

  // Also lock the AI input and show the CTA hint
  const inputArea = document.getElementById('chat-inp-area');
  if (inputArea) {
    inputArea.innerHTML = `
      <div class="chat-locked-bar">
        <span>💬</span>
        <span>Connect to a human agent to continue this conversation</span>
        <button onclick="connectToHuman('${esc(hb.escalation_trigger||'')}')" class="chat-locked-btn">Connect Now</button>
      </div>`;
  }
}

/* ═══ CONNECT TO HUMAN — CREATE LIVE TICKET ═══════════════ */
async function connectToHuman(trigger) {
  const order = window._currentOrder;
  if (!order) return;
  const user  = window._cartlyUser || {};
  const name  = user.name || order.buyer_name || 'Customer';

  // Disable button to prevent double-click
  document.querySelectorAll('.hcta-btn,.chat-locked-btn').forEach(b => {
    b.disabled = true; b.textContent = 'Connecting…';
  });

  try {
    const r = await fetch(`${API_BASE}/live/connect`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        order_id:      String(order.order_id),
        buyer_name:    name,
        product_name:  order.product_name || '',
        issue_summary: `Escalated (${trigger || 'user request'}) — Order #${order.order_id}: ${order.product_name}`,
      }),
    });
    if (!r.ok) throw new Error('Failed to connect');
    const ticket = await r.json();
    _liveTicketId  = ticket.id;
    _lastMsgCount  = 0;

    // Switch to live chat view
    if (typeof switchView === 'function') switchView('live-chat');
    initLiveChatView(ticket);
  } catch (err) {
    showToast('Could not connect. Please try again.', 'err');
    document.querySelectorAll('.hcta-btn,.chat-locked-btn').forEach(b => {
      b.disabled = false; b.textContent = 'Connect to Human Support →';
    });
  }
}

/* ═══ LIVE CHAT — INIT VIEW ════════════════════════════════ */
function initLiveChatView(ticket) {
  const msgs = document.getElementById('live-messages');
  if (msgs) msgs.innerHTML = '';
  _lastMsgCount = 0;

  // Update ticket info sidebar
  const infoEl = document.getElementById('live-ticket-info');
  if (infoEl && window._currentOrder) {
    const o = window._currentOrder;
    infoEl.innerHTML = `
      <div class="live-info-row"><span>Order</span><strong>#${esc(String(o.order_id))}</strong></div>
      <div class="live-info-row"><span>Product</span><strong>${esc(o.product_name)}</strong></div>
      <div class="live-info-row"><span>Amount</span><strong>₹${Number(o.order_amount).toLocaleString('en-IN')}</strong></div>`;
  }

  // Show waiting state
  showLiveStatus('waiting');

  // Start polling
  clearInterval(_livePolling);
  _livePolling = setInterval(pollLiveChat, 2000);
}

function showLiveStatus(status) {
  const statusEl = document.getElementById('live-agent-status');
  const waitEl   = document.getElementById('live-waiting-banner');
  if (statusEl) {
    if (status === 'waiting') {
      statusEl.textContent = '⏳ Waiting for an agent…';
      statusEl.style.color = 'var(--orange)';
    } else if (status === 'active') {
      statusEl.textContent = '🟢 Agent online';
      statusEl.style.color = 'var(--green)';
    } else {
      statusEl.textContent = '✅ Resolved';
      statusEl.style.color = 'var(--gray-400)';
    }
  }
  if (waitEl) {
    waitEl.classList.toggle('hidden', status !== 'waiting');
  }
  // Enable/disable input
  const liveInp = document.getElementById('live-inp');
  const liveSend = document.getElementById('live-send-btn');
  if (liveInp)  liveInp.disabled  = (status === 'resolved');
  if (liveSend) liveSend.disabled = (status === 'resolved');
}

/* ═══ LIVE CHAT — POLL ══════════════════════════════════════ */
async function pollLiveChat() {
  if (!_liveTicketId) return;
  try {
    const r = await fetch(`${API_BASE}/live/${_liveTicketId}`);
    if (!r.ok) return;
    const ticket = await r.json();

    // Update status indicator
    showLiveStatus(ticket.status);

    // Render any new messages
    const msgs = ticket.messages || [];
    if (msgs.length > _lastMsgCount) {
      const newMsgs = msgs.slice(_lastMsgCount);
      newMsgs.forEach(m => renderLiveMessage(m));
      _lastMsgCount = msgs.length;
    }

    // Stop polling when resolved
    if (ticket.status === 'resolved') {
      clearInterval(_livePolling);
      addLiveBubble('system', '✅ This conversation has been resolved by the support agent. Thank you for contacting Cartly!');
    }
  } catch (_) { /* silently ignore poll errors */ }
}

function renderLiveMessage(msg) {
  // Don't re-render messages we already showed
  addLiveBubble(msg.sender, msg.message, msg.sender_name);
}

function addLiveBubble(role, text, senderName) {
  const container = document.getElementById('live-messages');
  if (!container) return;
  const div = document.createElement('div');
  div.className = `chat-bubble bubble-${role === 'admin' ? 'bot' : (role === 'user' ? 'user' : 'bot')}`;
  const now  = new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
  const name = (role === 'admin') ? `<div class="bubble-sender">Support Agent</div>` :
               (role === 'system') ? '' :
               (senderName ? `<div class="bubble-sender">${esc(senderName)}</div>` : '');
  div.innerHTML = `<div class="bubble-body">${name}${renderMarkdown(text)}</div><div class="bubble-time">${now}</div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

/* ═══ LIVE CHAT — SEND (USER SIDE) ════════════════════════ */
async function sendLiveMessage() {
  if (!_liveTicketId) return;
  const inputEl = document.getElementById('live-inp');
  if (!inputEl) return;
  const text = (inputEl.value || '').trim();
  if (!text) return;

  const user = window._cartlyUser || {};
  const name = user.name || window._currentOrder?.buyer_name || 'Customer';

  // Optimistic render
  addLiveBubble('user', text, name);
  inputEl.value = '';
  resizeTextarea(inputEl);
  _lastMsgCount++;   // prevent poll from re-rendering

  const sendBtn = document.getElementById('live-send-btn');
  if (sendBtn) sendBtn.disabled = true;
  try {
    await fetch(`${API_BASE}/live/${_liveTicketId}/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sender: 'user', sender_name: name, message: text }),
    });
  } catch { showToast('Message failed to send. Please try again.', 'err'); }
  finally {
    if (sendBtn) sendBtn.disabled = false;
    setTimeout(() => inputEl.focus(), 80);
  }
}

/* ═══ CLEANUP ═══════════════════════════════════════════════ */
function stopLivePolling() {
  clearInterval(_livePolling);
  _livePolling  = null;
  _liveTicketId = null;
}
