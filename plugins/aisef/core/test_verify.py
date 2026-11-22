#!/usr/bin/env python3
"""verify-loop (aisef_verify): fases por stack, SKIP de ferramenta ausente, FAIL que reprova, varredura de segredos
no diff sem imprimir o valor, e relatorio de evidencia por tarefa."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_verify as av  # noqa: E402

fails, total = 0, 0


def check(name, cond, detail=None):
    global fails, total
    total += 1
    if not cond:
        fails += 1
        print("FALHA %s %s" % (name, "" if detail is None else json.dumps(detail, ensure_ascii=False)[:600]))


work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
proj = os.path.join(work, "p")
os.makedirs(os.path.join(proj, ".aisef"))
py = '"%s"' % sys.executable.replace("\\", "/")


def config(verify):
    with open(os.path.join(proj, ".aisef", "config.json"), "w", encoding="utf-8") as fh:
        json.dump({"verify": verify}, fh)
    with open(os.path.join(proj, ".aisef", "architecture.json"), "w", encoding="utf-8") as fh:
        json.dump({"commands": {}}, fh)


def git(*args):
    subprocess.run(["git", *args], cwd=proj, capture_output=True, check=True)


git("init", "-q")
git("config", "user.email", "t@example.com")
git("config", "user.name", "t")
with open(os.path.join(proj, "app.py"), "w", encoding="utf-8") as fh:
    fh.write("x = 1\n")
git("add", "app.py")
git("commit", "-q", "-m", "init")

# ---------------------------------------------------------------- nada configurado
config({})
rep = av.verify(proj)
check("sem comandos: INCOMPLETE com aviso", rep["verdict"] == "INCOMPLETE" and rep["note"], rep)

# ---------------------------------------------------------------- tudo verde, ferramenta ausente vira SKIP
config({"python": {"test": py + " -c \"print('ok')\"", "lint": py + " -c \"pass\"",
                   "build": "ferramenta-que-nao-existe-aisef build"}})
rep = av.verify(proj)
phases = {s["phase"]: s["result"] for s in rep["steps"]}
check("testes e lint passam", phases.get("test") == "PASS" and phases.get("lint") == "PASS", rep["steps"])
check("ferramenta ausente vira SKIP", phases.get("build") == "SKIP", rep["steps"])
check("veredito PASS", rep["verdict"] == "PASS", rep)
check("ordem das fases: build, lint, test, secrets, diff",
      [s["phase"] for s in rep["steps"]] == ["build", "lint", "test", "secrets", "diff"], [s["phase"] for s in rep["steps"]])

# ---------------------------------------------------------------- teste falhando reprova
config({"python": {"test": py + " -c \"import sys; print('quebrou'); sys.exit(3)\""}})
rep = av.verify(proj, only={"test"})
st = rep["steps"][0]
check("teste falhando: FAIL com exit code e saida", rep["verdict"] == "FAIL" and st["exit_code"] == 3 and "quebrou" in st["tail"], st)
check("CLI sai 1 com FAIL", av.main(["--project", proj, "--only", "test"]) == 1)

# ---------------------------------------------------------------- segredo no diff
key = "AKIA" + "ABCDEFGHIJKLMNOP"
with open(os.path.join(proj, "app.py"), "a", encoding="utf-8") as fh:
    fh.write('aws = "%s"\nsenha_exemplo = os.environ["X"]\n' % key)
config({})
rep = av.verify(proj, only={"secrets"})
sec = rep["steps"][0]
check("segredo adicionado no diff reprova", sec["result"] == "FAIL" and sec["findings"][0]["file"] == "app.py"
      and sec["findings"][0]["line"] == 2 and sec["findings"][0]["kind"] == "chave AWS", sec)
check("o valor do segredo nunca aparece no relatorio", key not in json.dumps(rep) and key not in av.render(rep))
check("leitura de variavel de ambiente nao e segredo", len(sec["findings"]) == 1, sec["findings"])

# ---------------------------------------------------------------- relatorio por tarefa
config({"python": {"test": py + " -c \"pass\""}})
git("checkout", "--", "app.py")
check("CLI com --task sai 0", av.main(["--project", proj, "--task", "T-010"]) == 0)
path = os.path.join(proj, ".aisef", "evidence", "VERIFY-T-010.json")
check("--task grava a evidencia", os.path.exists(path) and json.load(open(path, encoding="utf-8"))["task_id"] == "T-010")

# ---------------------------------------------------------------- repositorio sem nenhum commit (uso real, HireMe)
fresh = os.path.join(work, "novo")
os.makedirs(fresh)
subprocess.run(["git", "init", "-q", fresh], capture_output=True, check=True)
with open(os.path.join(fresh, ".env"), "w", encoding="utf-8") as fh:
    fh.write('token = "%s"\n' % key)
rep = av.verify(fresh, only={"secrets", "diff"})
st = {s["phase"]: s for s in rep["steps"]}
check("sem commit e nada no index: segredos e diff nao pulam (PASS, nada para o commit levar)",
      st["secrets"]["result"] == "PASS" and st["diff"]["result"] == "PASS", rep["steps"])
subprocess.run(["git", "-C", fresh, "add", "-A"], capture_output=True, check=True)
rep = av.verify(fresh, only={"secrets"})
sec = rep["steps"][0]
check("sem commit: segredo no index (o que o commit inicial levaria) reprova",
      sec["result"] == "FAIL" and sec["findings"][0]["file"] == ".env", sec)

shutil.rmtree(work, ignore_errors=True)
print("%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
