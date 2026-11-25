#!/usr/bin/env python3
"""M-06: o braco aisef-lean do benchmark usa a triagem de verdade (perfil solo). Tarefa comum vai pelo caminho
enxuto (uma fatia, so o code-reviewer); a de seguranca cai no ciclo completo. Sem modelo."""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bench_outcomes as bo  # noqa: E402

fails = total = 0


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)[:500]))
    fails += not cond


tasks = {t["id"]: t for t in bo.load_tasks({"feat-slugify", "sec-path-traversal"})}
base = tempfile.mkdtemp(prefix="aisef-lean-", dir=os.environ.get("TMPDIR"))
try:
    check("braco aisef-lean conhecido", "aisef-lean" in bo.ARMS)
    wd, env = bo.prepare(tasks["feat-slugify"], "aisef-lean", base)
    cfg = json.load(open(os.path.join(wd, ".aisef", "config.json"), encoding="utf-8"))
    feat = json.load(open(os.path.join(wd, ".aisef", "contracts", "features", "FEAT-BENCH.json"), encoding="utf-8"))
    tdir = os.path.join(wd, ".aisef", "contracts", "tasks")
    tc = [json.load(open(os.path.join(tdir, f), encoding="utf-8")) for f in os.listdir(tdir) if f.endswith(".json")]
    check("perfil solo no braco lean", cfg.get("profile") == "solo", cfg.get("profile"))
    check("feature comum: triagem real deu lean e ficou no contrato", bo.feature_path(wd) == "lean"
          and feat["triage"]["computed"] == "lean", feat.get("triage"))
    check("lean: uma fatia so", len(tc) == 1 and tc[0].get("kind") == "slice", [t.get("kind") for t in tc])
    check("lean: so o code-reviewer", (tc[0].get("review") or {}).get("reviewers") == ["code-reviewer"], tc[0].get("review"))
    ok, res = bo.aisef_ready(wd, env)
    check("lean: pronto para despachar", ok, res.get("actions"))

    wd2, env2 = bo.prepare(tasks["sec-path-traversal"], "aisef-lean", base)
    check("tarefa de seguranca: a triagem manda para o ciclo completo", bo.feature_path(wd2) == "full")
    check("seguranca no braco lean continua pronta", bo.aisef_ready(wd2, env2)[0])

    wd3, _ = bo.prepare(tasks["feat-slugify"], "aisef", base)
    f3 = json.load(open(os.path.join(wd3, ".aisef", "contracts", "features", "FEAT-BENCH.json"), encoding="utf-8"))
    check("braco aisef (completo) nao passa pela triagem: ciclo completo", bo.feature_path(wd3) == "full"
          and "triage" not in f3)
finally:
    shutil.rmtree(base, ignore_errors=True)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
