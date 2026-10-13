/**
 * 轻量原生 WebSocket 工具
 * - 默认地址：ws(s)://host/scene/ws  （vite proxy 下为 /scene）
 * - 自动重连（指数退避，最大 30s）
 * - 心跳：30s ping/pong
 * - onMessage / onOpen / onClose 回调
 * - send 兼容后端无 error 后再成功
 */
export function createSceneSocket(opts = {}) {
  const {
    url = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/scene/ws',
    onMessage,
    onOpen,
    onClose,
    onError,
    heartbeatMs = 30000,
    maxBackoffMs = 30000,
  } = opts;

  let ws = null;
  let timer = null;
  let hbTimer = null;
  let backoff = 1000;
  let manuallyClosed = false;
  let listeners = { onMessage, onOpen, onClose, onError };

  function bind() {
    ws.onopen = () => {
      backoff = 1000;
      listeners.onOpen && listeners.onOpen();
      hbTimer = setInterval(() => {
        try { ws.readyState === 1 && ws.send(JSON.stringify({ type: 'ping', t: Date.now() })); }
        catch (e) { /* swallow */ }
      }, heartbeatMs);
    };
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        listeners.onMessage && listeners.onMessage(data);
      } catch {
        listeners.onMessage && listeners.onMessage(ev.data);
      }
    };
    ws.onerror = (e) => { listeners.onError && listeners.onError(e); };
    ws.onclose = () => {
      clearInterval(hbTimer); hbTimer = null;
      listeners.onClose && listeners.onClose();
      if (manuallyClosed) return;
      timer = setTimeout(bind, backoff);
      backoff = Math.min(backoff * 2, maxBackoffMs);
    };
  }

  function connect() {
    manuallyClosed = false;
    try {
      ws = new WebSocket(url);
      bind();
    } catch (e) {
      listeners.onError && listeners.onError(e);
      timer = setTimeout(connect, backoff);
      backoff = Math.min(backoff * 2, maxBackoffMs);
    }
  }

  function send(payload) {
    if (!ws || ws.readyState !== 1) return false;
    try {
      ws.send(typeof payload === 'string' ? payload : JSON.stringify(payload));
      return true;
    } catch { return false; }
  }

  function close() {
    manuallyClosed = true;
    clearTimeout(timer); clearInterval(hbTimer);
    if (ws) try { ws.close(); } catch {}
  }

  function updateListeners(next) { listeners = { ...listeners, ...next }; }

  connect();
  return {
    send,
    close,
    updateListeners,
    getReadyState: () => (ws ? ws.readyState : 3),
  };
}