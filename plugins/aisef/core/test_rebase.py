#!/usr/bin/env python3
"""F-07: check com correcao sugerida e rebase-req. Um requisito muda; o check acusa as versoes divergentes com o
comando de correcao; rodar so os comandos sugeridos leva o projeto de volta a 0 erros."""
import copy
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_new as an  # noqa: E402
import aisef_project as ap  # noqa: E402
import audit_chain  # noqa: E402
import check_project as cp  # noqa: E402
import make_demo_project as demo  # noqa: E402

fails = total = 0
POL = os.path.join(HERE, "permission-policy.v0.1.json")
DEF = os.path.join(HERE, "orchestration-defaults.v0.1.json")


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)[:600]))
    fails += not cond


def report(proj):
    return cp.check(proj, policy_path=POL, defaults_path=DEF)


def errors(rep):
    return sorted({f["rule"] for f in rep.findings if f["severity"] == "error"})


proj = os.path.join(work, "proj")
os.makedirs(proj)
ap.init(proj, "PRJ-REB")
ap.activate_agents(proj)
SPEC = {"solution": "Cupom percentual no total do carrinho", "user_stories": ["Como cliente quero aplicar um cupom"],
        "test_seams": ["total()"]}
an.cmd_feature(proj, {"id": "FEAT-010", "title": "Cupom", "objective": "Dar desconto no total do carrinho por cupom percentual", "problem": "A loja nao tem promocoes",
                      "requirements": {"REQ-100": "Aplicar cupom de 1% a 50%", "REQ-101": "Recusar cupom invalido com erro"},
                      "scope_in": ["cupom"], "spec": SPEC,
                      "tasks": [{"id": "T-010", "title": "aplicar cupom", "reqs": ["REQ-100"], "criteria": {"AC-10": "testes"},
                                 "paths": ["src/cupom.py"]},
                                {"id": "T-011", "title": "recusar cupom invalido", "reqs": ["REQ-101"],
                                 "criteria": {"AC-11": "testes"}, "paths": ["src/erros.py"]}]})
check("projeto de partida sem erro", errors(report(proj)) == [], errors(report(proj)))

# o usuario muda REQ-101 (nova versao do Feature Contract)
fpath = os.path.join(proj, ".aisef", "contracts", "features", "FEAT-010.json")
f = json.load(open(fpath, encoding="utf-8"))
r = next(x for x in f["requirements"] if x["id"] == "REQ-101")
r["version"], r["statement"] = 2, "Recusar cupom invalido ou vencido com erro"
r["history"].append({"version": 2, "statement": r["statement"], "author": "user", "justification": "vencimento",
                     "changed_at": ap.now_iso()})
f["contract_version"] = 2
for x in f["rtm"]:
    if x["requirement_id"] == "REQ-101":
        x["requirement_version"] = 2
ap.write_json(fpath, f)

rep = report(proj)
errs = errors(rep)
check("check acusa as versoes divergentes", {"TASK-REQ-VERSION", "PLAN-FEATURE-VERSION", "RTM-TASK-NOT-LINKED"} <= set(errs), errs)
version_findings = [x for x in rep.findings if x["rule"] in ("TASK-REQ-VERSION", "PLAN-FEATURE-VERSION", "RTM-TASK-NOT-LINKED")]
check("cada achado de versao traz a correcao com o comando", version_findings and all(
    "rebase-req" in (x.get("fix") or {}).get("cmd", "") and "FEAT-010" in x["fix"]["cmd"] for x in version_findings),
    version_findings)
cmds = rep.fixes(HERE)
check("fixes() devolve um comando so, sem repeticao, com o CORE real", len(cmds) == 1 and HERE in cmds[0], cmds)

lines, blocked = an.cmd_rebase(proj, "FEAT-010", dry_run=True)
check("dry-run mostra e nao grava", lines and json.load(open(os.path.join(proj, ".aisef", "contracts", "tasks", "T-011.json"),
                                                       encoding="utf-8"))["contract_version"] == 1)
n_events = len(audit_chain.read_log_dir(os.path.join(proj, ".aisef", "audit")))
check("rodar o comando sugerido sai 0", an.main(["rebase-req", "--project", proj, "--feature", "FEAT-010"]) == 0)
check("so com o comando sugerido o projeto volta a 0 erros", errors(report(proj)) == [], errors(report(proj)))
t10 = json.load(open(os.path.join(proj, ".aisef", "contracts", "tasks", "T-010.json"), encoding="utf-8"))
t11 = json.load(open(os.path.join(proj, ".aisef", "contracts", "tasks", "T-011.json"), encoding="utf-8"))
check("tarefa do requisito que mudou ganha nova versao", t11["contract_version"] == 2
      and t11["requirements"]["requirement_ids"] == [{"id": "REQ-101", "version": 2}] and t11["feature_contract_version"] == 2, t11)
