#!/usr/bin/env python3
"""Testes da triagem (C-01): aisef_triage (sinais, perfis, --force), o brief lean no aisef_new e as regras TRIAGE-*."""
import copy
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_new as an  # noqa: E402
import aisef_project as ap  # noqa: E402
import aisef_triage as tr  # noqa: E402
import check_project as cp  # noqa: E402

fails = total = 0


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)))
    fails += not cond


def path_of(**kw):
    kw.setdefault("files", 2)
    kw.setdefault("lines", 30)
    return tr.compute(**kw)[0]


# ------------------------------------------------------------------ sinais (perfil a parte)
check("typo em doc: quick", path_of(paths=["README.md"], changes=["typo"]) == "quick")
check("lint e rename local pequenos: quick", path_of(paths=["src/a.py"], changes=["lint", "rename_local"]) == "quick")
check("patch de dependencia: quick", path_of(paths=["requirements.txt"], changes=["dependency_patch"], lines=2) == "quick")
check("so testes: quick", path_of(paths=["tests/test_a.py"], changes=["test_only"]) == "quick")
check("mudanca sem comportamento com mais de 50 linhas: lean",
      path_of(paths=["docs/a.md"], changes=["docs"], lines=200) == "lean")
check("comportamento novo pequeno: lean", path_of(paths=["src/slug.py", "tests/test_slug.py"], changes=["behavior"]) == "lean")
check("bugfix pequeno: lean", path_of(paths=["src/page.py"], changes=["bugfix"]) == "lean")
check("refatoracao pequena: lean", path_of(paths=["src/ship.py"], changes=["refactor"]) == "lean")
check("ui pequena: lean", path_of(paths=["src/ui/Button.tsx"], changes=["ui"]) == "lean")
check("sem tipo de mudanca informado: lean (nunca quick)", path_of(paths=["src/a.py"], changes=[]) == "lean")
for kind in sorted(tr.FULL_CHANGES):
    check("tipo %s: full" % kind, path_of(paths=["src/a.py"], changes=["behavior", kind]) == "full")
check("risco high: full", path_of(paths=["src/a.py"], changes=["behavior"], risk="high") == "full")
check("risco critical: full mesmo para typo", path_of(paths=["src/a.py"], changes=["typo"], risk="critical") == "full")
check("risco medium nao forca full", path_of(paths=["src/a.py"], changes=["behavior"], risk="medium") == "lean")
check("2 fatias: full", path_of(paths=["src/a.py"], changes=["behavior"], slices=2) == "full")
check("6 arquivos: full", path_of(paths=["src/*"], changes=["behavior"], files=6) == "full")
check("tamanho desconhecido: full", path_of(paths=["src/a.py"], changes=["behavior"], files=None) == "full")
check("migracao pelo caminho: full", path_of(paths=["migrations/0003_add.py"], changes=["behavior"]) == "full")
check("arquivo .sql: full", path_of(paths=["db/seed.sql"], changes=["behavior"]) == "full")
check("pasta auth: full", path_of(paths=["src/auth/token.py"], changes=["bugfix"]) == "full")
check("CI (classificacao do gateway): full", path_of(paths=[".github/workflows/ci.yml"], changes=["text"]) == "full")
check("arquivo sensivel (.env): full", path_of(paths=[".env"], changes=["config_local"]) == "full")
check("config de lint (gateway: nao afrouxar): full", path_of(paths=["ruff.toml"], changes=["lint"]) == "full")
check("pasta 'author' nao e auth", path_of(paths=["src/authors/list.py"], changes=["behavior"]) == "lean")
c, why = tr.compute(paths=["src/auth/x.py"], changes=["api"], files=9, slices=3, risk="high")
check("full junta todos os motivos", c == "full" and len(why) == 5, why)
try:
    tr.compute(changes=["magia"], files=1)
    ok = False
except ValueError as e:
    ok = "magia" in str(e)
check("tipo de mudanca desconhecido e erro", ok)

# ------------------------------------------------------------------ perfis e --force
lean_args = dict(paths=["src/slug.py"], changes=["behavior"], files=2, lines=40)
r = tr.triage(profile="solo", **lean_args)
check("solo: lean efetivo", r["path"] == "lean" and r["computed"] == "lean" and "note" not in r, r)
r = tr.triage(profile="team", **lean_args)
check("team: lean calculado vira full, com nota", r["path"] == "full" and r["computed"] == "lean" and "team" in r["note"], r)
r = tr.triage(profile="team", paths=["README.md"], changes=["typo"], files=1, lines=1)
check("team: quick continua quick", r["path"] == "quick", r)
r = tr.triage(profile="regulated", paths=["README.md"], changes=["typo"], files=1, lines=1)
check("regulated: quick vira lean", r["path"] == "lean" and r["computed"] == "quick", r)
r = tr.triage(profile="solo", force="full", **lean_args)
check("--force full sobe e marca forced_by_user", r["path"] == "full" and r.get("forced_by_user"), r)
try:
    tr.triage(profile="solo", force="quick", **lean_args)
    ok = False
