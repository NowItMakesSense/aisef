#!/usr/bin/env python3
"""AISEF: cliente minimo do Chrome DevTools Protocol (V-05), so com a biblioteca padrao.

Abre o Chrome/Edge headless com `--remote-debugging-port=0`, descobre a porta pelo arquivo DevToolsActivePort e fala
com a pagina por WebSocket (RFC 6455, cliente: quadros mascarados, sem extensoes). Serve a sonda de UI
(`ui_probe.py`): eventos reais de mouse, toque e teclado, emulacao de tela e capturas.

    with Browser() as b:
        page = b.page()
        page.call("Page.navigate", url="http://127.0.0.1:8000/")
"""
import base64
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


class CDPError(RuntimeError):
    pass


def find_chrome():
    import design_check
    return os.environ.get("CHROME_PATH") or design_check.find_chrome()


class WebSocket:
    """WebSocket cliente sincrono: texto de ida, texto de volta, ping respondido, fragmentos juntados."""

    def __init__(self, url, timeout=30):
        assert url.startswith("ws://"), url
        hostport, _, path = url[5:].partition("/")
        host, _, port = hostport.partition(":")
        self.sock = socket.create_connection((host, int(port or 80)), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = ("GET /%s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n" % (path, hostport, key))
        self.sock.sendall(req.encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise CDPError("WebSocket: conexao fechada no handshake")
            head += chunk
        status, _, rest = head.partition(b"\r\n\r\n")
        if b" 101 " not in status.split(b"\r\n")[0]:
            raise CDPError("WebSocket: handshake recusado: %r" % status[:120])
        self.buf = bytearray(rest)

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(max(65536, n - len(self.buf)))
            if not chunk:
                raise CDPError("WebSocket: conexao fechada")
            self.buf += chunk
        out = bytes(self.buf[:n])
        del self.buf[:n]
        return out

    def _send_frame(self, opcode, payload):
        n = len(payload)
        head = bytes([0x80 | opcode])
        if n < 126:
            head += bytes([0x80 | n])
        elif n < 65536:
            head += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            head += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        m = int.from_bytes((mask * (n // 4 + 1))[:n], "big") if n else 0
        body = (int.from_bytes(payload, "big") ^ m).to_bytes(n, "big") if n else b""
        self.sock.sendall(head + mask + body)

    def send(self, text):
        self._send_frame(0x1, text.encode("utf-8"))

    def recv(self):
        parts = []
        while True:
            b1, b2 = self._read(2)
            fin, opcode, n = b1 & 0x80, b1 & 0x0F, b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if b2 & 0x80 else None
            data = self._read(n)
            if mask:
                data = bytes(c ^ mask[i % 4] for i, c in enumerate(data))
            if opcode == 0x9:
                self._send_frame(0xA, data)
                continue
            if opcode == 0x8:
                raise CDPError("WebSocket: fechado pelo navegador")
            if opcode in (0x0, 0x1, 0x2):
                parts.append(data)
                if fin:
                    return b"".join(parts).decode("utf-8", "replace")

    def close(self):
        try:
            self._send_frame(0x8, b"")
        except OSError:
            pass
        self.sock.close()


class Page:
    """Uma aba: `call` espera a resposta do comando; eventos chegam em `on` (metodo -> funcao)."""

    def __init__(self, ws_url, timeout=60):
        self.ws = WebSocket(ws_url, timeout=timeout)
        self.next_id = 0
        self.on = {}
        self.events = []
        self.pending = {}   # respostas que chegaram enquanto outro comando (de um evento) esperava a dele

    def call(self, method, **params):
        self.next_id += 1
        mid = self.next_id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = self.pending.pop(mid, None) or json.loads(self.ws.recv())
            if "id" in msg and msg["id"] != mid:
                self.pending[msg["id"]] = msg
                continue
            if msg.get("id") == mid:
                if "error" in msg:
                    raise CDPError("%s: %s" % (method, msg["error"].get("message")))
                return msg.get("result", {})
            if "method" in msg:
                self.events.append(msg["method"])
                del self.events[:-200]
                fn = self.on.get(msg["method"])
                if fn:
                    fn(self, msg.get("params", {}))

    def js(self, expr, await_promise=True):
        """Avalia `expr` na pagina e devolve o valor (JSON). Excecao da pagina vira CDPError."""
        r = self.call("Runtime.evaluate", expression=expr, awaitPromise=await_promise, returnByValue=True,
                      userGesture=True)
        if r.get("exceptionDetails"):
            d = r["exceptionDetails"]
            raise CDPError("JS: %s" % ((d.get("exception") or {}).get("description") or d.get("text")))
        return (r.get("result") or {}).get("value")

    def close(self):
        self.ws.close()


class Browser:
    """Chrome headless com perfil temporario. `page()` devolve a aba inicial."""

    def __init__(self, chrome=None, timeout=20):
        self.chrome = chrome or find_chrome()
        if not self.chrome or not os.path.exists(self.chrome):
            raise CDPError("Chrome/Edge nao encontrado (defina CHROME_PATH): %s" % (self.chrome or "nenhum no sistema"))
        self.timeout = timeout
        self.proc = self.profile = None
        self.no_sandbox = False

    def _launch(self, no_sandbox):
        self.profile = tempfile.mkdtemp(prefix="aisef-probe-")
        args = [self.chrome, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                "--disable-extensions", "--disable-background-networking", "--disable-sync", "--mute-audio",
                "--remote-debugging-port=0", "--remote-allow-origins=*", "--user-data-dir=" + self.profile,
                "--window-size=1440,900", "about:blank"]
        if no_sandbox:
            args.insert(1, "--no-sandbox")
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        port_file = os.path.join(self.profile, "DevToolsActivePort")
        end = time.time() + self.timeout
        while time.time() < end:
            if self.proc.poll() is not None:
                return None
            if os.path.exists(port_file):
                with open(port_file, encoding="utf-8") as fh:
                    first = fh.readline().strip()
                if first.isdigit():
                    return int(first)
            time.sleep(0.1)
        return None

    def __enter__(self):
        port = self._launch(False)
        if port is None and os.name != "nt":  # Linux sem user namespaces (CI): sem o sandbox do Chrome
            self.close()
            self.no_sandbox = True
            port = self._launch(True)
        if port is None:
            self.close()
            raise CDPError("o Chrome nao abriu a porta de depuracao")
        self.port = port
        return self

    def targets(self):
        with urllib.request.urlopen("http://127.0.0.1:%d/json/list" % self.port, timeout=10) as r:
            return json.load(r)

    def page(self):
        end = time.time() + self.timeout
        while time.time() < end:
            pages = [t for t in self.targets() if t.get("type") == "page" and t.get("webSocketDebuggerUrl")]
            if pages:
                return Page(pages[0]["webSocketDebuggerUrl"])
            time.sleep(0.2)
        raise CDPError("nenhuma aba disponivel no Chrome")

    def version(self):
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/json/version" % self.port, timeout=10) as r:
                return json.load(r).get("Browser", "")
        except OSError:
            return ""

    def close(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        if self.profile:
            shutil.rmtree(self.profile, ignore_errors=True)

    def __exit__(self, *exc):
        self.close()