check("tarefa nao afetada so acerta a base da feature", t10["contract_version"] == 1 and t10["feature_contract_version"] == 2)
log = audit_chain.read_log_dir(os.path.join(proj, ".aisef", "audit"))
check("registra um contract_changed", len(log) == n_events + 1 and log[-1]["event_type"] == "contract_changed"
      and "T-011 v2" in log[-1]["summary"], log[-1])
check("segunda vez: nada a atualizar", an.cmd_rebase(proj, "FEAT-010") == ([], []))

# tarefa ja iniciada nao e reescrita: reabertura
tp = os.path.join(proj, ".aisef", "contracts", "tasks", "T-010.json")
t10["state"]["status"] = "in_progress"
ap.write_json(tp, t10)
f = json.load(open(fpath, encoding="utf-8"))
r = next(x for x in f["requirements"] if x["id"] == "REQ-100")
r["version"] = 2
r["history"].append({"version": 2, "statement": r["statement"], "author": "user", "justification": "x", "changed_at": ap.now_iso()})
f["contract_version"] = 3
ap.write_json(fpath, f)
lines, blocked = an.cmd_rebase(proj, "FEAT-010", dry_run=True)
check("tarefa iniciada com requisito antigo fica bloqueada e pede reabertura", any("T-010" in b and "reabra" in b for b in blocked), blocked)
check("as outras tarefas ainda sao atualizadas", any("T-011" in x for x in lines), lines)
check("CLI sai 1 quando algo fica bloqueado", an.main(["rebase-req", "--project", proj, "--feature", "FEAT-010", "--dry-run"]) == 1)

# blueprint: demo (dry-run, sem gravar)
dp = os.path.join(work, "demo")
demo.make(os.path.join(dp, ".aisef"))
with open(os.path.join(dp, ".aisef", "config.json"), "w", encoding="utf-8") as fh:
    json.dump({"project_id": "PRJ-1", "schema_version": "0.1.0"}, fh)
dfp = os.path.join(dp, ".aisef", "contracts", "features", "FEAT-001.json")
df = json.load(open(dfp, encoding="utf-8"))
df["contract_version"] = 2
ap.write_json(dfp, df)
pl = an.rebase_plan(dp, "FEAT-001")
check("blueprint que nao cita requisito que mudou: so acerta a base", [x["blueprint"]["blueprint_id"] for x in pl["blueprints"]] == ["BP-001"]
      and not pl["blocked"], pl["blocked"])
df2 = copy.deepcopy(df)
r = df2["requirements"][2]
r["version"] = 2
r["history"].append({"version": 2, "statement": r["statement"], "author": "user", "justification": "x", "changed_at": ap.now_iso()})
ap.write_json(dfp, df2)
pl = an.rebase_plan(dp, "FEAT-001")
bp_cites = r["id"] in json.dumps(json.load(open(os.path.join(dp, ".aisef", "blueprints", "BP-001.json"), encoding="utf-8")))
check("blueprint que cita o requisito que mudou: bloqueado, pede nova versao",
      (any("BP-001" in b for b in pl["blocked"]) and not pl["blueprints"]) if bp_cites else bool(pl["blueprints"]), pl["blocked"])

# next (F-07): a tarefa nao e despachada com requisito antigo
import aisef_next as nx  # noqa: E402
apr = os.path.join(proj, ".aisef", "approvals", "APR-001.json")
ap.write_json(apr, dict(json.load(open(apr, encoding="utf-8")), status="approved"))  # plano aprovado: nada mais bloqueia
res = nx.compute_next(proj, git_state={"current": None, "branches": None})
rc = [a for a in res["actions"] if a["kind"] == "requirement_changed"]
check("next: requirement_changed para a tarefa iniciada vira decisao (reabrir)",
      any(a["task_ids"] == ["T-010"] and a["started"] and "reabra" in a["hint"] for a in rc), rc)
check("next: tarefa com requisito antigo nao entra no dispatch", not any(
    t["task_id"] == "T-010" for a in res["actions"] if a["kind"] == "dispatch" for t in a["tasks"]))
t10["state"]["status"] = "ready"
ap.write_json(tp, t10)
res = nx.compute_next(proj, git_state={"current": None, "branches": None})
rc = [a for a in res["actions"] if a["kind"] == "requirement_changed"]
check("next: tarefa nao iniciada recebe o comando rebase-req (automatico)", rc and not rc[0]["started"]
      and "rebase-req" in rc[0]["cmd"] and "FEAT-010" in rc[0]["cmd"], rc)
check("next: o texto mostra a acao", "requirement_changed T-010" in nx.format_next(res))

# correcoes de outras regras
check("VAL-NO-VALIDATOR traz o comando do validator", "--roles validator" in cp.FIX_HINTS["VAL-NO-VALIDATOR"]["cmd"])
for rule in ("AGENT-PATH-CEILING", "DESIGN-MISSING", "STATE-UNAPPROVED-PLAN", "STATE-NO-START-EVENT", "STATE-NO-REPORT",
             "STATE-NO-VALIDATION", "STATE-NO-COMPLETE-EVENT"):
    check("%s tem correcao" % rule, rule in cp.FIX_HINTS)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
