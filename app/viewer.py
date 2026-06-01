"""Threaded MJPEG server so any device on the LAN can watch the annotated feed
in a browser (http://<nuc-ip>:8080) — no X11/display passthrough needed.

The page also has an "ask a question" box wired to the VLM: typing a question
sets it as the live prompt and triggers an immediate run; the answer is polled
back onto the page. This is the easiest way to interact during a demo (the
IOTCONNECT cloud command `ask-vlm` does the same thing remotely).
"""
from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

log = logging.getLogger("viewer")


class _FrameStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._jpeg: bytes | None = None

    def update(self, frame) -> None:
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            with self._lock:
                self._jpeg = buf.tobytes()

    def get(self) -> bytes | None:
        with self._lock:
            return self._jpeg


_STORE = _FrameStore()
# Hooks wired up by MjpegServer.start(): ask(question)->None, answer()->str.
_HOOKS: dict = {"ask": None, "answer": None}

_PAGE_TEMPLATE = """<!doctype html><html><head><title>Physical AI Demo</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
 body{margin:0;padding-top:__PAD__px;background:#111;color:#eee;font-family:sans-serif;text-align:center}
 h2{padding:8px;margin:0}
 img{max-width:100%;height:auto;background:#000}
 .bar{display:flex;gap:6px;max-width:900px;margin:8px auto;padding:0 8px}
 #q{flex:1;padding:10px;font-size:16px;border-radius:6px;border:1px solid #444;background:#222;color:#eee}
 button{padding:10px 16px;font-size:16px;border:0;border-radius:6px;background:#2d7;color:#012;cursor:pointer}
 #ans{max-width:900px;margin:8px auto;padding:10px;background:#1b1b1b;border-radius:6px;
      min-height:2em;text-align:left;color:#0ff;white-space:pre-wrap}
 .hint{color:#888;font-size:13px}
</style></head>
<body>
 <h2>NUC Physical AI &mdash; live perception</h2>
 <img id="cam" alt="(connecting to camera...)">
 <div class="bar">
   <input id="q" placeholder="Ask the VLM about the scene, e.g. 'How many people do you see?'"
          onkeydown="if(event.key==='Enter')ask()">
   <button onclick="ask()">Ask</button>
 </div>
 <div id="ans">(waiting for the model...)</div>
 <div class="hint">The answer updates live. Asking a question makes it the recurring prompt
   until you ask another.</div>
<script>
 async function ask(){
   const q=document.getElementById('q').value.trim();
   if(!q)return;
   document.getElementById('ans').innerText='(thinking...)';
   await fetch('/ask',{method:'POST',body:q});
 }
 async function pollAnswer(){
   try{const r=await fetch('/answer');document.getElementById('ans').innerText=await r.text();}
   catch(e){}
   setTimeout(pollAnswer,1500);
 }
 // Frame-polling preview using the browser's NATIVE image loader (no fetch /
 // blob URLs, which behave inconsistently across browsers and over the LAN).
 // Each frame loads as a plain <img>; onload chains the next request, which also
 // self-throttles to the network speed. Works in every browser/webview.
 const cam=document.getElementById('cam');
 function nextFrame(){ cam.src='/frame?t='+Date.now(); }
 cam.onload  = function(){ setTimeout(nextFrame, 80);  };   // ~12 fps when fast
 cam.onerror = function(){ setTimeout(nextFrame, 500); };   // retry slower on error/503
 nextFrame();
 pollAnswer();
</script>
</body></html>"""


def _build_page(top_pad: int) -> bytes:
    return _PAGE_TEMPLATE.replace("__PAD__", str(int(top_pad))).encode("utf-8")


# Default page (no extra top padding); MjpegServer.start() rebuilds it with the
# configured VIEWER_TOP_PAD so the feed clears an embedding dashboard's header.
_PAGE = _build_page(0)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence per-request logging
        pass

    def _send(self, code, ctype, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, "text/html", _PAGE)
            return
        if self.path == "/answer":
            fn = _HOOKS.get("answer")
            text = fn() if fn else ""
            self._send(200, "text/plain; charset=utf-8", (text or "").encode("utf-8"))
            return
        if self.path.startswith("/frame"):
            jpeg = _STORE.get()
            if jpeg is None:
                self.send_response(503)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(jpeg)))
            self.end_headers()
            self.wfile.write(jpeg)
            return
        if self.path == "/stream":
            self.send_response(200)
            self.send_header(
                "Content-Type", "multipart/x-mixed-replace; boundary=frame"
            )
            self.end_headers()
            try:
                while True:
                    jpeg = _STORE.get()
                    if jpeg is None:
                        continue
                    self.wfile.write(b"--frame\r\n")
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode())
                    self.wfile.write(jpeg)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                return
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/ask":
            length = int(self.headers.get("Content-Length", 0) or 0)
            question = self.rfile.read(length).decode("utf-8", "replace") if length else ""
            fn = _HOOKS.get("ask")
            if fn:
                try:
                    fn(question)
                except Exception:  # noqa: BLE001
                    log.exception("ask hook failed")
            self._send(200, "text/plain", b"ok")
        else:
            self.send_response(404)
            self.end_headers()


class MjpegServer:
    def __init__(self, port: int):
        self.port = port
        self._server: ThreadingHTTPServer | None = None

    def start(self, ask_cb=None, answer_cb=None, top_pad=0) -> None:
        global _PAGE
        _PAGE = _build_page(top_pad)
        _HOOKS["ask"] = ask_cb
        _HOOKS["answer"] = answer_cb
        self._server = ThreadingHTTPServer(("0.0.0.0", self.port), _Handler)
        t = threading.Thread(target=self._server.serve_forever, daemon=True)
        t.start()
        log.info("MJPEG viewer at http://<device-ip>:%d/", self.port)

    @staticmethod
    def publish(frame) -> None:
        _STORE.update(frame)

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
