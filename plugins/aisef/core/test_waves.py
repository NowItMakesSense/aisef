#!/usr/bin/env python3
"""Testes das ondas automaticas (aisef_project.compute_waves e o subcomando waves)."""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_project as ap  # noqa: E402

fails = total = 0


def check(name, cond):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name)
    fails += not cond


def T(tid, deps=(), paths=None, par=True, status="ready", feature="FEAT-1", role="backend", shared=()):
    return {
        "task_id": tid, "feature_id": feature, "title": "Tarefa " + tid,
        "assigned_agent": {"agent_id": role + "-1", "agent_contract_version": 1, "role": role},
        "scope": {"included": ["x"], "excluded": [], "paths_allowed": ["src/%s/**" % tid] if paths is None else list(paths)},
        "dependencies": {"depends_on": list(deps), "parallelizable": par, "shared_resources": list(shared)},
        "state": {"status": status},
    }


def ids(res):
    return [[t["task_id"] for t in w["tasks"]] for w in res["waves"]]


def raises(tasks, **kw):
    try:
        ap.compute_waves(tasks, **kw)
    except ap.WaveError as e:
        return e
    return None


r = ap.compute_waves([T("T-1"), T("T-2", ["T-1"]), T("T-3", ["T-2"])])
check("cadeia simples: 3 ondas de 1 tarefa", ids(r) == [["T-1"], ["T-2"], ["T-3"]] and not r["deferred"])

r = ap.compute_waves([T("T-1"), T("T-2", ["T-1"]), T("T-3", ["T-1"]), T("T-4", ["T-2", "T-3"])])
check("diamante: T-1 | T-2,T-3 em paralelo | T-4", ids(r) == [["T-1"], ["T-2", "T-3"], ["T-4"]])

r = ap.compute_waves([T("T-1"), T("T-2"), T("T-3")])
check("paralelas sem conflito: uma onda so", ids(r) == [["T-1", "T-2", "T-3"]] and not r["deferred"])

r = ap.compute_waves([T("T-1", paths=["src/api/**"]), T("T-2", paths=["src/api/users.py"]), T("T-3", paths=["web/**"])])
check("conflito de paths: T-2 vai para a onda 2, com motivo",
      ids(r) == [["T-1", "T-3"], ["T-2"]] and r["deferred"][0]["task"] == "T-2" and r["deferred"][0]["wave"] == 1
      and "T-1" in r["deferred"][0]["reason"] and "src/api" in r["deferred"][0]["reason"])

r = ap.compute_waves([T("T-1"), T("T-2", par=False), T("T-3")])
check("parallelizable=false vai sozinha na sua onda", ids(r) == [["T-1", "T-3"], ["T-2"]] and any(d["task"] == "T-2" for d in r["deferred"]))
r = ap.compute_waves([T("T-1", par=False), T("T-2"), T("T-3")])
check("tarefa solo primeira da fila tambem fica sozinha", ids(r) == [["T-1"], ["T-2", "T-3"]])

e = raises([T("T-1", ["T-3"]), T("T-2", ["T-1"]), T("T-3", ["T-2"]), T("T-4")])
check("ciclo: erro com os ids envolvidos", e is not None and e.ids == ["T-1", "T-2", "T-3"] and "ciclo" in str(e))
e = raises([T("T-1", ["T-9"])])
check("dependencia inexistente: erro com os ids", e is not None and e.ids == ["T-1", "T-9"] and "T-9" in str(e))

r = ap.compute_waves([T("T-1", status="completed"), T("T-2", status="validated"), T("T-3", ["T-1", "T-2"])])
check("concluidas/validadas contam como satisfeitas: T-3 na onda 1", ids(r) == [["T-3"]] and r["satisfied"] == ["T-1", "T-2"])

r = ap.compute_waves([T("T-1", status="cancelled"), T("T-2", status="blocked"), T("T-3", ["T-1"]), T("T-4", ["T-3"]), T("T-5")])
check("canceladas/bloqueadas ficam fora com motivo; dependentes ficam sem onda",
      ids(r) == [["T-5"]] and [x["task"] for x in r["excluded"]] == ["T-1", "T-2"]
      and sorted((d["task"], d["wave"]) for d in r["deferred"]) == [("T-3", None), ("T-4", None)])

mixed = [T("T-1", feature="FEAT-1"), T("T-2", feature="FEAT-2"), T("T-3", ["T-1"], feature="FEAT-2")]
check("sem filtro: todas as features", ids(ap.compute_waves(mixed)) == [["T-1", "T-2"], ["T-3"]])
check("filtro por feature: so FEAT-2 (T-3 depende de T-1 de outra feature ainda nao concluida e fica sem onda)",
      ids(ap.compute_waves(mixed, feature="FEAT-2")) == [["T-2"]])
mixed[0]["state"]["status"] = "completed"
check("filtro por feature: dependencia concluida em outra feature conta como satisfeita",
      ids(ap.compute_waves(mixed, feature="FEAT-2")) == [["T-2", "T-3"]])

check("heuristica: literais distintos nao conflitam, diretorio contem arquivo, prefixo de curinga conflita",
      not ap.paths_overlap("src/a.py", "src/ab.py") and ap.paths_overlap("src", "src/a.py") and ap.paths_overlap("src/api/*.py", "src/api/**/x.py")
      and not ap.paths_overlap("src/api/u*.py", "src/api/o*.py") and ap.paths_overlap("**", "x/y") and ap.paths_overlap("./src/a/", "src\\a\\b.py"))
r = ap.compute_waves([T("T-1", paths=[]), T("T-2")])
check("sem paths declarados: conflito (conservador)", ids(r) == [["T-1"], ["T-2"]])
r = ap.compute_waves([T("T-1", shared=["db"]), T("T-2", shared=["db"])])
check("recurso compartilhado: conflito", ids(r) == [["T-1"], ["T-2"]] and "db" in r["deferred"][0]["reason"])

# CLI
tmp = tempfile.mkdtemp()
os.makedirs(os.path.join(tmp, ".aisef", "contracts", "tasks"))
for t in (T("T-1"), T("T-2", ["T-1"])):
    with open(os.path.join(tmp, ".aisef", "contracts", "tasks", t["task_id"] + ".json"), "w", encoding="utf-8") as fh:
        json.dump(t, fh)
cmd = [sys.executable, "-I", os.path.join(HERE, "aisef_project.py"), "waves", "--project", tmp]
p = subprocess.run(cmd + ["--json"], capture_output=True, text=True)
j = json.loads(p.stdout) if p.returncode == 0 else {}
check("CLI --json: ondas, deferred e excluded", p.returncode == 0 and [w["wave"] for w in j["waves"]] == [1, 2] and j["deferred"] == [] and j["excluded"] == [])
p = subprocess.run(cmd, capture_output=True, text=True)
check("CLI humano: ondas numeradas", p.returncode == 0 and "Onda 1" in p.stdout and "Onda 2" in p.stdout and "T-2 [backend]" in p.stdout)
with open(os.path.join(tmp, ".aisef", "contracts", "tasks", "T-3.json"), "w", encoding="utf-8") as fh:
    json.dump(T("T-3", ["T-404"]), fh)
p = subprocess.run(cmd, capture_output=True, text=True)
check("CLI: dependencia inexistente sai com codigo != 0 e cita os ids", p.returncode != 0 and "T-404" in p.stdout and "T-3" in p.stdout)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
