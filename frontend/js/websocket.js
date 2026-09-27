/**
 * DINESYNC Real-Time WebSocket Client
 */
class LiveWebSocketClient {
  constructor() {
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectDelay = 5000;
    this.listeners = new Map();
    this.isConnected = false;
  }

  connect() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host || 'localhost:8000';
    const wsUrl = `${protocol}//${host}/ws`;

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        this.isConnected = true;
        this.reconnectAttempts = 0;
        this.updateConnectionBadge(true);
        console.log('[DINESYNC WS] Connected to real-time telemetry stream');
      };

      this.ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          this.handleIncomingMessage(payload);
        } catch (e) {
          console.error('[DINESYNC WS] Message parse error:', e);
        }
      };

      this.ws.onclose = () => {
        this.isConnected = false;
        this.updateConnectionBadge(false);
        this.scheduleReconnect();
      };

      this.ws.onerror = (err) => {
        console.warn('[DINESYNC WS] Connection error:', err);
        this.ws.close();
      };

    } catch (e) {
      console.error('[DINESYNC WS] Failed to establish connection:', e);
      this.scheduleReconnect();
    }
  }

  scheduleReconnect() {
    const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), this.maxReconnectDelay);
    this.reconnectAttempts++;
    setTimeout(() => {
      console.log(`[DINESYNC WS] Attempting reconnect #${this.reconnectAttempts}...`);
      this.connect();
    }, delay);
  }

  handleIncomingMessage(payload) {
    const { type, data, event } = payload;
    
    // Dispatch native DOM event
    window.dispatchEvent(new CustomEvent(`dinesync:${type.toLowerCase()}`, {
      detail: { data, event }
    }));

    if (this.listeners.has(type)) {
      this.listeners.get(type).forEach(cb => cb(data, event));
    }
  }

  on(type, callback) {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, []);
    }
    this.listeners.get(type).push(callback);
  }

  updateConnectionBadge(connected) {
    const badge = document.getElementById('ws-status-indicator');
    const text = document.getElementById('ws-status-text');
    if (badge && text) {
      if (connected) {
        badge.className = 'w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse';
        text.innerText = 'Live IoT Connected';
        text.className = 'text-xs text-emerald-400 font-medium';
      } else {
        badge.className = 'w-2.5 h-2.5 rounded-full bg-amber-400';
        text.innerText = 'Reconnecting...';
        text.className = 'text-xs text-amber-400 font-medium';
      }
    }
  }
}

window.dinesyncWS = new LiveWebSocketClient();
