#!/usr/bin/env python3
"""Boas praticas (core/practices + aisef_practices): integridade dos arquivos, selecao pela deteccao, instalacao
idempotente que respeita mudancas do projeto, filtro por caminhos e entrada no pacote de contexto."""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_context as ctx  # noqa: E402
import aisef_detect as det  # noqa: E402
import aisef_practices as pr  # noqa: E402

fails, total = 0, 0


def check(name, cond, detail=None):
    global fails, total
    total += 1
    if not cond:
        fails += 1
        print("FALHA %s %s" % (name, "" if detail is None else detail))


# ---------------------------------------------------------------- integridade
all_files = []
for root, _, names in os.walk(pr.SRC):
    all_files += [os.path.relpath(os.path.join(root, n), pr.SRC).replace(os.sep, "/") for n in names if n.endswith(".md")]
check("ha praticas comuns, de arquitetura e de linguagem",
      {f.split("/")[0] for f in all_files} == {"common", "architecture", "lang"}, sorted(all_files))
for f in sorted(all_files):
    text = pr.read(os.path.join(pr.SRC, f))
    head = text.split("---", 2)[1] if text.startswith("---") else ""
    check("%s: frontmatter com description e source" % f, "description:" in head and "source:" in head)
    if f.startswith("lang/"):
        check("%s: regra de linguagem tem paths:" % f, pr.paths_of(text) != [])
    else:
        check("%s: regra geral sem paths:" % f, pr.paths_of(text) == [])
    if f.startswith("architecture/"):
        check("%s: diz quando nao usar ou quando evoluir" % f,
              any(k in text for k in ("Quando não usar", "Quando evoluir", "Use só com motivo", "no AISEF")), f)
referenced = {p for s in det.load_stacks() for p in s.get("practices", [])} | set(det.STYLE_PRACTICE.values())
for ref in sorted(referenced):
    check("pratica referenciada existe: %s" % ref, pr.files_for([ref]) != [], ref)
for d in det.recommend([], [{"id": "microservices", "confidence": 1}], [{"file": "a", "line": 1, "import": "x"}], ["a.py"] * 50,
                       {".py": 50}):
    for s in d["suggested"]:
        if s.startswith("practice:"):
            check("recomendacao aponta pratica existente: %s" % s, pr.files_for([s[9:]]) != [])

# ---------------------------------------------------------------- selecao e instalacao
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
proj = os.path.join(work, "p")
os.makedirs(os.path.join(proj, ".aisef"))
check("sem deteccao: so as comuns", pr.wanted(proj) == ["common"])
arch = {"practices": ["common", "lang/python", "architecture/layered-mvc"],
        "styles": [{"id": "layered-mvc", "confidence": 0.8}]}
with open(os.path.join(proj, ".aisef", "architecture.json"), "w", encoding="utf-8") as fh:
    json.dump(arch, fh)
rows = pr.plan(proj)
targets = {r["target"] for r in rows}
check("plano inclui python e o estilo detectado", ".claude/rules/aisef/lang/python.md" in targets
      and ".claude/rules/aisef/architecture/layered-mvc.md" in targets, sorted(targets))
check("plano nao inclui outra linguagem", ".claude/rules/aisef/lang/go.md" not in targets)
check("tudo novo antes de instalar", {r["state"] for r in rows} == {"novo"})
done, kept = pr.apply(proj)
check("instala todos", len(done) == len(rows) and kept == [])
check("segunda instalacao nao muda nada", pr.apply(proj) == ([], []))
mine = os.path.join(proj, ".claude", "rules", "aisef", "common", "testing.md")
with open(mine, "a", encoding="utf-8") as fh:
    fh.write("\n- regra do time\n")
done, kept = pr.apply(proj)
check("arquivo mudado no projeto e mantido", kept == [".claude/rules/aisef/common/testing.md"] and done == [], (done, kept))
check("--force sobrescreve", pr.apply(proj, force=True)[0] == [".claude/rules/aisef/common/testing.md"])

arch["approved"] = {"styles": ["clean", "ddd-tactical"], "request_id": "REQ-1", "approved_at": "2026-11-19T10:00:00-03:00"}
with open(os.path.join(proj, ".aisef", "architecture.json"), "w", encoding="utf-8") as fh:
    json.dump(arch, fh)
w = pr.wanted(proj)
check("estilo adotado substitui o detectado", "architecture/clean-architecture" in w and "architecture/ddd-tactical" in w
      and "architecture/layered-mvc" not in w, w)

# ---------------------------------------------------------------- por caminhos e no pacote de contexto
got = pr.for_paths(proj, ["src/app/models.py"])
check("arquivo .py recebe a pratica de python", "lang/python.md" in got, got)
check("regras gerais valem sempre", "common/coding-style.md" in got and "architecture/clean-architecture.md" in got)
check("arquivo .ts nao recebe a pratica de python", "lang/python.md" not in pr.for_paths(proj, ["web/a.ts"]))
a = ctx._architecture_for(proj, ["src/app/models.py"])
check("pacote: estilo adotado", a["adopted"] and a["styles"] == ["clean", "ddd-tactical"], a)
check("pacote: pratica instalada aponta para .claude/rules", ".claude/rules/aisef/common/testing.md" in a["practices"], a["practices"])
check("pacote: pratica nao instalada aponta para o plugin",
      "<CORE>/practices/architecture/clean-architecture.md" in a["practices"], a["practices"])

shutil.rmtree(work, ignore_errors=True)
print("%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
