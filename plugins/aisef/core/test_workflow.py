#!/usr/bin/env python3
"""L-03: o workflow declarativo e valido, coerente e e a fonte que o next, o guia, a triagem, o aisef_new e o check
usam. Mudar o fluxo e mudar o JSON: o teste confere que os leitores seguem o arquivo."""
import copy
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_guide as gd  # noqa: E402
import aisef_next as nx  # noqa: E402
import aisef_triage as tr  # noqa: E402
import aisef_workflow as wf  # noqa: E402

fails = total = 0


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)[:500]))
    fails += not cond


check("workflow do plugin: schema e coerencia sem problemas", wf.check() == [], wf.check())
check("next le estados, ordem e terminais do workflow", nx.EVENT_STATE == wf.event_state() and nx.RANK == wf.rank()
      and tuple(nx.DONE) == wf.terminal())
check("guia le os passos das fases do workflow", gd.STEPS == wf.steps())
check("fases na ordem do fluxo", wf.phases() == ["discovery", "specify", "approve_plan", "execute", "review", "decide", "done"])
check("todo tipo de pedido do Approval Center e um portao decidido pelo usuario",
      all(g["decided_by"] == "user" for g in wf.gates().values()) and "plan_approval" in wf.gates())
check("perfil desconhecido cai no team (comportamento anterior)", wf.profile("inexistente") == wf.profile("team"))
check("estado efetivo: contrato cancelado prevalece", nx.effective_state("cancelled", "executed") == "cancelled")
check("estado efetivo: log a frente do contrato", nx.effective_state("ready", "executed") == "executed")
check("triagem segue o perfil do workflow: team sugere lean", tr.apply_profile("lean", "team")[0] == "full")
check("triagem segue o perfil do workflow: regulated sem quick", tr.apply_profile("quick", "regulated")[0] == "lean")
check("triagem segue o perfil do workflow: solo usa lean", tr.apply_profile("lean", "solo") == ("lean", None))

# coerencia: um workflow quebrado e acusado
tmp = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))


def broken(mutate):
    doc = copy.deepcopy(wf.load())
    mutate(doc)
    p = os.path.join(tmp, "wf%d.json" % len(os.listdir(tmp)))
    json.dump(doc, open(p, "w", encoding="utf-8"))
    return wf.check(p)


check("evento levando a estado inexistente e acusado",
      any("estado" in x for x in broken(lambda d: d["events"]["task_executed"].update(state="feito"))))
check("evento que nao existe no log de auditoria e acusado",
      any("log de auditoria" in x for x in broken(lambda d: d["events"].update(task_dancou={"state": "ready", "recorded_by": ["agent"]}))))
check("tipo de pedido sem portao e acusado", any("sem portao" in x for x in broken(lambda d: d["gates"].pop("git_operation"))))
check("portao que nao e tipo de pedido e acusado", any("nao e tipo de pedido" in x for x in broken(
    lambda d: d["gates"].update(cafe={"decided_by": "user", "what": "x"}))))
check("fase com portao inexistente e acusada", any("portao" in x for x in broken(lambda d: d["phases"][0].update(gate="nada"))))
check("perfil a mais ou a menos que o config aceita e acusado", any("perfis" in x for x in broken(lambda d: d["profiles"].pop("solo"))))
check("schema: decisao de portao so do usuario", any("schema" in x for x in broken(
    lambda d: d["gates"]["plan_approval"].update(decided_by="orchestrator"))))
check("CLI check sai 0", wf.main(["check"]) == 0)
check("CLI show sai 0", wf.main(["show"]) == 0)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
