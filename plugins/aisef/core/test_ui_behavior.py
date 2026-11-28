#!/usr/bin/env python3
"""Testes da V-06: a tarefa de UI declara como se comporta (`ui_behavior`) e so e entregue com a sonda de UI anexada e
limpa. Cobre o schema, o gerador (criterio da sonda), o pacote de contexto, a sonda lendo o contrato e as regras
UI-BEHAVIOR-MISSING, UI-PROBE-MISSING e UI-PROBE-DIRTY."""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_context  # noqa: E402
import aisef_new  # noqa: E402
import aisef_project as ap  # noqa: E402
import check_project as cp  # noqa: E402
import check_rules_5 as r5  # noqa: E402
import ui_probe_io  # noqa: E402

fails = total = 0
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


def check(name, cond, extra=None):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond or extra is None else "  -> %s" % (extra,)))
    fails += not cond


UB = {"base_url": "http://127.0.0.1:5173",
      "routes": [{"name": "reset", "path": "/reset", "wait_for": "form"}],
      "widths": {"<=480": "formulario em uma coluna, botao com largura total", ">=481": "cartao centralizado de 420 px"},
      "overflow": [{"target": ".erros", "strategy": "wrap"}],
      "interactions": [{"target": ".senha-toggle", "gesture": "click", "expect": "change"},
                       {"target": ".dicas", "gesture": "swipe", "route": "reset", "widths": [375]}],
      "states": ["empty", "loading", "error"]}


def path(*p):
    return os.path.join(proj, ".aisef", *p)


def load(rel):
    with open(path(rel), encoding="utf-8") as fh:
        return json.load(fh)


