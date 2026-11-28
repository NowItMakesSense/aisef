#!/usr/bin/env python3
"""Testes da V-05: a sonda de UI acha cada defeito numa pagina de exemplo e passa limpa na versao corrigida.

Cada par em fixtures/ui/ tem o defeito (`*_bad.html`) e a correcao (`*_ok.html`). Roda num Chrome real; sem Chrome,
so os testes que nao precisam dele rodam (e a sonda tem de sair com erro, nunca com "tudo ok")."""
import functools
import http.server
import json
import os
import shutil
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cdp_client as cdp  # noqa: E402
import ui_probe as up  # noqa: E402

FIX = os.path.join(HERE, "fixtures", "ui")
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
fails = total = 0


def check(name, cond, extra=None):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond or extra is None else "  -> %s" % (extra,)))
    fails += not cond


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=FIX))
srv.handle_error = lambda *a: None
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d/" % srv.server_port

# ---------------------------------------------------------------- sem navegador
check("so endereco local por padrao", up.is_local("http://localhost:5173/x") and up.is_local("http://app.test/") and up.is_local("file:///c/x.html")
      and not up.is_local("https://example.com/"))
rc = up.main(["run", "--url", "https://example.com/", "--out", os.path.join(work, "remote"), "--quiet"])
check("endereco remoto sem --allow-remote: recusa (sai 2) sem abrir nada", rc == 2 and not os.path.exists(os.path.join(work, "remote", "report.json")))
old = os.environ.get("CHROME_PATH")
os.environ["CHROME_PATH"] = os.path.join(work, "nao-existe", "chrome.exe")
rc = up.main(["run", "--url", BASE + "reflow_ok.html", "--out", os.path.join(work, "nochrome"), "--quiet"])
check("sem Chrome: sai com erro (2), nunca com 'tudo ok'", rc == 2 and not os.path.exists(os.path.join(work, "nochrome", "report.json")))
if old is None:
    os.environ.pop("CHROME_PATH")
else:
    os.environ["CHROME_PATH"] = old
kept, ign = up.apply_ignore([{"rule": "UI-CLIPPED", "selector": "span.n"}, {"rule": "UI-REFLOW", "selector": "div.x"}],
                            [{"rule": "UI-CLIPPED", "selector": "span.n", "reason": "corte de proposito, texto no rodape"}])
check("ignore com motivo: o achado sai da lista e o motivo fica no relatorio",
      [k["rule"] for k in kept] == ["UI-REFLOW"] and ign[0]["reason"].startswith("corte"))

if not cdp.find_chrome():
    print("Chrome nao encontrado: testes no navegador pulados")
