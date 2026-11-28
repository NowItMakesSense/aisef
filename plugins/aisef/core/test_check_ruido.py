#!/usr/bin/env python3
"""Testes da A-02: avisos do check que nao apontavam nada a fazer (vistos no HireMe).
- PAR-PATH-OVERLAP entre duas tarefas ja encerradas: elas nao rodam mais juntas;
- BP-NO-PK numa entidade que nao e tabela (arquivo com um token): `storage` diz onde ela fica."""
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

fails = total = 0


def check(name, cond, extra=None):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond or extra is None else "  -> %s" % (extra,)))
    fails += not cond


def rules():
    return [f["rule"] for f in cp.check(os.path.join(proj, ".aisef"), HERE).findings]


def rw(rel, fn):
    p = os.path.join(proj, ".aisef", rel)
    with open(p, encoding="utf-8") as fh:
        d = json.load(fh)
    fn(d)
    ap.write_json(p, d)


try:
    proj = os.path.join(work, "p")
    os.makedirs(proj)
    ap.init(proj, "PRJ-R", "ruido", "dev")
    ap.activate_agents(proj)
    b = json.loads(json.dumps(aisef_new.EXAMPLES["feature"]))
    for t in b["tasks"]:
        t.pop("depends_on", None)
        t["parallelizable"] = True
        t["paths"] = ["src/auth/*"]
    aisef_new.cmd_feature(proj, b)
    check("tarefas abertas e paralelas no mesmo caminho: PAR-PATH-OVERLAP", "PAR-PATH-OVERLAP" in rules())
    for tid in ("T-010", "T-011"):
        rw("contracts/tasks/%s.json" % tid, lambda d: d["state"].update(status="completed"))
    check("as duas ja encerradas: sem PAR-PATH-OVERLAP", "PAR-PATH-OVERLAP" not in rules())
    rw("contracts/tasks/T-011.json", lambda d: d["state"].update(status="ready"))
    check("uma ainda aberta: o aviso volta", "PAR-PATH-OVERLAP" in rules())

    bp = json.loads(json.dumps(aisef_new.EXAMPLES["blueprint"]))
    bp["entities"]["ENT-TOKEN"] = ["arquivo do token", "restricted", ["REQ-010"], [["token", "text", "secret"]]]
    aisef_new.cmd_blueprint(proj, bp)
    check("entidade sem chave primaria: BP-NO-PK", "BP-NO-PK" in rules())
    path = [f for f in os.listdir(os.path.join(proj, ".aisef", "blueprints")) if f.endswith(".json")][0]

    def mark(d):
        for e in d["database"]["entities"]:
            if e["id"] == "ENT-TOKEN":
                e["storage"] = "file"
    rw("blueprints/" + path, mark)
    r = cp.check(os.path.join(proj, ".aisef"), HERE)
    check("storage: file dispensa a chave primaria e passa no schema",
          "BP-NO-PK" not in [f["rule"] for f in r.findings] and not [f for f in r.findings if f["rule"] == "SCHEMA"],
          [(f["rule"], f["message"][:80]) for f in r.findings if f["rule"] in ("SCHEMA", "BP-NO-PK")])
finally:
    shutil.rmtree(work, ignore_errors=True)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
