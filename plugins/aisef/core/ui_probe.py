#!/usr/bin/env python3
"""AISEF ui_probe (V-05): abre a tela num Chrome real, muda a largura, rola, arrasta, toca e usa o teclado, e prova
com capturas o que nao se adapta ou nao se alcanca.

    python -I ui_probe.py run --url http://127.0.0.1:5173/ --out .aisef/reports/ui/T-012
    python -I ui_probe.py run --routes ui-probe.routes.json --out .aisef/reports/ui/T-012
    python -I ui_probe.py run --project . --task T-012 --base http://127.0.0.1:5173   (rotas e gestos do contrato)
    python -I ui_probe.py verify --report .aisef/reports/ui/T-012/report.json

Regras: UI-REFLOW, UI-CLIPPED, UI-UNREACHABLE, UI-COVERED, UI-TARGET, UI-KEYBOARD, UI-DEAD, UI-HOVER-ONLY,
UI-FOCUS-RETURN, UI-ZOOM, UI-MOTION, UI-OVERLAP, UI-INTERACTION. Larguras padrao 320, 375, 768, 1024 e 1440, com
toque emulado ate 480 px, e uma passada de zoom de 200% (640 px com escala 2).

Seguranca: so abre endereco local (localhost, 127.0.0.1, ::1, *.localhost, *.test, file://, data:) sem
`--allow-remote`, e nao clica em envio de formulario, link externo, download nem em texto de acao destrutiva.
Arquivo de rotas: {"base": url, "routes": [{"name", "path", "wait_for"?, "setup"?: [{"click": css}],
"interactions"?: [{"target": css, "gesture": drag|swipe|wheel|keyboard|hover|long_press|click, "axis"?: "x"|"y",
"expect"?: scroll|change, "widths"?: [..]}]}], "ignore"?: [{"rule", "selector", "reason"}]}.
"""
import argparse
import base64
import datetime
import json
import os
import re
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cdp_client as cdp  # noqa: E402
from ui_probe_input import Gestures  # noqa: E402
from ui_probe_io import apply_ignore, load_routes, routes_from_task, sha256, verify_report  # noqa: E402,F401

WIDTHS = [320, 375, 768, 1024, 1440]
ZOOM = 640
SEV = {"low": 1, "medium": 2, "high": 3, "critical": 4}
LOCAL = ("localhost", "127.0.0.1", "::1", "[::1]")
PROBE_JS = os.path.join(HERE, "ui_probe.js")


def is_local(url):
    u = urllib.parse.urlparse(url)
    if u.scheme in ("file", "data", "about"):
        return True
    h = (u.hostname or "").lower()
    return h in LOCAL or h.endswith(".localhost") or h.endswith(".test")


