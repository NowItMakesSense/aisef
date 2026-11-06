#!/usr/bin/env python3
"""Testes dos geradores (aisef_new.py): brief curto -> documentos validos, aprovacao do plano refletida
no contrato, caminho rapido de manutencao, e tudo passando no check_project --strict."""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_new  # noqa: E402
import aisef_project as ap  # noqa: E402
import check_project as cp  # noqa: E402

POL = os.path.join(HERE, "permission-policy.v0.1.json")
DEF = os.path.join(HERE, "orchestration-defaults.v0.1.json")
fails = total = 0


def check(name, cond):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name)
    fails += not cond


def clean(project):
    r = cp.check(os.path.join(project, ".aisef"), HERE, POL, DEF)
    return [f for f in r.findings]


def load(project, rel):
    with open(os.path.join(project, ".aisef", rel), encoding="utf-8") as fh:
        return json.load(fh)


def expect_exit(fn):
    try:
        fn()
        return False
    except SystemExit:
        return True


proj = os.path.join(work, "p")
os.makedirs(proj)
ap.init(proj, "PRJ-G", "gerador", "dev")
ap.activate_agents(proj)

brief = json.loads(json.dumps(aisef_new.EXAMPLES["feature"]))
aisef_new.cmd_feature(proj, brief)
f = load(proj, "contracts/features/FEAT-002.json")
check("feature: contrato, 2 tarefas e pedido de plano gerados a partir do brief",
      os.path.exists(os.path.join(proj, ".aisef", "contracts", "tasks", "T-011.json"))
      and load(proj, "approvals/APR-001.json")["request_type"] == "plan_approval")
check("feature: RTM liga cada requisito a tarefa e criterio", {r["requirement_id"]: r["task_ids"] for r in f["rtm"]}
      == {"REQ-010": ["T-010"], "REQ-011": ["T-011"]})
check("feature: aguardando aprovacao do plano, tarefas em draft",
      f["state"]["status"] == "awaiting_plan_approval" and load(proj, "contracts/tasks/T-010.json")["state"]["status"] == "draft")
check("feature: projeto limpo no check_project", clean(proj) == [])

ap.decide(proj, "APR-001", "approve")
f = load(proj, "contracts/features/FEAT-002.json")
check("decide: plano aprovado vira approved_for_execution e tarefas ficam ready",
      f["approval"]["plan"]["approved_by"] == "user" and f["state"]["status"] == "approved_for_execution"
      and load(proj, "contracts/tasks/T-011.json")["state"]["status"] == "ready")

aisef_new.cmd_blueprint(proj, json.loads(json.dumps(aisef_new.EXAMPLES["blueprint"])))
bp = load(proj, "blueprints/BP-002.json")
check("blueprint: endpoints, entidade com segredo e migracao com rollback",
      len(bp["backend"]["endpoints"]) == 2 and bp["database"]["entities"][0]["fields"][1].get("secret") is True
      and bp["database"]["migrations"][0]["reversible"] is True)
check("blueprint: projeto limpo no check_project", clean(proj) == [])

bad = json.loads(json.dumps(aisef_new.EXAMPLES["feature"]))
bad.update(id="FEAT-003")
bad["tasks"][0]["reqs"] = ["REQ-404"]
check("brief com requisito inexistente e recusado sem gravar nada",
      expect_exit(lambda: aisef_new.cmd_feature(proj, bad))
      and not os.path.exists(os.path.join(proj, ".aisef", "contracts", "features", "FEAT-003.json")))
check("brief sem tarefa para um requisito e recusado (RTM obrigatoria)",
      expect_exit(lambda: aisef_new.cmd_feature(proj, dict(json.loads(json.dumps(aisef_new.EXAMPLES["feature"])), id="FEAT-004",
                                                          requirements={"REQ-010": "x" * 10, "REQ-099": "sem tarefa"}))))
check("contrato existente nao e sobrescrito", expect_exit(lambda: aisef_new.cmd_feature(proj, json.loads(json.dumps(aisef_new.EXAMPLES["feature"])))))

aisef_new.cmd_quick(proj, "Corrige typo no README", "texto errado", [], None)
check("quick: primeira vez cria FEAT-MAINT com pedido de plano", load(proj, "contracts/features/FEAT-MAINT.json")["state"]["status"] == "awaiting_plan_approval")
ap.decide(proj, "APR-002", "approve")
aisef_new.cmd_quick(proj, "Atualiza lib", "patch", ["requirements.txt"], "pytest -q")
t2 = load(proj, "contracts/tasks/T-MAINT-002.json")
check("quick: tarefas seguintes ja nascem ready, sem validador independente",
      t2["state"]["status"] == "ready" and t2["validation"]["independent_validator_required"] is False
      and t2["acceptance_criteria"][0]["verification"]["command"] == "pytest -q")
check("quick: FEAT-MAINT acumula as tarefas na RTM", load(proj, "contracts/features/FEAT-MAINT.json")["rtm"][0]["task_ids"]
      == ["T-MAINT-001", "T-MAINT-002"])
check("tudo limpo no check_project e log integro", clean(proj) == [] and not ap.verify(proj)[0])

shutil.rmtree(work, ignore_errors=True)
print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
