#!/usr/bin/env python3
"""Testes da F-10: dependencias entre features. O gerador (aisef_new.py feature) exige `depends_on_features` quando o
projeto ja tem outra feature e grava `dependencies.features`; o check acusa feature sem declaracao, dependencia
inexistente e ciclo."""
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


def check(name, cond, extra=None):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond or extra is None else "  -> %s" % (extra,)))
    fails += not cond


def brief(fid, n, deps="omit"):
    b = json.loads(json.dumps(aisef_new.EXAMPLES["feature"]))
    b.pop("depends_on_features", None)
    if deps != "omit":
        b["depends_on_features"] = deps
    b.update(id=fid, requirements={"REQ-%d" % n: "Requisito %d" % n})
    b["tasks"] = [dict(b["tasks"][0], id="T-%d" % n, reqs=["REQ-%d" % n], criteria={"AC-%d" % n: "Criterio %d (teste)" % n})]
    return b


def refused(b):
    try:
        aisef_new.cmd_feature(proj, b)
        return False
    except SystemExit:
        return not os.path.exists(path(b["id"]))


def path(fid):
    return os.path.join(proj, ".aisef", "contracts", "features", fid + ".json")


def load(fid):
    with open(path(fid), encoding="utf-8") as fh:
        return json.load(fh)


def save(fid, doc):
    with open(path(fid), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)


def rules():
    r = cp.check(os.path.join(proj, ".aisef"), HERE, POL, DEF)
    return [(f["rule"], f.get("where") or f.get("location") or "") for f in r.findings if f["rule"].startswith("FEATURE-")]


try:
    proj = os.path.join(work, "p")
    os.makedirs(proj)
    ap.init(proj, "PRJ-D", "deps", "dev")
    ap.activate_agents(proj)

    # ---------------------------------------------------------------- gerador
    aisef_new.cmd_feature(proj, brief("FEAT-001", 1))
    check("primeira feature dispensa depends_on_features", load("FEAT-001")["dependencies"] == {})
    aisef_new.cmd_quick(proj, "Corrige typo", "texto errado", [], None)
    check("FEAT-MAINT nasce sem declarar dependencia", os.path.exists(path("FEAT-MAINT")))
    check("segunda feature sem depends_on_features e recusada sem gravar nada", refused(brief("FEAT-002", 2)))
    check("depends_on_features com feature inexistente e recusado", refused(brief("FEAT-002", 2, ["FEAT-099"])))
    check("depends_on_features nao aceita FEAT-MAINT como dependencia", refused(brief("FEAT-002", 2, ["FEAT-MAINT"])))
    aisef_new.cmd_feature(proj, brief("FEAT-002", 2, ["FEAT-001"]))
    check("dependencia declarada e gravada no contrato", load("FEAT-002")["dependencies"] == {"features": ["FEAT-001"]})
    aisef_new.cmd_feature(proj, brief("FEAT-003", 3, []))
    check("[] grava a independencia explicita", load("FEAT-003")["dependencies"] == {"features": []})
    check("exemplo do brief ja traz depends_on_features",
          "depends_on_features" in aisef_new.EXAMPLES["feature"])
    check("projeto gerado assim nao tem achado FEATURE-*", rules() == [], rules())

    # ---------------------------------------------------------------- check
    f3 = load("FEAT-003")
    f3["dependencies"] = {}
    save("FEAT-003", f3)
    r = rules()
    check("feature sem dependencies.features -> FEATURE-DEPS-UNDECLARED (aviso)",
          [x for x in r if x[0] == "FEATURE-DEPS-UNDECLARED" and "FEAT-003" in x[1]], r)
    check("a primeira feature e a FEAT-MAINT nao sao acusadas",
          not [x for x in r if "FEAT-001" in x[1] or "FEAT-MAINT" in x[1]], r)
    f3["dependencies"] = {"features": ["FEAT-404"]}
    save("FEAT-003", f3)
    check("dependencia inexistente -> FEATURE-DEP-UNKNOWN", ("FEATURE-DEP-UNKNOWN", "feature FEAT-003") in rules(), rules())
    f3["dependencies"] = {"features": ["FEAT-003"]}
    save("FEAT-003", f3)
    check("feature que depende de si mesma -> FEATURE-DEP-CYCLE", ("FEATURE-DEP-CYCLE", "feature FEAT-003") in rules(), rules())
    f3["dependencies"] = {"features": ["FEAT-002"]}
    save("FEAT-003", f3)
    f1 = load("FEAT-001")
    f1["dependencies"] = {"features": ["FEAT-003"]}
    save("FEAT-001", f1)
    r = rules()
    check("ciclo entre features (001 -> 003 -> 002 -> 001) -> FEATURE-DEP-CYCLE",
          [x for x in r if x[0] == "FEATURE-DEP-CYCLE" and x[1] == "features"], r)
    f1["dependencies"] = {}
    save("FEAT-001", f1)
    check("sem ciclo e com tudo declarado, nenhum achado", rules() == [], rules())
finally:
    shutil.rmtree(work, ignore_errors=True)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