class Probe(Gestures):
    def __init__(self, page, out, log=None):
        self.p, self.out, self.log = page, out, log or (lambda *_: None)
        self.findings, self.interactions, self.shots, self.skipped = [], [], [], []
        self.js_src = open(PROBE_JS, encoding="utf-8").read()
        self.mobile = False
        os.makedirs(os.path.join(out, "shots"), exist_ok=True)
        page.on["Page.javascriptDialogOpening"] = lambda pg, _: pg.call("Page.handleJavaScriptDialog", accept=False)
        page.call("Page.enable")
        page.call("Runtime.enable")

    # ------------------------------------------------------------------ navegador
    def viewport(self, width, zoom=False):
        self.mobile = width <= 480 and not zoom
        self.p.call("Emulation.setDeviceMetricsOverride", width=width, height=900 if width > 480 else 780,
                    deviceScaleFactor=2 if zoom else 1, mobile=self.mobile)
        self.p.call("Emulation.setTouchEmulationEnabled", enabled=self.mobile, maxTouchPoints=5 if self.mobile else 1)

    def load(self, route):
        self.p.call("Page.navigate", url="about:blank")
        self.p.call("Page.navigate", url=route["url"])
        end = time.time() + 20
        while time.time() < end:
            try:
                if self.p.js("document.readyState") == "complete":
                    break
            except cdp.CDPError:
                pass
            time.sleep(0.15)
        if route.get("wait_for"):
            end = time.time() + 10
            while time.time() < end and not self.p.js("!!document.querySelector(%s)" % json.dumps(route["wait_for"])):
                time.sleep(0.15)
        time.sleep(0.5)
        self.p.js(self.js_src)
        for step in route.get("setup") or []:
            if step.get("click"):
                pid = self.P("resolve(%s)" % json.dumps(step["click"]))
                c = pid is not None and self.P("center(%d)" % pid)
                if c:
                    self.click(c["x"], c["y"])
                    time.sleep(0.4)
        self.P("blur()")

    def P(self, call):
        return self.p.js("window.__aisefProbe." + call)

    # ------------------------------------------------------------------ provas
    def shot(self, name, rect=None, mark=None):
        if mark:
            self.P("mark(%s)" % json.dumps(mark))
        try:
            if rect:
                w, h = max(200, min(rect["w"] + 48, 1600)), max(100, min(rect["h"] + 48, 1200))   # elemento pequeno: recorte com contexto
                clip = dict(x=max(0, rect["x"] + rect["w"] / 2 - w / 2), y=max(0, rect["y"] + rect["h"] / 2 - h / 2), width=w, height=h, scale=1)
            else:
                pg = self.p.js("({w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight})")
                clip = dict(x=0, y=0, width=pg["w"], height=min(pg["h"], 8000), scale=1)
            data = self.p.call("Page.captureScreenshot", format="png", captureBeyondViewport=True, clip=clip)["data"]
        finally:
            if mark:
                self.P("unmark()")
        rel = "shots/%s.png" % re.sub(r"[^A-Za-z0-9._-]", "-", name)
        path = os.path.join(self.out, rel)
        with open(path, "wb") as fh:
            fh.write(base64.b64decode(data))
        return {"path": rel, "sha256": sha256(path)}

    def add(self, route, width, f, rect=None):
        """Agrupa achados iguais (regra + grupo + largura); o primeiro de cada grupo ganha a captura contornada."""
        key = (route["name"], width, f["rule"], f.get("group") or f.get("selector"))
        for g in self.findings:
            if g["_key"] == key:
                g["count"] += 1
                return
        f = {k: v for k, v in f.items() if k not in ("pid",)}
        f.update(route=route["name"], width=width, count=1, _key=key)
        if rect is None and isinstance(f.get("_pid"), int):
            rect = self.P("rectOf(%d)" % f["_pid"])
        if rect and len([g for g in self.findings if g["route"] == route["name"] and g["width"] == width]) < 25:
            f["shot"] = self.shot("%s-w%s-F%02d" % (route["name"], width, len(self.findings) + 1), rect, rect)
        f.pop("_pid", None)
        self.findings.append(f)

    # ------------------------------------------------------------------ passadas
    def static(self, route, width, zoom):
        res = self.P("static()")
        for f in res["findings"]:
            f["_pid"] = f.get("pid")
            if zoom:
                f = dict(f, rule="UI-ZOOM", message="com zoom de 200%: " + f["message"])
            self.add(route, width, f)
        for c in res["overflow"]:
            if c["bar"] and c["scrolls"][c["axis"]]:
                continue
            works = []
            tries = (["swipe", "keyboard"] if self.mobile else ["wheel", "drag", "keyboard"]) + ([] if self.mobile or c["axis"] == "y" else ["wheel_x", "shift_wheel"])
            for g in tries:
                self.reset_scroll(c["pid"])
                r = self.gesture(c["pid"], g, c["axis"])
                if r and r["moved"]:
                    works.append(g)
            self.reset_scroll(c["pid"])
            pointer = [g for g in works if g in ("wheel", "drag", "swipe")]   # mouse sem trackpad ou dedo
            if pointer:
                continue
            NAMES = {"wheel_x": "trackpad", "shift_wheel": "Shift+roda", "keyboard": "teclado"}
            what = "%d item(ns) fora da area visivel%s" % (c["lost"], " (%d interativo(s))" % c["interactive"] if c["interactive"] else "")
            if works:
                msg = "%s; sem barra visivel nem %s: so alcanca com %s" % (what, "deslizar" if self.mobile else "arrastar ou roda",
                                                                         " ou ".join(NAMES.get(w, w) for w in works))
                sev = "medium"
            else:
                msg = "%s e nenhum jeito de chegar: tentei %s" % (what, ", ".join(tries))
                sev = "high"
            self.add(route, width, {"rule": "UI-UNREACHABLE", "severity": sev, "certainty": "high", "selector": c["selector"],
                                    "group": c["selector"], "message": msg, "tried": tries, "works": works}, c["rect"])
        return res

    def settled(self):
        """O Chrome rola o conteiner logo depois do foco: espera a posicao parar antes de medir."""
        prev = None
        for _ in range(8):
            time.sleep(0.06)
            info = self.P("focusInfo()")
            if prev is not None and info.get("visible") == prev.get("visible") and info.get("covered") == prev.get("covered"):
                return info
            prev = info
        return info

    def tab_order(self, route, width):
        focusables = self.P("focusList()")
        self.P("blur()")
        # o Chrome comeca o Tab de onde o ultimo foco estava: vai ate o fim, passa pelo navegador e da a volta inteira
        seq, seen, wrapped, trap = [], set(), False, False
        for _ in range(min(2 * len(focusables) + 6, 300)):
            self.key("Tab")
            info = self.settled()
            if info.get("none"):
                if wrapped:
                    break
                wrapped = True
                continue
            if info["pid"] in seen:
                trap = not wrapped   # repetiu sem nunca sair da pagina: ciclo preso
                break
            seen.add(info["pid"])
            seq.append(info["pid"])
            if info["visible"] <= 0.02 or info["covered"]:   # 2.4.11: foco inteiro escondido ou coberto por outro elemento
                rect = self.P("rectOf(%d)" % info["pid"])
                why = ("coberto por %s" % info["covered"]) if info["covered"] else "fora da area visivel"
                self.add(route, width, {"rule": "UI-COVERED", "severity": "high", "certainty": "high", "selector": info["selector"],
                                        "group": info["group"], "message": "com foco, mas %s: \"%s\"" % (why, info["label"])}, rect)
            elif not info["indicator"]:
                self.add(route, width, {"rule": "UI-KEYBOARD", "severity": "medium", "certainty": "medium", "selector": info["selector"],
                                        "group": "foco:" + info["group"], "message": "foco invisivel: nada muda no estilo ao receber o foco: \"%s\"" % info["label"]},
                         self.P("rectOf(%d)" % info["pid"]))
        missing = [p for p in focusables if p not in seen]
        if trap and missing:
            self.add(route, width, {"rule": "UI-KEYBOARD", "severity": "high", "certainty": "medium", "selector": self.P("sel(%d)" % seq[0]),
                                    "group": "armadilha", "message": "o Tab fica preso num ciclo de %d controle(s) e nao alcanca outros %d" % (len(seq), len(missing))})
        else:
            for p in missing[:15]:
                self.add(route, width, {"rule": "UI-KEYBOARD", "severity": "high", "certainty": "medium", "selector": self.P("sel(%d)" % p),
                                        "group": "sem-tab", "message": "focavel, mas o Tab nunca chega nele"}, self.P("rectOf(%d)" % p))
        self.P("blur()")
        return len(seq)

    def clicks(self, route, width, pointer_only):
        origin = "%s://%s" % urllib.parse.urlparse(route["url"])[:2]
        self.load(route)
        groups = [(c["group"], c) for c in self.P("clickables(%s)" % json.dumps(origin))]
        po = {x["group"] for x in pointer_only}
        tested = 0
        for group, item in groups:
            if item["skip"]:
                self.skipped.append({"route": route["name"], "width": width, "selector": item["selector"], "reason": item["skip"]})
                continue
            cur = [c for c in self.P("clickables(%s)" % json.dumps(origin)) if c["group"] == group]
            if not cur:
                continue
            c, pid = cur[0], cur[0]["pid"]
            pos = self.P("center(%d)" % pid)
            if not pos or not pos.get("hit"):   # fora da tela ou coberto: o mouse nao chega nele (ex.: link de pular conteudo)
                self.skipped.append({"route": route["name"], "width": width, "selector": c["selector"], "reason": "nao da para clicar onde esta"})
                continue
            self.P("focusInside(%d)" % pid)   # o clique foca o proprio controle: so conta foco que vai para outro lugar
            rect, base, dialogs = self.P("rectOf(%d)" % pid), self.P("sig()"), self.P("openDialogs()")
            self.click(pos["x"], pos["y"])
            time.sleep(0.4)
            tested += 1
            alive = self.P("sig()") != base
            if not alive:
                self.add(route, width, {"rule": "UI-DEAD", "severity": "medium", "certainty": "medium", "selector": c["selector"], "group": group,
                                        "message": "parece clicavel e nao faz nada ao ser clicado: \"%s\"" % c["label"]}, rect)
                continue
            opened = [d for d in self.P("openDialogs()") if d not in dialogs]
            if opened:
                self.key("Escape")
                time.sleep(0.35)
                still = [d for d in self.P("openDialogs()") if d in opened]
                act = self.P("active()")
                if still:
                    self.add(route, width, {"rule": "UI-FOCUS-RETURN", "severity": "medium", "certainty": "high", "selector": c["selector"], "group": group,
                                            "message": "abre %s e o Esc nao fecha" % opened[0]}, rect)
                elif act != pid and self.P("sel(%s)" % json.dumps(act)) != c["selector"]:
                    self.add(route, width, {"rule": "UI-FOCUS-RETURN", "severity": "medium", "certainty": "high", "selector": c["selector"], "group": group,
                                            "message": "fecha %s mas o foco nao volta a quem abriu (foi para %s)" % (opened[0], self.P("sel(%s)" % json.dumps(act)))}, rect)
            if group in po or not c["native"]:
                self.load(route)
                cur = [x for x in self.P("clickables(%s)" % json.dumps(origin)) if x["group"] == group]
                if cur:
                    pid = cur[0]["pid"]
                    if not self.P("focusInside(%d)" % pid):
                        self.add(route, width, {"rule": "UI-KEYBOARD", "severity": "high", "certainty": "high", "selector": c["selector"], "group": group,
                                                "message": "funciona no clique, mas o teclado nao chega nele: \"%s\"" % c["label"]}, rect)
                    else:
                        base = self.P("sig()")
                        self.key("Enter")
                        time.sleep(0.3)
                        if self.P("sig()") == base:
                            self.key(" ")
                            time.sleep(0.3)
                            if self.P("sig()") == base:
                                self.add(route, width, {"rule": "UI-KEYBOARD", "severity": "high", "certainty": "high", "selector": c["selector"], "group": group,
                                                        "message": "funciona no clique, mas Enter e Espaco nao fazem nada: \"%s\"" % c["label"]}, rect)
            self.load(route)
        return tested

    def declared(self, route, width):
        for i, it in enumerate(route.get("interactions") or []):
            if it.get("widths") and width not in it["widths"]:
                continue
            if not it.get("widths") and width not in self.inter_widths:
                continue
            self.load(route)
            name = "%s-w%s-I%02d" % (route["name"], width, i + 1)
            pid = self.P("resolve(%s)" % json.dumps(it["target"]))
            rec = {"route": route["name"], "width": width, "target": it["target"], "gesture": it["gesture"], "expect": it.get("expect", "any")}
            if pid is None or not self.P("rectOf(%d)" % pid):
                rec.update(ok=False, detail="o alvo nao existe ou nao aparece nesta largura")
            else:
                self.P("center(%d)" % pid)
                rect = self.P("rectOf(%d)" % pid)
                rec["before"] = self.shot(name + "-antes", rect)
                r = self.gesture(pid, it["gesture"], it.get("axis", "x")) or {}
                time.sleep(0.2)
                rec["after"] = self.shot(name + "-depois", self.P("rectOf(%d)" % pid) or rect)
                exp = it.get("expect", "any")
                ok = r.get("moved") if exp == "scroll" else r.get("changed") if exp == "change" else (r.get("moved") or r.get("changed"))
                rec.update(ok=bool(ok), detail=r.get("note") or ("o conteudo mexeu" if r.get("moved") else "a pagina mudou" if r.get("changed") else "nada mudou"))
            self.interactions.append(rec)
            if not rec["ok"]:
                self.add(route, width, {"rule": "UI-INTERACTION", "severity": "high", "certainty": "high", "selector": it["target"],
                                        "group": "%s:%s" % (it["target"], it["gesture"]),
                                        "message": "interacao declarada nao funciona: %s em %s (%s)" % (it["gesture"], it["target"], rec["detail"])})

    def motion(self, route):
        self.viewport(1440)
        self.p.call("Emulation.setEmulatedMedia", features=[{"name": "prefers-reduced-motion", "value": "reduce"}])
        try:
            self.load(route)
            time.sleep(1.0)
            for a in self.P("motion()") or []:
                inf = a["iterations"] is None or a["iterations"] == "Infinity" or (isinstance(a["iterations"], (int, float)) and a["iterations"] > 1e9)
                self.add(route, "reduce", {"rule": "UI-MOTION", "severity": "medium" if inf else "low", "certainty": "high", "selector": a["target"],
                                           "group": a["target"], "message": "animacao %s rodando com prefers-reduced-motion: reduce (%s ms%s)"
                                           % (a["name"] or "", a["duration"], ", infinita" if inf else "")})
        finally:
            self.p.call("Emulation.setEmulatedMedia", features=[{"name": "prefers-reduced-motion", "value": ""}])

    def run(self, routes, widths, click_widths, inter_widths, zoom=True):
        self.inter_widths = inter_widths
        stats = {}
        passes = [(w, False) for w in widths] + ([(ZOOM, True)] if zoom else [])
        for route in routes:
            for w, z in passes:
                t0 = time.time()
                label = w if not z else "%d-zoom" % w
                self.viewport(w, z)
                self.load(route)
                full = self.shot("%s-w%s" % (route["name"], label))
                self.shots.append(dict(full, route=route["name"], width=label))
                res = self.static(route, label, z)
                st = {"tabs": 0, "clicks": 0}
                if not z:
                    self.load(route)
                    st["tabs"] = self.tab_order(route, label)
                    if w in click_widths:
                        st["clicks"] = self.clicks(route, label, res["pointerOnly"])
                    self.declared(route, w)
                st["seconds"] = round(time.time() - t0, 1)
                stats["%s@%s" % (route["name"], label)] = st
                self.log("%s @ %s: %s" % (route["name"], label, st))
            self.motion(route)
        return stats


