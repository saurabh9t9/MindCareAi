(() => {
  const toggle = document.getElementById('chat-toggle');
  const close = document.getElementById('chat-close');
  const panel = document.getElementById('chat-panel');
  const form = document.getElementById('chat-form');
  const input = document.getElementById('chat-input');
  const log = document.getElementById('chat-log');
  const status = document.getElementById('chat-status');
  if (!toggle || !close || !panel || !form || !input || !log || !status) return;

  let userId = localStorage.getItem('mannmitra-user-id');
  if (!userId) {
    userId = window.crypto && typeof window.crypto.randomUUID === 'function'
      ? window.crypto.randomUUID()
      : `${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
    localStorage.setItem('mannmitra-user-id', userId);
  }

  let started = false;
  let busy = false;
  const outgoing = [];

  function addMessage(kind, text) {
    const bubble = document.createElement('p');
    bubble.className = `chat-message ${kind}`;
    bubble.textContent = text;
    log.appendChild(bubble);
    log.scrollTop = log.scrollHeight;
  }

  function setOpen(open) {
    panel.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    if (open) {
      input.focus();
      if (!started) {
        started = true;
        sendMessage('/start');
      }
    } else {
      toggle.focus();
    }
  }

  function sendMessage(message) {
    if (outgoing.length >= 8) {
      addMessage('assistant', 'Please wait for a reply before sending more messages.');
      return;
    }
    outgoing.push(message);
    if (message !== '/start') addMessage('user', message);
    processQueue();
  }

  async function processQueue() {
    if (busy) return;
    busy = true;
    form.querySelector('button[type="submit"]').disabled = true;
    while (outgoing.length) {
      const message = outgoing.shift();
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), 35000);
      status.textContent = outgoing.length ? 'Sending queued messages…' : 'MannMitra is replying…';
      try {
        const response = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: userId, message }),
          signal: controller.signal
        });
        const result = await response.json();
        if (!response.ok) {
          throw new Error(result.error || 'The message could not be sent.');
        }
        addMessage('assistant', result.reply);
      } catch (error) {
        const messageText = error.name === 'AbortError'
          ? 'That reply took too long. Please try again, or use the offline demo mode.'
          : (error.message || 'Unable to connect right now. Please try again.');
        addMessage('assistant', messageText);
      } finally {
        window.clearTimeout(timeout);
      }
    }
    busy = false;
    status.textContent = '';
    form.querySelector('button[type="submit"]').disabled = false;
    if (!panel.hidden) input.focus();
  }

  toggle.addEventListener('click', () => setOpen(panel.hidden));
  close.addEventListener('click', () => setOpen(false));
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const message = input.value.trim();
    if (!message) return;
    input.value = '';
    sendMessage(message);
  });
  document.querySelectorAll('[data-chat-command]').forEach((button) => {
    button.addEventListener('click', () => sendMessage(button.dataset.chatCommand));
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !panel.hidden) setOpen(false);
  });
})();
