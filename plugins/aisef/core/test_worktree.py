#!/usr/bin/env python3
"""L-02a: dentro de um worktree, hooks e CLI gravam no .aisef do repositorio principal (o log nunca se divide).
Usa git de verdade (git worktree add); sem git no PATH, o teste e pulado."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(os.path.dirname(HERE), "hooks")
sys.path.insert(0, HERE)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_git  # noqa: E402
import aisef_project as ap  # noqa: E402
import audit_chain  # noqa: E402

fails = total = 0


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)[:400]))
    fails += not cond


if not shutil.which("git"):
    print("(git ausente: teste pulado)\n\n0 testes, 0 falhas")
    sys.exit(0)


def git(cwd, *args):
    return subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True)


main = os.path.join(work, "repo")
os.makedirs(main)
git(main, "init", "-q")
git(main, "config", "user.email", "t@aisef")
git(main, "config", "user.name", "t")
open(os.path.join(main, "README.md"), "w").write("x\n")
ap.init(main, "PRJ-WT")
git(main, "add", "-A")
git(main, "commit", "-qm", "init")
wt = os.path.join(work, "wt-T-001")
r = git(main, "worktree", "add", "-q", "-b", "slice/feat-x/T-001", wt)
check("worktree criado", r.returncode == 0 and os.path.isfile(os.path.join(wt, ".git")), r.stderr)
check("main_worktree_root: do worktree acha o principal", os.path.normcase(aisef_git.main_worktree_root(wt) or "")
      == os.path.normcase(os.path.realpath(main)) or os.path.normcase(aisef_git.main_worktree_root(wt) or "") == os.path.normcase(main),
      aisef_git.main_worktree_root(wt))
check("main_worktree_root: no principal, nada a redirecionar", aisef_git.main_worktree_root(main) is None)
check("aisef_root de uma subpasta do worktree", os.path.normcase(os.path.realpath(aisef_git.aisef_root(os.path.join(wt, ".aisef"))))
      == os.path.normcase(os.path.realpath(main)))
check("branch do worktree e a da fatia", aisef_git.current_branch(wt) == "slice/feat-x/T-001")


def log_len(root):
    return len(audit_chain.read_log_dir(os.path.join(root, ".aisef", "audit")))


m0, w0 = log_len(main), log_len(wt)
payload = {"tool_name": "Bash", "tool_input": {"command": "pytest -q"}, "cwd": wt, "session_id": "S"}
subprocess.run([sys.executable, "-I", os.path.join(HOOKS, "audit_hook.py")], input=json.dumps(payload), text=True,
               capture_output=True, env=dict(os.environ, CLAUDE_PROJECT_DIR=wt))
check("hook de auditoria dentro do worktree grava no log principal", log_len(main) == m0 + 1 and log_len(wt) == w0,
      (log_len(main), m0, log_len(wt), w0))
r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "aisef_project.py"), "append", "--project", wt, "--type",
                    "delegation", "--summary", "T-001 delegada no worktree"], capture_output=True, text=True)
check("CLI append com --project do worktree grava no log principal", log_len(main) == m0 + 2 and log_len(wt) == w0,
      r.stdout + r.stderr)
check("log principal continua integro (cadeia e assinaturas)", ap.verify(main)[0] == [], ap.verify(main)[0])
gw = {"tool_name": "Bash", "tool_input": {"command": "git status"}, "cwd": wt}
r = subprocess.run([sys.executable, "-I", os.path.join(HOOKS, "gateway.py")], input=json.dumps(gw), text=True,
                   capture_output=True, env=dict(os.environ, CLAUDE_PROJECT_DIR=wt))
check("gateway dentro do worktree usa a config do principal e segue decidindo", r.returncode == 0 and not r.stdout.strip(),
      r.stdout + r.stderr)
outro = os.path.join(work, "sem-aisef")
os.makedirs(outro)
check("pasta sem worktree nem AISEF: aisef_root devolve ela mesma", aisef_git.aisef_root(outro) == outro)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
