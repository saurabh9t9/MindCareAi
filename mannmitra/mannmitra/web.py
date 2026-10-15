"""Web chat + institution dashboard using only the Python standard library.

  python -m mannmitra.web            -> http://127.0.0.1:8000
  Dashboard:  /api/dashboard?token=YOUR_TOKEN   (set MANNMITRA_ADMIN_TOKEN; disabled if unset)
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .agent import MannMitraAgent
from .llm import get_provider

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>MannMitra</title>
<style>
:root{--teal:#17423a;--coral:#ff8a5b;--tint:#edf5f1;--ink:#1f2a30}
*{box-sizing:border-box}body{margin:0;font-family:Calibri,Arial,sans-serif;background:#fff;color:var(--ink);display:flex;flex-direction:column;height:100vh}
header{background:var(--teal);color:#fff;padding:12px 16px}header b{font-size:20px}header small{display:block;color:#c5e0d6}
.note{background:var(--tint);padding:8px 16px;font-size:13px}
#log{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:10px}
.m{max-width:80%;padding:10px 14px;border-radius:14px;white-space:pre-wrap;line-height:1.4}
.bot{background:var(--tint);align-self:flex-start}.me{background:var(--teal);color:#fff;align-self:flex-end}
form{display:flex;gap:8px;padding:12px;border-top:1px solid #dde;}
input{flex:1;padding:12px;border:1px solid #bcd;border-radius:10px;font-size:16px}
button{background:var(--coral);border:0;border-radius:10px;padding:0 18px;font-weight:bold;font-size:16px;cursor:pointer}
.chips{padding:0 12px 8px;display:flex;gap:6px;flex-wrap:wrap}.chips button{background:var(--tint);padding:6px 12px;font-size:13px;font-weight:normal;height:30px}
</style></head><body>
<header><b>MannMitra</b><small>A friendly AI for how you're feeling</small></header>
<div class="note">I'm an AI, not a doctor or therapist. In an emergency call your local emergency number (112 in India).</div>
<div id="log"></div>
<div class="chips"><button data-t="/checkin">Check-in</button><button data-t="/screen">Self-check</button><button data-t="/tools">Calming tools</button><button data-t="/privacy">Privacy</button></div>
<form id="f"><input id="t" autocomplete="off" placeholder="Type how you're feeling..."><button>Send</button></form>
<script>
let uid=localStorage.getItem('mm_uid');if(!uid){uid=Math.random().toString(36).slice(2)+Date.now().toString(36);localStorage.setItem('mm_uid',uid)}
const log=document.getElementById('log');
function add(c,t){const d=document.createElement('div');d.className='m '+c;d.textContent=t;log.appendChild(d);log.scrollTop=log.scrollHeight}
async function send(t){add('me',t);try{const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:uid,message:t})});const j=await r.json();add('bot',j.reply||j.error)}catch(e){add('bot','Sorry, I could not connect. Please try again.')}}
document.getElementById('f').onsubmit=e=>{e.preventDefault();const i=document.getElementById('t');const v=i.value.trim();if(v){i.value='';send(v)}};
document.querySelectorAll('.chips button').forEach(b=>b.onclick=()=>send(b.dataset.t));
send('/start');
</script></body></html>"""


def make_server(agent, host="127.0.0.1", port=8000):
    admin = os.environ.get("MANNMITRA_ADMIN_TOKEN", "")

    class H(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/":
                return self._send(200, PAGE, "text/html")
            if u.path == "/api/dashboard":
                tok = parse_qs(u.query).get("token", [""])[0]
                if not admin or tok != admin:
                    return self._send(403, json.dumps({"error": "dashboard disabled or bad token"}))
                return self._send(200, json.dumps(agent.store.aggregate()))
            self._send(404, json.dumps({"error": "not found"}))

        def do_POST(self):
            if urlparse(self.path).path != "/api/chat":
                return self._send(404, json.dumps({"error": "not found"}))
            try:
                n = int(self.headers.get("Content-Length", 0))
                if n > 10000:
                    return self._send(413, json.dumps({"error": "too large"}))
                body = json.loads(self.rfile.read(n) or b"{}")
                reply = agent.handle(str(body.get("user_id", ""))[:64] or "anon", str(body.get("message", "")), "web")
                self._send(200, json.dumps({"reply": reply}, ensure_ascii=False))
            except Exception:
                self._send(400, json.dumps({"error": "bad request"}))

        def log_message(self, *a):  # keep logs free of user content
            pass

    return ThreadingHTTPServer((host, port), H)


def main():
    agent = MannMitraAgent(get_provider())
    port = int(os.environ.get("PORT", "8000"))
    srv = make_server(agent, port=port)
    print(f"MannMitra ({agent.provider.name} mode) running at http://127.0.0.1:{port}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