def probe(routes, out, widths=None, click_widths=(375, 1440), inter_widths=(375, 1440), ignore=(), zoom=True, log=None, chrome=None):
    t0 = time.time()
    os.makedirs(out, exist_ok=True)
    with cdp.Browser(chrome) as b:
        page = b.page()
        pr = Probe(page, out, log)
        stats = pr.run(routes, list(widths or WIDTHS), list(click_widths), list(inter_widths), zoom)
        version, nosb = b.version(), b.no_sandbox
    for f in pr.findings:
        f.pop("_key", None)
    findings, ignored = apply_ignore(pr.findings, list(ignore))
    findings.sort(key=lambda f: (-SEV[f["severity"]], f["rule"], str(f["width"])))
    for i, f in enumerate(findings, 1):
        f["id"] = "F-%03d" % i
    by_rule, by_sev = {}, {}
    for f in findings:
        by_rule[f["rule"]] = by_rule.get(f["rule"], 0) + f["count"]
        by_sev[f["severity"]] = by_sev.get(f["severity"], 0) + 1
    worst = max((f["severity"] for f in findings), key=lambda s: SEV[s], default=None)
    report = {"schema_version": "0.1.0", "tool": "aisef ui_probe", "generated_at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat(),
              "browser": version, "chrome_sandbox": not nosb, "routes": [{"name": r["name"], "url": r["url"]} for r in routes],
              "widths": list(widths or WIDTHS) + ([str(ZOOM) + "-zoom"] if zoom else []), "findings": findings, "ignored": ignored,
              "interactions": pr.interactions, "shots": pr.shots, "skipped_clicks": pr.skipped, "stats": stats,
              "summary": {"by_rule": by_rule, "by_severity": by_sev, "worst": worst, "seconds": round(time.time() - t0, 1)}}
    with open(os.path.join(out, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["run", "verify"])
    ap.add_argument("--url")
    ap.add_argument("--routes")
    ap.add_argument("--out")
    ap.add_argument("--report")
    ap.add_argument("--project", default=".")
    ap.add_argument("--task", help="le rotas e gestos da ui_behavior do Task Contract; relatorio em .aisef/reports/ui/<T>/probe")
    ap.add_argument("--base", help="onde a UI roda (com --task)")
    ap.add_argument("--widths", default=",".join(map(str, WIDTHS)))
    ap.add_argument("--click-widths", default="375,1440")
    ap.add_argument("--no-zoom", action="store_true")
    ap.add_argument("--fail-on", default="medium", choices=list(SEV))
    ap.add_argument("--allow-remote", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    if a.command == "verify":
        if not a.report:
            ap.error("--report e obrigatorio")
        probs = verify_report(a.report)
        print("provas intactas" if not probs else "\n".join(probs))
        return 1 if probs else 0
    if not (a.url or a.routes or a.task) or not (a.out or a.task):
        ap.error("use --url, --routes ou --task, e --out")
    routes, ignore = load_routes(a)
    remote = [r["url"] for r in routes if not is_local(r["url"])]
    if remote and not a.allow_remote:
        print("endereco nao local: %s (a sonda clica e digita na pagina; use --allow-remote so num ambiente de teste)" % remote[0])
        return 2
    widths = [int(x) for x in a.widths.split(",") if x.strip()]
    try:
        rep = probe(routes, a.out, widths, [int(x) for x in a.click_widths.split(",") if x.strip()], ignore=ignore,
                    zoom=not a.no_zoom, log=None if a.quiet else (lambda m: print(m, file=sys.stderr)))
    except cdp.CDPError as e:
        print("ui_probe: %s" % e)
        return 2
    for f in rep["findings"]:
        print("%s %-8s %-16s %-9s %s%s" % (f["id"], f["severity"], f["rule"], f["width"], f["message"], " (x%d)" % f["count"] if f["count"] > 1 else ""))
    bad = [i for i in rep["interactions"] if not i["ok"]]
    print("%d achado(s), %d interacao(oes) declarada(s), %d falhou(aram); relatorio em %s"
          % (len(rep["findings"]), len(rep["interactions"]), len(bad), os.path.join(a.out, "report.json")))
    return 1 if any(SEV[f["severity"]] >= SEV[a.fail_on] for f in rep["findings"]) else 0


if __name__ == "__main__":
    sys.exit(main())