else:
    CASES = [  # (pagina, largura, regra esperada no defeito, pagina corrigida)
        ("reflow_bad", 375, "UI-REFLOW", "reflow_ok"),
        ("clipped_bad", 1440, "UI-CLIPPED", "clipped_ok"),
        ("unreachable_bad", 1440, "UI-UNREACHABLE", "unreachable_ok"),
        ("covered_bad", 1440, "UI-COVERED", "covered_ok"),
        ("target_bad", 1440, "UI-TARGET", "target_ok"),
        ("keyboard_bad", 1440, "UI-KEYBOARD", "keyboard_ok"),
        ("dead_bad", 1440, "UI-DEAD", "dead_ok"),
        ("hover_bad", 1440, "UI-HOVER-ONLY", "hover_ok"),
        ("dialog_bad", 1440, "UI-FOCUS-RETURN", "dialog_ok"),
        ("motion_bad", 1440, "UI-MOTION", "motion_ok"),
        ("overlap_bad", 1440, "UI-OVERLAP", "overlap_ok"),
    ]
    DRAG = [{"target": ".pills", "gesture": "drag", "expect": "scroll"}]
    with cdp.Browser() as b:
        page = b.page()

        def run(name, width, zoom=False, inter=None):
            pr = up.Probe(page, os.path.join(work, name + "-%d" % width))
            route = {"name": name, "url": BASE + name + ".html"}
            if inter:
                route["interactions"] = inter
            pr.run([route], [width], [width], [width], zoom=zoom)
            return pr

        for bad, width, rule, ok in CASES:
            pb = run(bad, width)
            got = [f["rule"] for f in pb.findings]
            check("%s: acha %s" % (bad, rule), rule in got, got)
            po = run(ok, width)
            check("%s: a versao corrigida passa limpa" % ok, not po.findings, [(f["rule"], f["message"][:70]) for f in po.findings])

        pr = run("keyboard_bad", 1440)
        msgs = " | ".join(f["message"] for f in pr.findings)
        check("teclado: acusa o clicavel que o Tab nao alcanca e o foco invisivel", "teclado nao chega" in msgs and "foco invisivel" in msgs, msgs)
        pr = run("dialog_bad", 1440)
        msgs = " | ".join(f["message"] for f in pr.findings)
        check("janela: acusa o Esc que nao fecha e o foco que nao volta", "Esc nao fecha" in msgs and "foco nao volta" in msgs, msgs)
        pr = run("unreachable_hiddenbar", 1440)
        f = [x for x in pr.findings if x["rule"] == "UI-UNREACHABLE"]
        check("rola sem barra e sem arrastar: so com trackpad ou Shift+roda (medium, diz o que funcionou)",
              f and f[0]["severity"] == "medium" and "Shift+roda" in f[0]["message"], [x["message"] for x in pr.findings])
        pr = run("unreachable_hiddenbar", 375)
        check("mesma lista no celular: o toque alcanca, sem achado", not [x for x in pr.findings if x["rule"] == "UI-UNREACHABLE"])
        pr = run("unreachable_bad", 1440)
        f = [x for x in pr.findings if x["rule"] == "UI-UNREACHABLE"][0]
        check("overflow hidden sem gesto: high, com a lista do que foi tentado", f["severity"] == "high" and f["works"] == [] and "drag" in f["tried"])

        pr = run("zoom_bad", 1440, zoom=True)
        rules = [(f["rule"], f["width"]) for f in pr.findings]
        check("zoom de 200%: caixa de 700 px cabe em 1440 e estoura com zoom (UI-ZOOM)", ("UI-ZOOM", "640-zoom") in rules
              and not [r for r in rules if r[1] == 1440], rules)

        pr = run("drag_bad", 1440, inter=DRAG)
        check("interacao declarada (arrastar) que nao funciona: UI-INTERACTION com antes e depois",
              any(f["rule"] == "UI-INTERACTION" for f in pr.findings) and pr.interactions and not pr.interactions[0]["ok"]
              and pr.interactions[0].get("before") and pr.interactions[0].get("after"), pr.interactions)
        pr = run("drag_ok", 1440, inter=DRAG)
        check("arrastar implementado: a interacao passa e nao ha achado", pr.interactions and pr.interactions[0]["ok"] and not pr.findings,
              (pr.interactions, [f["message"] for f in pr.findings]))

        pr = run("clipped_bad", 1440)
        f = pr.findings[0]
        p = os.path.join(work, "clipped_bad-1440", f["shot"]["path"])
        check("cada achado tem captura recortada com hash", os.path.exists(p) and up.sha256(p) == f["shot"]["sha256"])
        pr = run("target_bad", 1440)
        f = [x for x in pr.findings if x["rule"] == "UI-TARGET"][0]
        check("achados iguais sao agrupados (2 icones pequenos = 1 achado x2)", f["count"] == 2, f)

    # ponta a ponta pela CLI: relatorio no schema, capturas conferiveis, adulteracao acusada
    routes = os.path.join(work, "routes.json")
    with open(routes, "w", encoding="utf-8") as fh:
        json.dump({"base": BASE, "routes": [{"name": "pills", "path": "drag_bad.html", "interactions": DRAG}],
                   "ignore": [{"rule": "UI-DEAD", "selector": "pill", "reason": "fixture: pilula sem acao"}]}, fh)
    out = os.path.join(work, "e2e")
    rc = up.main(["run", "--routes", routes, "--out", out, "--widths", "375,1440", "--quiet"])
    with open(os.path.join(out, "report.json"), encoding="utf-8") as fh:
        rep = json.load(fh)
    check("CLI: sai 1 quando ha achado medium ou pior (padrao --fail-on medium)", rc == 1)
    try:
        import jsonschema
        with open(os.path.join(HERE, "ui-probe-report.schema.v0.1.json"), encoding="utf-8") as fh:
            errs = [e.message for e in jsonschema.Draft202012Validator(json.load(fh)).iter_errors(rep)]
        check("relatorio valido no schema", not errs, errs[:3])
    except ImportError:
        print("jsonschema ausente: schema nao conferido")
    check("relatorio: captura da pagina inteira por largura, mais o zoom", len(rep["shots"]) == 3, [s["width"] for s in rep["shots"]])
    check("relatorio: interacao declarada nas larguras pedidas", {i["width"] for i in rep["interactions"]} == {375, 1440})
    check("verify: provas intactas", up.verify_report(os.path.join(out, "report.json")) == [])
    with open(os.path.join(out, rep["shots"][0]["path"]), "ab") as fh:
        fh.write(b"x")
    probs = up.verify_report(os.path.join(out, "report.json"))
    check("verify: captura alterada depois do relatorio e acusada", len(probs) == 1 and "alterada" in probs[0], probs)
    check("verify pela CLI sai 1 com prova alterada", up.main(["verify", "--report", os.path.join(out, "report.json")]) == 1)

srv.shutdown()
shutil.rmtree(work, ignore_errors=True)
print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
