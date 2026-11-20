#!/usr/bin/env python3
"""T-01: verificacao de PR (aisef_ci.py, usada pela Action aisef-verify), com git de verdade e so as chaves publicas."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_ci as ci  # noqa: E402
import aisef_new as an  # noqa: E402
import aisef_project as ap  # noqa: E402

fails = total = 0


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)[:600]))
    fails += not cond


if not shutil.which("git"):
    print("(git ausente: teste pulado)\n\n0 testes, 0 falhas")
    sys.exit(0)


def git(cwd, *args):
    return subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True)


proj = os.path.join(work, "repo")
os.makedirs(os.path.join(proj, "src"))
git(proj, "init", "-q", "-b", "main")
git(proj, "config", "user.email", "t@aisef")
git(proj, "config", "user.name", "t")
open(os.path.join(proj, "src", "a.py"), "w").write("X = 1\n")
ap.init(proj, "PRJ-CI")
ap.activate_agents(proj)
an.cmd_feature(proj, {"id": "FEAT-001", "title": "Cupom", "objective": "Aplicar cupom de desconto no total",
                      "problem": "Loja sem promocoes", "requirements": {"REQ-1": "Aplicar cupom"}, "scope_in": ["cupom"],
                      "spec": {"solution": "Cupom percentual no total", "user_stories": ["Como cliente quero cupom"],
                               "test_seams": ["total()"]},
                      "tasks": [{"id": "T-1", "title": "aplicar o cupom no total", "reqs": ["REQ-1"],
                                 "criteria": {"AC-1": "testes do cupom passam"}, "paths": ["src/a.py"]}]})
git(proj, "add", "-A")
git(proj, "commit", "-qm", "base")
BASE = "main"

rep = ci.run(proj, pr=False, strict=False)
check("projeto limpo: log integro so com chave publica e head versionado", rep["log_errors"] == [], rep["log_errors"])
check("projeto limpo passa (sem --strict)", rep["ok"], rep)

check("CLI na base limpa sai 0", ci.main(["--project", proj, "--no-strict"]) == 0)
git(proj, "switch", "-qc", "feat/001")
open(os.path.join(proj, "src", "a.py"), "w").write("X = 2\n")
ap.append(proj, {"event_type": "delegation", "actor": {"type": "orchestrator", "id": "orchestrator"},
                 "feature_id": "FEAT-001", "task_id": "T-1", "summary": "T-1 delegada"})
ap.append(proj, {"event_type": "task_started", "actor": {"type": "agent", "id": "implementer"},
                 "feature_id": "FEAT-001", "task_id": "T-1", "summary": "T-1 iniciada"})
ap.append(proj, {"event_type": "task_executed", "actor": {"type": "agent", "id": "implementer"},
                 "feature_id": "FEAT-001", "task_id": "T-1", "summary": "T-1 executada"})
git(proj, "add", "-A")
git(proj, "commit", "-qm", "T-1")
rep = ci.run(proj, pr=True, base=BASE, strict=False)
check("PR: tarefa tocada pelo arquivo do escopo e identificada", rep["pr"]["touched_tasks"] == ["T-1"], rep["pr"])
check("PR: tarefa executada e nao validada barra a PR", not rep["ok"] and rep["pr"]["unvalidated"] == ["T-1"], rep["pr"])
check("PR: log so cresceu desde a base", rep["pr"]["append_only_errors"] == [], rep["pr"])
ap.append(proj, {"event_type": "task_validated", "actor": {"type": "validator", "id": "validator"},
                 "feature_id": "FEAT-001", "task_id": "T-1", "summary": "T-1 validada"})
git(proj, "add", "-A")
git(proj, "commit", "-qm", "validada")
rep = ci.run(proj, pr=True, base=BASE, strict=False)
check("PR: depois de validada, a tarefa nao barra", rep["pr"]["unvalidated"] == [], rep["pr"])

# adulteracao de um evento
logp = os.path.join(proj, ".aisef", "audit", "log.jsonl")
original = open(logp, encoding="utf-8").read()
lines = original.splitlines()
ev = json.loads(lines[1])
ev["summary"] = "resumo trocado"
open(logp, "w", encoding="utf-8").write("\n".join([lines[0], json.dumps(ev)] + lines[2:]) + "\n")
check("evento alterado: log_errors e PR barrada", ci.run(proj, pr=True, base=BASE, strict=False)["log_errors"] != [])
open(logp, "w", encoding="utf-8").write(original)

# corte do fim com o head.json antigo (assinatura valida) restaurado
headp = os.path.join(proj, ".aisef", "audit", "head.json")
base_head = json.loads(git(proj, "show", "main:.aisef/audit/head.json").stdout)
seq = base_head["sequence"]
kept = [l for l in original.splitlines() if json.loads(l)["sequence"] < seq]
open(logp, "w", encoding="utf-8").write("\n".join(kept) + "\n")
# head de uma sequencia anterior, assinado: pegamos do historico do proprio repo (primeiro commit tinha o head da base)
older = git(proj, "log", "--format=%H", "--", ".aisef/audit/head.json").stdout.split()
heads = [json.loads(git(proj, "show", "%s:.aisef/audit/head.json" % c).stdout) for c in older]
valid_old = next((h for h in heads if h["sequence"] < seq), None)
if valid_old is None:
    # sem head mais antigo no historico: simula a reversao reconstruindo o log ate o head da base menos o fim
    valid_old = base_head
    kept = [l for l in original.splitlines() if json.loads(l)["sequence"] <= seq - 1]
    open(logp, "w", encoding="utf-8").write("\n".join(kept) + "\n")
json.dump(valid_old, open(headp, "w", encoding="utf-8"))
rep = ci.run(proj, pr=True, base=BASE, strict=False)
check("corte do log com head antigo: a PR e barrada (log da base nao esta mais la ou head nao confere)",
      not rep["ok"] and (rep["pr"]["append_only_errors"] or rep["log_errors"]), (rep["pr"], rep["log_errors"][:2]))
open(logp, "w", encoding="utf-8").write(original)
json.dump(json.loads(git(proj, "show", "HEAD:.aisef/audit/head.json").stdout), open(headp, "w", encoding="utf-8"))

# resumo e CLI
summ = os.path.join(work, "summary.md")
code = ci.main(["--project", proj, "--pr", "--base", BASE, "--no-strict", "--summary", summ])
md = open(summ, encoding="utf-8").read()
check("CLI sai 1 e o resumo lista o que o check pegou (o atalho do teste validou sem relatorio nem revisores)",
      code == 1 and "STATE-NO-REPORT" in md and "Log só cresce" in md, md[:400])
check("Action composta existe e chama o aisef_ci", "aisef_ci.py" in open(os.path.join(HERE, "..", "..", "..", ".github",
                                                                                     "actions", "aisef-verify", "action.yml"),
                                                                        encoding="utf-8").read())

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
