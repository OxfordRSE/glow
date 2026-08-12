// Pings the server every few seconds so it can tell "tab/window closed" from
// "user is just reading this page" — see routes/heartbeat.py and main.py's
// watcher thread, which quits the process once pings stop arriving.
const PING_INTERVAL_MS = 3000;

function ping(): void {
  void fetch("/heartbeat", { method: "POST", keepalive: true }).catch(() => {});
}

export function init(): void {
  ping();
  window.setInterval(ping, PING_INTERVAL_MS);
}

if (!(globalThis as { __TEST__?: boolean }).__TEST__) init();
