"""
Phone / browser monitor.

Serves the queue and the live log over plain HTTP, so the suite can be
checked from a phone on the same Tailscale network without installing
anything there. No login: Tailscale is the access control. This must never
be bound to anything but a Tailscale or local interface.
"""
import json
import logging
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

log = logging.getLogger("web_monitor")

PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ram Racing CFD</title>
<style>
  body { background:#21252b; color:#abb2bf; font-family:-apple-system,"Segoe UI",sans-serif;
         margin:0; padding:14px; }
  h1 { font-size:15px; color:#dcdfe4; margin:0 0 10px; text-transform:uppercase;
       letter-spacing:1px; color:#3d9960; }
  .job { background:#282c34; border:1px solid #3e4451; border-radius:6px;
         padding:10px 12px; margin-bottom:8px; }
  .top { display:flex; justify-content:space-between; font-weight:600; color:#dcdfe4; }
  .bar { background:#2c313a; border-radius:4px; height:9px; margin-top:7px; overflow:hidden; }
  .bar > div { background:#3d9960; height:100%; transition:width .3s; }
  .msg { color:#7f8593; font-size:12px; margin-top:4px; }
  .Pending{color:#7f8593} .Running{color:#c678dd} .Completed{color:#98c379}
  .Failed{color:#e06c75} .Cancelled{color:#e5c07b}
  pre#log { background:#1b1e24; border:1px solid #3e4451; border-radius:6px; padding:10px;
            height:40vh; overflow-y:auto; font-size:11px; white-space:pre-wrap;
            font-family:"Cascadia Mono","Consolas",monospace; }
  .empty { color:#7f8593; font-style:italic; }
  .updated { color:#7f8593; font-size:11px; float:right; }
</style></head>
<body>
<h1>Queue <span class="updated" id="updated"></span></h1>
<div id="jobs"><p class="empty">Loading…</p></div>
<h1>Log</h1>
<pre id="log"></pre>
<script>
async function refresh() {
  try {
    const r = await fetch('/api/status', {cache:'no-store'});
    const data = await r.json();
    const jobsEl = document.getElementById('jobs');
    jobsEl.innerHTML = data.jobs.length ? data.jobs.map(j => `
      <div class="job">
        <div class="top"><span>[${j.id}] ${j.name}</span><span class="${j.state}">${j.state}</span></div>
        <div class="msg">${j.type} &middot; ${j.elapsed}</div>
        ${j.state === 'Running' ? `<div class="bar"><div style="width:${j.progress}%"></div></div>` : ''}
        ${j.message ? `<div class="msg">${j.message}</div>` : ''}
      </div>`).join('') : '<p class="empty">Queue is empty</p>';

    const logEl = document.getElementById('log');
    const atBottom = logEl.scrollTop + logEl.clientHeight >= logEl.scrollHeight - 24;
    logEl.textContent = data.log.join('\\n');
    if (atBottom) logEl.scrollTop = logEl.scrollHeight;

    document.getElementById('updated').textContent =
      new Date().toLocaleTimeString();
  } catch (e) { /* Fluent launching can pause the app briefly; try again */ }
}
refresh();
setInterval(refresh, 2000);
</script>
</body></html>"""


def _format_elapsed(seconds: float) -> str:
    if seconds <= 0:
        return "--"
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m {secs:02d}s"


def _tailscale_ips() -> set:
    """Ask the local Tailscale client for this machine's Tailscale IPs."""
    ips = set()
    for exe in ("tailscale", "tailscale.exe"):
        try:
            result = subprocess.run([exe, "ip"], capture_output=True,
                                    text=True, timeout=3)
            for line in result.stdout.splitlines():
                line = line.strip()
                if line:
                    ips.add(line)
            if ips:
                break
        except Exception:
            continue
    return ips


def _make_handler(queue, log_buffer):
    class Handler(BaseHTTPRequestHandler):

        def log_message(self, fmt, *args):
            pass    # silence the default per-request console spam

        def do_GET(self):
            if self.path.startswith("/api/status"):
                self._status()
            elif self.path in ("/", "/index.html"):
                self._page()
            else:
                self.send_error(404)

        def _page(self):
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _status(self):
            jobs = [{
                "id": j.job_id,
                "name": j.name,
                "type": j.type_name,
                "state": j.state.value,
                "progress": j.progress,
                "message": j.error or j.message,
                "elapsed": _format_elapsed(j.elapsed),
            } for j in queue.jobs()]

            payload = json.dumps({
                "jobs": jobs,
                "log": log_buffer.tail(300),
            }).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

    return Handler


class MonitorServer:
    """
    Serves the queue and log over HTTP.

    start()/stop() control a background thread; nothing touches the network
    until start() is called, so constructing one is always safe.
    """

    def __init__(self, queue, log_buffer, host: str = "0.0.0.0",
                port: int = 8765):
        self.queue = queue
        self.log_buffer = log_buffer
        self.host = host
        self.port = port
        self._httpd = None
        self._thread = None

    def start(self) -> bool:
        """Returns True on success, False if the port is already in use."""
        if self._httpd is not None:
            return True
        try:
            handler = _make_handler(self.queue, self.log_buffer)
            self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        except OSError as exc:
            log.warning(f"Phone monitor could not bind :{self.port}: {exc}")
            self._httpd = None
            return False

        self._thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True,
            name="web-monitor")
        self._thread.start()
        log.info(f"Phone monitor listening on :{self.port}")
        return True

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def urls(self) -> list:
        """Addresses this server can be reached at, Tailscale first."""
        addrs = list(sorted(_tailscale_ips()))
        try:
            addrs.append(socket.gethostbyname(socket.gethostname()))
        except Exception:
            pass
        if not addrs:
            addrs = ["localhost"]
        return [f"http://{ip}:{self.port}" for ip in addrs]
