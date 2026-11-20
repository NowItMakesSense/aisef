#!/usr/bin/env python3
"""G-07: grafo do sistema consultavel (impact --req, impact --file, why --task) sobre o projeto de demonstracao."""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_sysgraph as g  # noqa: E402
import make_demo_project as demo  # noqa: E402

fails = total = 0


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)[:500]))
    fails += not cond


p = os.path.join(tempfile.mkdtemp(dir=os.environ.get("TMPDIR")), "p")
demo.make(os.path.join(p, ".aisef"))

r = g.impact_req(p, "REQ-001")
check("impact --req: tarefa, criterio e status", [t["task_id"] for t in r["tasks"]] == ["T-001"]
      and [c["id"] for c in r["criteria"]] == ["AC-1"] and r["tasks"][0]["status"] == "completed", r)
check("impact --req: arquivos do escopo e do relatorio", "src/auth/*" in r["files"] and "src/auth/jwt.py" in r["files"], r["files"])
check("impact --req: evidencias dos relatorios", any(e["report_id"] == "RPT-001" for e in r["evidence"]), r["evidence"])
check("impact --req: elementos do blueprint que citam o requisito",
      {(b["blueprint_id"], b["id"]) for b in r["blueprint_elements"]} >= {("BP-001", "C-API")}, r["blueprint_elements"])
try:
    g.impact_req(p, "REQ-999")
    ok = False
except SystemExit as e:
    ok = "REQ-999" in str(e)
check("impact --req: requisito inexistente e erro claro", ok)

f = g.impact_file(p, "src/auth/jwt.py")
check("impact --file: arquivo do relatorio aparece pela evidencia real",
      any(t["task_id"] == "T-001" and t["via"] == "relatorio" for t in f["tasks"]), f["tasks"])
check("impact --file: requisitos das tarefas que tocam o arquivo", "REQ-001" in [x["id"] for x in f["requirements"]], f)
check("impact --file: arquivo fora de qualquer escopo -> nada", g.impact_file(p, "docs/README.md")["tasks"] == [])
check("impact --file: aceita ./ e barra invertida", g.impact_file(p, ".\\src\\auth\\x.py")["tasks"] != [])

w = g.why_task(p, "T-001")
check("why --task: requisito com origem", w["requirements"][0]["id"] == "REQ-001" and w["requirements"][0]["origin"], w)
check("why --task: decisao e ADR da feature", any(d.get("id") == "ADR-001" for d in w["decisions"]) and "ADR-001" in w["adrs"], w)
check("why --task: blueprint vigente", w["blueprint"] and w["blueprint"]["blueprint_id"] == "BP-001", w["blueprint"])

for args in (["impact", "--project", p, "--req", "REQ-001"], ["impact", "--project", p, "--file", "src/auth/a.py", "--json"],
             ["why", "--project", p, "--task", "T-002"]):
    check("CLI %s sai 0" % " ".join(a for a in args if not a.startswith(p)), g.main(args) == 0)
try:
    g.main(["impact", "--project", p])
    ok = False
except SystemExit as e:
    ok = e.code == 2
check("CLI: impact sem --req nem --file e erro de uso", ok)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
