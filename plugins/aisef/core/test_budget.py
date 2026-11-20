#!/usr/bin/env python3
"""Orcamento e falta de progresso no modo continuo (L-01 + L-06): budget_exhausted, no_progress, stale_agent e a regra
BUDGET-RAISED. Sem modelo: o log e o usage.jsonl sao gravados direto."""
import datetime
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_budget as bg  # noqa: E402
import aisef_new as an  # noqa: E402
import aisef_next as nx  # noqa: E402
import aisef_project as ap  # noqa: E402
import check_project as cp  # noqa: E402

fails = total = 0
NOGIT = {"current": None, "branches": None}


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)[:700]))
    fails += not cond


# ------------------------------------------------------------------ funcoes puras
check("limites do projeto: padroes do plugin", bg.project_limits({})["max_attempts"] == 30)
check("config.json sobe ou baixa o projeto", bg.project_limits({"budget": {"max_attempts": 50}})["max_attempts"] == 50)
check("feature so baixa", bg.feature_limits({}, {"budget": {"max_attempts": 5}})["max_attempts"] == 5
      and bg.feature_limits({}, {"budget": {"max_attempts": 99}})["max_attempts"] == 30)
check("raised acusa o que a feature tenta subir", bg.raised({}, {"budget": {"max_attempts": 99, "max_minutes": 10}}) == ["max_attempts"])
e1 = {"task_id": "T-1", "event_type": "task_rejected", "summary": "T-1 reprovada: AC-1 falhou na linha 12"}
e2 = {"task_id": "T-1", "event_type": "task_rejected", "summary": "T-1 reprovada: AC-1 falhou na linha 40"}
e3 = {"task_id": "T-1", "event_type": "task_rejected", "summary": "T-1 reprovada: AC-2 falhou"}
check("assinatura ignora numeros (linha, tempo)", bg.failure_signature(e1) == bg.failure_signature(e2))
check("assinatura muda quando o motivo muda", bg.failure_signature(e1) != bg.failure_signature(e3))
p1 = {"task_id": "T-1", "event_type": "task_rejected", "data": {"precheck": ["sem tdd_evidence"]}}
check("assinatura do precheck vem da lista de problemas", bg.failure_signature(p1) == bg.failure_signature(dict(p1, summary="x")))
check("no_progress: duas iguais seguidas", bg.no_progress([e1, e2], "T-1", 2))
check("no_progress: a ultima diferente nao para", not bg.no_progress([e1, e3], "T-1", 2))
check("no_progress: uma so nao basta", not bg.no_progress([e1], "T-1", 2))

# ------------------------------------------------------------------ next com um projeto real
proj = os.path.join(work, "proj")
os.makedirs(proj)
ap.init(proj, "PRJ-BUD")
ap.activate_agents(proj)
an.cmd_feature(proj, {"id": "FEAT-020", "title": "Cupom", "objective": "Dar desconto no total do carrinho por cupom",
                      "problem": "A loja nao tem promocoes", "requirements": {"REQ-1": "Aplicar cupom", "REQ-2": "Recusar cupom invalido"},
                      "scope_in": ["cupom"],
                      "spec": {"solution": "Cupom percentual no total", "user_stories": ["Como cliente quero cupom"],
                               "test_seams": ["total()"]},
                      "tasks": [{"id": "T-1", "title": "aplicar o cupom no total", "reqs": ["REQ-1"], "criteria": {"AC-1": "testes"}, "paths": ["src/a.py"]},
                                {"id": "T-2", "title": "recusar cupom invalido", "reqs": ["REQ-2"], "criteria": {"AC-2": "testes"}, "paths": ["src/b.py"]}]})
apr = os.path.join(proj, ".aisef", "approvals", "APR-001.json")
ap.write_json(apr, dict(json.load(open(apr, encoding="utf-8")), status="approved"))
for tid in ("T-1", "T-2"):
    tp = os.path.join(proj, ".aisef", "contracts", "tasks", tid + ".json")
    t = json.load(open(tp, encoding="utf-8"))
    t["state"]["status"] = "ready"
    ap.write_json(tp, t)


def ev(etype, tid, actor=("orchestrator", "orchestrator"), **extra):
    ap.append(proj, dict({"event_type": etype, "actor": {"type": actor[0], "id": actor[1]}, "feature_id": "FEAT-020",
                          "task_id": tid, "summary": "%s %s" % (etype, tid)}, **extra))


def nxt(now=None):
    return nx.compute_next(proj, git_state=NOGIT, now=now)


