#!/usr/bin/env python3
"""AISEF ui_probe: gestos reais pelo DevTools Protocol (mouse, roda, toque, teclado), usados pela sonda (V-05).
A classe espera `self.p` (cdp_client.Page), `self.mobile` e `self.P` (chamada a window.__aisefProbe)."""
import json
import time

KEYS = {"Tab": 9, "Enter": 13, "Escape": 27, " ": 32, "End": 35, "ArrowRight": 39, "ArrowDown": 40}
CODES = {" ": "Space"}


class Gestures:
    def mouse(self, kind, x, y, **kw):
        self.p.call("Input.dispatchMouseEvent", type=kind, x=x, y=y, **kw)

    def click(self, x, y):
        self.mouse("mouseMoved", x, y)
        self.mouse("mousePressed", x, y, button="left", clickCount=1, buttons=1)
        self.mouse("mouseReleased", x, y, button="left", clickCount=1)

    def key(self, name, shift=False):
        code = KEYS[name]
        base = dict(key=name, code=CODES.get(name, name), windowsVirtualKeyCode=code, nativeVirtualKeyCode=code,
                    modifiers=8 if shift else 0)
        text = {"Enter": "\r", " ": " "}.get(name)
        self.p.call("Input.dispatchKeyEvent", type="keyDown" if text else "rawKeyDown", **dict(base, **({"text": text} if text else {})))
        self.p.call("Input.dispatchKeyEvent", type="keyUp", **base)

    def drag(self, x, y, dx, dy):
        self.mouse("mouseMoved", x, y)
        self.mouse("mousePressed", x, y, button="left", clickCount=1, buttons=1)
        for i in range(1, 9):
            self.mouse("mouseMoved", x + dx * i / 8, y + dy * i / 8, button="left", buttons=1)
            time.sleep(0.016)
        self.mouse("mouseReleased", x + dx, y + dy, button="left", clickCount=1)

    def swipe(self, x, y, dx, dy, hold=0.0):
        if not self.mobile:
            self.p.call("Emulation.setTouchEmulationEnabled", enabled=True, maxTouchPoints=5)
        self.p.call("Input.dispatchTouchEvent", type="touchStart", touchPoints=[{"x": x, "y": y}])
        time.sleep(hold)
        for i in range(1, 9):
            self.p.call("Input.dispatchTouchEvent", type="touchMove", touchPoints=[{"x": x + dx * i / 8, "y": y + dy * i / 8}])
            time.sleep(0.016)
        self.p.call("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])
        if not self.mobile:
            self.p.call("Emulation.setTouchEmulationEnabled", enabled=False, maxTouchPoints=1)

    def gesture(self, pid, gesture, axis="x"):
        """Faz o gesto no centro do elemento e devolve se o conteudo dele mexeu e se a pagina mudou."""
        c = self.P("center(%d)" % pid)
        if not c:
            return None
        before, sig = self.P("scrollState(%d)" % pid), self.P("sig()")
        span = max(60, min(240, (c["w"] if axis == "x" else c["h"]) * 0.6))
        dx, dy = (-span, 0) if axis == "x" else (0, -span)
        if gesture == "drag":
            self.drag(c["x"] + span / 2 if axis == "x" else c["x"], c["y"] + span / 2 if axis == "y" else c["y"], dx, dy)
        elif gesture == "swipe":
            self.swipe(c["x"] + span / 2 if axis == "x" else c["x"], c["y"] + span / 2 if axis == "y" else c["y"], dx, dy)
        elif gesture == "long_press":
            self.swipe(c["x"], c["y"], 0, 0, hold=0.8)
        elif gesture in ("wheel", "wheel_x", "shift_wheel"):
            ddx, ddy = (300, 0) if gesture == "wheel_x" else (0, 300)
            self.mouse("mouseWheel", c["x"], c["y"], deltaX=ddx, deltaY=ddy, modifiers=8 if gesture == "shift_wheel" else 0)
        elif gesture == "keyboard":
            if not self.P("focusInside(%d)" % pid):
                return {"moved": False, "changed": False, "note": "nada focavel no alvo"}
            for k in (("ArrowRight", "ArrowRight", "End") if axis == "x" else ("ArrowDown", "ArrowDown", "End")):
                self.key(k)
        elif gesture == "hover":
            self.mouse("mouseMoved", c["x"], c["y"])
        elif gesture == "click":
            self.click(c["x"], c["y"])
        time.sleep(0.35)
        return {"moved": self.P("scrollState(%d)" % pid) != before, "changed": self.P("sig()") != sig}

    def reset_scroll(self, pid):
        sel =self.P("sel(%d)" % pid)
        if sel:
            self.p.js("(function(){var e=document.querySelector(%s);if(!e)return;[e].concat([].slice.call(e.querySelectorAll('*')))"
                      ".forEach(function(k){if(k.scrollLeft||k.scrollTop){k.scrollLeft=0;k.scrollTop=0;}});})()" % json.dumps(sel))