try:
    proj = os.path.join(work, "p")
    os.makedirs(proj)
    ap.init(proj, "PRJ-U", "ui", "dev")
    ap.activate_agents(proj)
    b = json.loads(json.dumps(aisef_new.EXAMPLES["feature"]))
    b["tasks"][1]["ui_behavior"] = UB
    aisef_new.cmd_feature(proj, b)
    t11, t10 = load("contracts/tasks/T-011.json"), load("contracts/tasks/T-010.json")

    # ------------------------------------------------------------ contrato e gerador
    check("contrato da fatia de UI leva a ui_behavior do brief", t11.get("ui_behavior") == UB)
    crit = {c["id"]: c for c in t11["acceptance_criteria"]}
    check("fatia de UI com ui_behavior ganha o criterio da sonda", "AC-T-011-UIPROBE" in crit
          and "ui_probe.py run --project . --task T-011" in crit["AC-T-011-UIPROBE"]["verification"]["command"])
    check("fatia sem UI nao ganha criterio de sonda", not [c for c in t10["acceptance_criteria"] if c["id"].endswith("UIPROBE")])
    schema_errs = [f for f in cp.check(path(), HERE).findings if f["rule"] == "SCHEMA"]
    check("contrato com ui_behavior passa no schema", not schema_errs, schema_errs[:2])
    try:
        import jsonschema
        with open(os.path.join(HERE, "task-contract.schema.v0.1.json"), encoding="utf-8") as fh:
            val = jsonschema.Draft202012Validator(json.load(fh))
        bad = dict(t11, ui_behavior=dict(UB, interactions=[{"target": "x", "gesture": "pinch"}]))
        check("schema recusa gesto desconhecido", list(val.iter_errors(bad)) != [])
        bad = dict(t11, ui_behavior={k: v for k, v in UB.items() if k != "states"})
        check("schema exige os estados declarados (mesmo que [])", list(val.iter_errors(bad)) != [])
    except ImportError:
        print("jsonschema ausente: recusas do schema nao conferidas")

    # ------------------------------------------------------------ pacote de contexto
    pk = aisef_context.build_pack(proj, "T-011", graph=False)
    ui = pk["mandatory"].get("ui") or {}
    check("pacote da fatia de UI traz o comportamento e o comando da sonda",
          ui.get("behavior") == UB and "ui_probe.py run --project . --task T-011" in ui.get("probe", ""))
    check("pacote de tarefa sem UI nao traz bloco de UI", aisef_context.build_pack(proj, "T-010", graph=False)["mandatory"].get("ui") is None)
    t11b = dict(t11)
    t11b.pop("ui_behavior")
    ap.write_json(path("contracts/tasks/T-011.json"), t11b)
    pk = aisef_context.build_pack(proj, "T-011", graph=False)
    check("tarefa de UI sem ui_behavior: o pacote avisa para declarar antes de codar",
          any("sem ui_behavior" in w for w in pk["warnings"]), pk["warnings"])
    ap.write_json(path("contracts/tasks/T-011.json"), t11)

    # ------------------------------------------------------------ a sonda le o contrato
    routes, ignore, out = ui_probe_io.routes_from_task(proj, "T-011")
    check("sonda --task: rota com a URL da base e os gestos daquela rota",
          routes[0]["url"] == "http://127.0.0.1:5173/reset" and len(routes[0]["interactions"]) == 2
          and out.replace("\\", "/").endswith(".aisef/reports/ui/T-011/probe"))
    with open(path("ui-probe.ignore.json"), "w", encoding="utf-8") as fh:
        json.dump({"ignore": [{"rule": "UI-TARGET", "selector": ".tl-bar", "reason": "tamanho representa dado"}]}, fh)
    check("sonda --task: le as excecoes de .aisef/ui-probe.ignore.json", ui_probe_io.routes_from_task(proj, "T-011", "http://x.test/")[1][0]["reason"]
          == "tamanho representa dado")
    try:
        ui_probe_io.routes_from_task(proj, "T-010")
        check("sonda --task em tarefa sem ui_behavior recusa", False)
    except SystemExit as e:
        check("sonda --task em tarefa sem ui_behavior recusa com o que falta", "ui_behavior" in str(e))

    # ------------------------------------------------------------ regras
    def rules(tasks, reports):
        rep = cp.Report()
        r5.rules_ui({"project": path(), "tasks": tasks, "reports": reports, "rep": rep})
        return [(f["rule"], f["message"]) for f in rep.findings]

    def task(status, ub=True):
        t = json.loads(json.dumps(t11))
        t["state"]["status"] = status
        if not ub:
            t.pop("ui_behavior")
        return {"T-011": t}

    def probe(findings=(), routes=("reset",), gestures=((".senha-toggle", "click"), (".dicas", "swipe"))):
        d = os.path.join(path("reports", "ui", "T-011", "probe"))
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "report.json"), "w", encoding="utf-8") as fh:
            json.dump({"routes": [{"name": n, "url": "x"} for n in routes], "findings": list(findings),
                       "interactions": [{"target": t, "gesture": g, "ok": True} for t, g in gestures]}, fh)
        return [{"report_id": "RPT-T-011-1", "task_id": "T-011",
                 "evidence": [{"id": "EV-1", "type": "ui_probe", "ref": ".aisef/reports/ui/T-011/probe/report.json", "secrets_redacted": True}]}]

    got = rules(task("ready", ub=False), [])
    check("UI aberta sem ui_behavior: UI-BEHAVIOR-MISSING (aviso)", [g[0] for g in got] == ["UI-BEHAVIOR-MISSING"], got)
    check("UI ja concluida sem ui_behavior (de antes do processo): nada", rules(task("completed", ub=False), []) == [])
    check("UI declarada e ainda em andamento: sem cobranca de sonda", rules(task("in_progress"), []) == [])
    got = rules(task("executed"), [])
    check("UI entregue sem a sonda no relatorio: UI-PROBE-MISSING", [g[0] for g in got] == ["UI-PROBE-MISSING"], got)
    shutil.rmtree(path("reports", "ui"), ignore_errors=True)
    reps = probe()
    os.remove(path("reports", "ui", "T-011", "probe", "report.json"))
    got = rules(task("executed"), reps)
    check("relatorio cita a sonda, mas o arquivo nao existe: UI-PROBE-MISSING", got and got[0][0] == "UI-PROBE-MISSING" and "nao existe" in got[0][1], got)
    check("sonda limpa, rotas e gestos cobertos: nada", rules(task("executed"), probe()) == [])
    got = rules(task("validated"), probe(findings=[{"rule": "UI-REFLOW", "severity": "high", "selector": ".tabela", "width": 375}]))
    check("sonda com achado high: UI-PROBE-DIRTY citando a regra e a largura", got and got[0][0] == "UI-PROBE-DIRTY" and "UI-REFLOW" in got[0][1] and "375" in got[0][1], got)
    check("achado low nao suja a entrega", rules(task("executed"), probe(findings=[{"rule": "UI-CLIPPED", "severity": "low"}])) == [])
    got = rules(task("executed"), probe(routes=("outra",)))
    check("sonda que nao passou pela rota declarada: UI-PROBE-MISSING", got and "reset" in got[0][1], got)
    got = rules(task("executed"), probe(gestures=((".senha-toggle", "click"),)))
    check("gesto declarado sem teste na sonda: UI-PROBE-MISSING", got and "swipe" in got[0][1], got)

    # ------------------------------------------------------------ agentes e documentacao
    for name in ("frontend", "implementer"):
        with open(os.path.join(ROOT, "plugins", "aisef", "agents", name + ".md"), encoding="utf-8") as fh:
            md = fh.read()
        check("agente %s gerado com o processo de UI (declarar, regras, provar com a sonda)" % name,
              "## UI: responsividade" in md and "ui_probe.py run --project . --task" in md and "UI-PROBE-MISSING" in md)
    with open(os.path.join(ROOT, "plugins", "aisef", "agents", "backend.md"), encoding="utf-8") as fh:
        check("agente de backend nao recebe o bloco de UI", "## UI: responsividade" not in fh.read())
finally:
    shutil.rmtree(work, ignore_errors=True)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