except ValueError as e:
    ok = "nao da para descer" in str(e)
check("--force para baixo e recusado", ok)
proj = os.path.join(work, "proj")
os.makedirs(proj)
ap.init(proj, "PRJ-TRI")
check("projeto sem profile no config: team (comportamento anterior)", tr.triage(proj, **lean_args)["profile"] == "team")
cfg = ap.load_config(proj)
cfg["profile"] = "solo"
ap.write_json(os.path.join(proj, ".aisef", "config.json"), cfg)
check("profile do config.json e lido", tr.triage(proj, **lean_args)["profile"] == "solo")
check("linha legivel cita caminho e motivo", tr.line(tr.triage(proj, **lean_args)).startswith("Caminho: lean, porque"))
check("CLI --json sai 0", tr.main(["--project", proj, "--paths", "src/a.py", "--changes", "behavior", "--files", "1",
                                    "--lines", "10", "--json"]) == 0)
check("CLI com tipo invalido sai 2", tr.main(["--project", proj, "--changes", "x", "--files", "1"]) == 2)

# ------------------------------------------------------------------ brief lean no aisef_new + check
ap.activate_agents(proj)
TRI = tr.triage(proj, **lean_args)
BRIEF = {"id": "FEAT-010", "title": "Slugify", "objective": "Gerar slugs de titulos", "problem": "URLs com acento quebram",
         "requirements": {"REQ-100": "Gerar slug minusculo sem acentos"}, "scope_in": ["funcao slugify"],
         "spec": {"solution": "Funcao pura slugify(texto) em src/slug.py", "user_stories": ["Como autor quero URLs limpas"],
                  "test_seams": ["slugify()"]},
         "triage": TRI,
         "tasks": [{"id": "T-100", "title": "slugify com testes", "reqs": ["REQ-100"],
                    "criteria": {"AC-100": "testes de slugify passam"}, "paths": ["src/slug.py", "tests/test_slug.py"],
                    "test_cmd": "pytest -q"}]}
an.cmd_feature(proj, copy.deepcopy(BRIEF))
feat = json.load(open(os.path.join(proj, ".aisef", "contracts", "features", "FEAT-010.json"), encoding="utf-8"))
task = json.load(open(os.path.join(proj, ".aisef", "contracts", "tasks", "T-100.json"), encoding="utf-8"))
check("lean: o contrato guarda a triagem", feat["triage"]["path"] == "lean" and feat["triage"]["reasons"], feat.get("triage"))
check("lean: uma fatia com TDD", task["kind"] == "slice" and task["tests"]["tdd_required"] is True, task.get("tests"))
check("lean: so o code-reviewer", task["review"]["reviewers"] == ["code-reviewer"], task.get("review"))
check("lean: validador independente continua", task["validation"]["independent_validator_required"] is True)


def rules(project):
    rep = cp.check(project, policy_path=os.path.join(HERE, "permission-policy.v0.1.json"),
                   defaults_path=os.path.join(HERE, "orchestration-defaults.v0.1.json"))
    return {f["rule"] for f in rep.findings if f["severity"] == "error"}


check("lean bem formado: sem erro TRIAGE", not {r for r in rules(proj) if r.startswith("TRIAGE")}, rules(proj))


def refuses(brief, text):
    try:
        an.feature_docs(brief, proj, ap.now_iso())
        return False
    except SystemExit as e:
        return text in str(e)


b = copy.deepcopy(BRIEF)
b["id"] = "FEAT-011"
b["tasks"].append(dict(copy.deepcopy(b["tasks"][0]), id="T-101"))
check("aisef_new: lean com 2 tarefas e recusado", refuses(b, "exatamente uma fatia"))
b = copy.deepcopy(BRIEF)
b["triage"] = dict(TRI, computed="full")
check("aisef_new: descer de full para lean e recusado", refuses(b, "descer"))
b = copy.deepcopy(BRIEF)
b["triage"] = dict(TRI, path="quick", computed="quick")
check("aisef_new: quick nao vira Feature Contract", refuses(b, "aisef_new.py quick"))

# o check pega edicao manual
fpath = os.path.join(proj, ".aisef", "contracts", "features", "FEAT-010.json")
orig = open(fpath, encoding="utf-8").read()
f2 = json.loads(orig)
f2["triage"]["computed"] = "full"
ap.write_json(fpath, f2)
check("check: TRIAGE-OVERRIDDEN-DOWN quando o caminho fica abaixo do calculado", "TRIAGE-OVERRIDDEN-DOWN" in rules(proj))
open(fpath, "w", encoding="utf-8").write(orig)
tpath = os.path.join(proj, ".aisef", "contracts", "tasks", "T-100.json")
torig = open(tpath, encoding="utf-8").read()
t2 = json.loads(torig)
t2["tests"]["tdd_required"] = False
ap.write_json(tpath, t2)
check("check: TRIAGE-LEAN-SHAPE quando o lean perde o TDD", "TRIAGE-LEAN-SHAPE" in rules(proj))
open(tpath, "w", encoding="utf-8").write(torig)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