r = nxt()
check("sem gasto: segue (sem stop_reason) e despacha", r["stop_reason"] is None and any(a["kind"] == "dispatch" for a in r["actions"]),
      r["stop_reason"])

# T-1 reprovada duas vezes pelo mesmo motivo -> no_progress so dela
for i in (1, 2):
    ev("delegation", "T-1")
    ev("task_executed", "T-1", ("agent", "implementer"))
    ev("task_rejected", "T-1", ("validator", "validator"), summary="T-1 reprovada: AC-1 falhou na linha %d" % (i * 10))
r = nxt()
npg = [a for a in r["actions"] if a.get("source") == "no_progress"]
check("no_progress: tarefa reprovada 2x pelo mesmo motivo para e nao e redespachada",
      npg and npg[0]["task_ids"] == ["T-1"] and not any(t["task_id"] == "T-1" for a in r["actions"] if a["kind"] == "dispatch"
                                                     for t in a["tasks"]), r["actions"])
check("no_progress: a outra tarefa da onda continua", any(t["task_id"] == "T-2" for a in r["actions"] if a["kind"] == "dispatch"
                                                       for t in a["tasks"]), r["actions"])

# T-2 delegada e parada ha muito tempo -> stale_agent
ev("delegation", "T-2")
later = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=90)
r = nxt(now=later)
st = [a for a in r["actions"] if a.get("source") == "stale_agent"]
check("stale_agent: em andamento acima do tempo limite vira decisao", st and st[0]["task_ids"] == ["T-2"], r["actions"])
check("stale_agent: antes do limite, so espera", not any(a.get("source") == "stale_agent" for a in nxt()["actions"]))

# orcamento: tempo e tentativas
r = nxt(now=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9))
check("budget_exhausted por tempo: o loop para logo depois de risco critico", r["stop_reason"] == "budget_exhausted"
      and r["actions"][0]["source"] == "budget_exhausted" and "minutes" in r["actions"][0]["title"], (r["stop_reason"], r["actions"][:1]))
cfg = ap.load_config(proj)
cfg["budget"] = {"max_attempts": 3}
ap.write_json(os.path.join(proj, ".aisef", "config.json"), cfg)
r = nxt()
check("budget_exhausted por tentativas (3 despachos, limite do config.json)", r["stop_reason"] == "budget_exhausted"
      and r["actions"][0]["used"]["attempts"] == 3, r["actions"][:1])
check("budget: nada e despachado", not any(a["kind"] == "dispatch" for a in r["actions"]))
cfg["budget"] = {"max_attempts": 100, "max_tokens": 1000}
ap.write_json(os.path.join(proj, ".aisef", "config.json"), cfg)
rdir = os.path.join(proj, ".aisef", "runtime")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "usage.jsonl"), "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"at": ap.now_iso(), "task_id": "T-1", "usage": {"input_tokens": 900, "output_tokens": 200}}) + "\n")
r = nxt()
check("budget_exhausted por tokens (usage.jsonl)", r["stop_reason"] == "budget_exhausted" and r["actions"][0]["used"]["tokens"] == 1100,
      r["actions"][:1])
check("texto do next mostra a decisao", "budget_exhausted" in nx.format_next(r))

# BUDGET-RAISED
cfg["budget"] = {}
ap.write_json(os.path.join(proj, ".aisef", "config.json"), cfg)
fpath = os.path.join(proj, ".aisef", "contracts", "features", "FEAT-020.json")
f = json.load(open(fpath, encoding="utf-8"))
f["budget"] = {"max_attempts": 500}
ap.write_json(fpath, f)
rep = cp.check(proj, policy_path=os.path.join(HERE, "permission-policy.v0.1.json"),
               defaults_path=os.path.join(HERE, "orchestration-defaults.v0.1.json"))
check("check: feature subindo o limite -> BUDGET-RAISED com correcao", any(
    x["rule"] == "BUDGET-RAISED" and x.get("fix") for x in rep.findings), [x["rule"] for x in rep.findings])
f["budget"] = {"max_attempts": 5}
ap.write_json(fpath, f)
rep = cp.check(proj, policy_path=os.path.join(HERE, "permission-policy.v0.1.json"))
bad = [x for x in rep.findings if x["rule"] == "BUDGET-RAISED" or (x["rule"] == "SCHEMA" and "features" in x["where"])]
check("check: feature baixando o limite e valida (schema e regra)", not bad, bad)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
