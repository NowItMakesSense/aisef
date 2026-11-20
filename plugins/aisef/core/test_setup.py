#!/usr/bin/env python3
"""Testes do setup em lote (C-03): plano, aplicar tudo numa decisao, desmarcar itens, idempotencia e docs sem
sobrescrever o que o usuario ja tinha."""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_project as ap  # noqa: E402
import aisef_setup as su  # noqa: E402
import audit_chain  # noqa: E402

fails = total = 0


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)))
    fails += not cond


def log(p):
    return audit_chain.read_log_dir(os.path.join(p, ".aisef", "audit"))


proj = os.path.join(work, "proj")
os.makedirs(proj)
with open(os.path.join(proj, "AGENTS.md"), "w", encoding="utf-8") as fh:
    fh.write("# Regras do time\n\nUse tabs.\n")
ap.init(proj, "PRJ-SETUP")
pl = su.plan(proj)
import aisef_env  # noqa: E402
SANDBOX = aisef_env.sandbox_status(proj)["supported"] and not aisef_env.sandbox_status(proj)["enabled"]
check("plano traz os itens num projeto novo (sandbox so onde ele existe)",
      set(pl) == set(su.ITEMS) - (set() if SANDBOX else {"sandbox"}), pl)
check("plano de agentes = os drafts do nucleo", "implementer" in pl["agents"] and "qa" not in pl["agents"], pl["agents"])
check("plano nao grava nada", not os.path.exists(os.path.join(proj, ".claude", "settings.json"))
      and "AISEF" not in open(os.path.join(proj, "AGENTS.md"), encoding="utf-8").read())

n0 = len(log(proj))
done = su.apply(proj, only=("agents", "settings", "docs"), roles=None)
check("aplica so os itens marcados (practices desmarcado)", set(done) == {"agents", "settings", "docs"}, done)
check("agentes ativos", all(json.load(open(os.path.join(proj, ".aisef", "contracts", "agents", r + ".json"), encoding="utf-8"))
                            ["status"] == "active" for r in pl["agents"]))
check("regras nativas gravadas", os.path.isfile(os.path.join(proj, ".claude", "settings.json")))
agents_md = open(os.path.join(proj, "AGENTS.md"), encoding="utf-8").read()
check("AGENTS.md: secao acrescentada sem apagar a do time", agents_md.startswith("# Regras do time\n\nUse tabs.\n")
      and "## AISEF" in agents_md, agents_md[:200])
check("CLAUDE.md criado com a linha", su.CLAUDE_LINE in open(os.path.join(proj, "CLAUDE.md"), encoding="utf-8").read())
last = log(proj)[-1]
check("uma decisao do usuario resume o setup", last["event_type"] == "decision_recorded" and last["actor"]["type"] == "user"
      and set(last["data"]["setup"]) == {"agents", "settings", "docs"}, last)
check("practices continua pendente no plano", set(su.plan(proj)) == {"practices"} | ({"sandbox"} if SANDBOX else set()),
      su.plan(proj))
done = su.apply(proj)
check("depois aplica o que faltou (practices)", set(done) == {"practices"} | ({"sandbox"} if SANDBOX else set()) and
      os.path.isdir(os.path.join(proj, ".claude", "rules", "aisef")), done)
n1 = len(log(proj))
check("segunda vez: nada a fazer, nenhum evento", su.apply(proj) == {} and len(log(proj)) == n1 and su.plan(proj) == {})
check("AGENTS.md nao duplica a secao", open(os.path.join(proj, "AGENTS.md"), encoding="utf-8").read().count("## AISEF") == 1)

p2 = os.path.join(work, "p2")
os.makedirs(p2)
ap.init(p2, "PRJ-SETUP2")
su.apply(p2, only=("agents",), roles=["implementer", "validator"])
st = {r: json.load(open(os.path.join(p2, ".aisef", "contracts", "agents", r + ".json"), encoding="utf-8"))["status"]
      for r in ("implementer", "validator", "backend")}
check("--roles limita os agentes ativados", st == {"implementer": "active", "validator": "active", "backend": "draft"}, st)
check("CLI: item desconhecido sai 2", su.main(["--project", p2, "--only", "tudo"]) == 2)
check("CLI: sem init sai 2", su.main(["--project", work]) == 2)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
