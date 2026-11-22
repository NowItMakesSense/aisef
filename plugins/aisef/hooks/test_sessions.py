#!/usr/bin/env python3
"""Outra sessao no mesmo projeto (aisef_sessions + gateway + auditoria + doctor), pelos hooks de verdade:
editar o arquivo que outra sessao tem alterado sem commit pergunta antes; commit/push/PR mostram as mudancas dela;
a mesma pasta compartilhada e detectada; as worktrees das fatias da propria sessao nao contam; o que ja foi commitado
la ou esta esquecido ha muito tempo nao incomoda."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.join(os.path.dirname(HERE), "core")
sys.path.insert(0, CORE)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_project  # noqa: E402
import aisef_sessions as ses  # noqa: E402

fails = total = 0


def check(name, cond, detail=None):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name)
    if not cond and detail is not None:
        print("      ", str(detail)[:900])
    fails += not cond


if not shutil.which("git"):
    print("git ausente: testes pulados\n0 testes, 0 falhas")
    sys.exit(0)

proj = os.path.join(work, "proj")
os.makedirs(os.path.join(proj, "src"))
aisef_project.init(proj, "PRJ-S", "sessoes", "dev")


def git(cwd, *args):
    return subprocess.run(["git", "-C", cwd, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
                          + list(args), capture_output=True, text=True, check=True).stdout


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


write(os.path.join(proj, "src", "a.py"), "a = 1\n")
write(os.path.join(proj, "src", "b.py"), "b = 1\n")
write(os.path.join(proj, ".gitignore"), ".aisef/\n")
git(proj, "init", "-q", "-b", "main")
git(proj, "add", "-A")
git(proj, "commit", "-q", "-m", "inicio")
wt2 = os.path.join(work, "proj-outra")
git(proj, "worktree", "add", "-q", "-b", "feat/outra", wt2)
wt3 = os.path.join(work, "proj-fatia")
git(proj, "worktree", "add", "-q", "-b", "slice/T-001", wt3)


def hook(script, payload, project):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=project)
    return subprocess.run([sys.executable, "-I", os.path.join(HERE, script)], input=json.dumps(payload),
                          capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)


def gate(sid, tool, cwd, **inp):
    r = hook("gateway.py", {"tool_name": tool, "tool_input": inp, "cwd": cwd, "session_id": sid}, cwd)
    if not r.stdout.strip():
        return "allow", ""
    out = json.loads(r.stdout.strip().splitlines()[0])["hookSpecificOutput"]
    return out.get("permissionDecision", "allow"), out.get("permissionDecisionReason", "")


def edit(sid, cwd, path, text):
    """Sessao edita de fato: gateway (antes), o arquivo muda, auditoria (depois)."""
    gate(sid, "Write", cwd, file_path=path, content=text)
    write(path, text)
    hook("audit_hook.py", {"tool_name": "Write", "tool_input": {"file_path": path, "content": text}, "cwd": cwd,
                           "session_id": sid}, cwd)


# ---- sessao B trabalha na outra worktree
edit("sessao-B-1234", wt2, os.path.join(wt2, "src", "a.py"), "a = 2  # B\n")
rec = next((r for r in ses.sessions(proj) if r["session_id"] == "sessao-B-1234"), None)
check("worktree grava o registro da sessao no .aisef do repositorio principal (fora do Git)",
      rec and any(k.endswith("|src/a.py") for k in rec["files"])
      and open(os.path.join(proj, ".aisef", "runtime", ".gitignore"), encoding="utf-8").read().strip() == "*", rec)

d, why = gate("sessao-A-5678", "Edit", proj, file_path=os.path.join(proj, "src", "a.py"), old_string="a = 1", new_string="a = 3")
check("editar o arquivo que outra sessao tem alterado sem commit: pergunta, dizendo quem, onde e como ver",
      d == "ask" and "sessao-B" in why and "src/a.py" in why and "feat/outra" in why and "--diff" in why, (d, why))
d, why = gate("sessao-A-5678", "Edit", proj, file_path=os.path.join(proj, "src", "b.py"), old_string="b = 1", new_string="b = 3")
check("arquivo que nenhuma outra sessao mexeu: segue livre", d == "allow", (d, why))
d, why = gate("sessao-B-1234", "Edit", wt2, file_path=os.path.join(wt2, "src", "a.py"), old_string="a = 2", new_string="a = 4")
check("a propria sessao editando o seu arquivo: segue livre", d == "allow", (d, why))

d, why = gate("sessao-A-5678", "Bash", proj, command="git commit -m x")
check("commit com outra sessao com mudancas sem commit: pergunta e mostra os arquivos, a branch e o comando do diff",
      d == "ask" and "src/a.py" in why and "feat/outra" in why and "git -C" in why and "diff HEAD" in why, (d, why))
for cmd in ("git push origin main", "gh pr create --fill", "git merge feat/x"):
    d, why = gate("sessao-A-5678", "Bash", proj, command=cmd)
    check("%s tambem mostra as mudancas da outra sessao" % cmd.split()[0:2], d in ("ask", "deny") and "src/a.py" in why, (d, why))
d, why = gate("sessao-A-5678", "Bash", proj, command="git status")
check("leitura (git status) nao e afetada", d == "allow", (d, why))

out = hook("doctor.py", {"hook_event_name": "SessionStart", "source": "startup", "cwd": proj, "session_id": "sessao-A-5678"}, proj).stdout
check("doctor: no inicio da sessao avisa da outra sessao e do que ela tem sem commit",
      "outra sessao esta trabalhando" in out and "src/a.py" in out, out)

st = subprocess.run([sys.executable, "-I", os.path.join(CORE, "aisef_sessions.py"), "status", "--project", proj,
                     "--session", "sessao-A-5678", "--diff"], capture_output=True, text=True, encoding="utf-8", timeout=60).stdout
check("status --diff mostra o diff da outra sessao para o usuario ver antes do commit", "a = 2  # B" in st and "feat/outra" in st, st)

# ---- fatia da propria sessao (worktree slice/) nao e "outra sessao"
edit("sessao-A-5678", proj, os.path.join(wt3, "src", "b.py"), "b = 9  # fatia de A\n")
found = ses.concurrent(proj, "sessao-A-5678", proj)
check("worktree da fatia da propria sessao nao entra na lista", all(ses._key(f["worktree"]) != ses._key(wt3) for f in found), found)

# ---- B commita: o trabalho dela deixa de estar em paralelo
git(wt2, "commit", "-q", "-am", "B terminou")
d, why = gate("sessao-A-5678", "Edit", proj, file_path=os.path.join(proj, "src", "a.py"), old_string="a = 1", new_string="a = 3")
check("depois que a outra sessao commita, editar o mesmo arquivo segue livre", d == "allow", (d, why))
check("e o commit nao pergunta mais por ela", not [f for f in ses.concurrent(proj, "sessao-A-5678", proj)
                                                     if ses._key(f["worktree"]) == ses._key(wt2)])

# ---- duas sessoes na MESMA pasta: o git add -A levaria o trabalho da outra
edit("sessao-C-0000", proj, os.path.join(proj, "src", "c.py"), "c = 1  # C\n")
d, why = gate("sessao-A-5678", "Bash", proj, command="git commit -am x")
check("mesma pasta: commit pergunta e lista so o arquivo da outra sessao",
      d == "ask" and "nesta mesma pasta" in why and "src/c.py" in why and "src/b.py" not in why, (d, why))

# ---- worktree sem sessao registrada: so conta se alguem mexeu ha pouco
wt4 = os.path.join(work, "proj-velha")
git(proj, "worktree", "add", "-q", "-b", "feat/velha", wt4)
old = os.path.join(wt4, "src", "a.py")
write(old, "a = 7  # esquecido\n")
t = time.time() - 3 * 86400
os.utime(old, (t, t))
check("worktree esquecida ha dias, sem sessao: nao incomoda",
      not [f for f in ses.concurrent(proj, "sessao-A-5678", proj) if ses._key(f["worktree"]) == ses._key(wt4)])
os.utime(old, None)
check("mexida agora, sem sessao do AISEF (outro editor, outra ferramenta): entra, marcada como sem sessao",
      any(ses._key(f["worktree"]) == ses._key(wt4) and not f["sessions"]
          for f in ses.concurrent(proj, "sessao-A-5678", proj)))

# ---- sem session_id (hook antigo ou teste): sem registro e sem pergunta nova
before = len(ses.sessions(proj))
r = hook("gateway.py", {"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": proj}, proj)
check("sem session_id: nao cria registro", len(ses.sessions(proj)) == before and not r.stdout.strip(), r.stdout)

# ---- batimento: a cada chamada, mas sem regravar o arquivo toda hora
fp = os.path.join(proj, ".aisef", "runtime", "sessions", "sessao-A-5678.json")
m1 = os.path.getmtime(fp)
time.sleep(0.05)
ses.touch(proj, "sessao-A-5678", proj)
check("batimento sem arquivo novo nao regrava o registro a cada chamada", os.path.getmtime(fp) == m1)

# ---- coordenacao: cada sessao numa area separada
SES = os.path.join(CORE, "aisef_sessions.py")


def cli(*args):
    return subprocess.run([sys.executable, "-I", SES] + list(args), capture_output=True, text=True, encoding="utf-8", timeout=60)


def context(sid, cwd):
    r = hook("gateway.py", {"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": cwd, "session_id": sid}, cwd)
    return json.loads(r.stdout)["hookSpecificOutput"].get("additionalContext", "") if r.stdout.strip() else ""


context("sessao-A-5678", proj)  # zera o que A ja viu
r = cli("claim", "--project", wt2, "--session", "sessao-B-1234", "--paths", "src/painel/**", "--note", "reforma do painel")
check("claim: a sessao reserva uma area (pela worktree dela, gravando no projeto principal)", r.returncode == 0, r.stdout + r.stderr)
ctx = context("sessao-A-5678", proj)
check("a outra sessao e avisada da area reservada, com a instrucao de ficar fora e reservar a sua",
      "sessao-B" in ctx and "reforma do painel" in ctx and "src/painel/**" in ctx and " claim " in ctx, ctx)
check("o aviso vem uma vez por mudanca, nao a cada chamada", context("sessao-A-5678", proj) == "")
d, why = gate("sessao-A-5678", "Write", proj, file_path=os.path.join(proj, "src", "painel", "x.py"), content="x")
check("editar na area reservada por outra sessao: pergunta e sugere trabalhar numa parte separada",
      d == "ask" and "area reservada" in why and "reforma do painel" in why and "separada" in why, (d, why))
d, why = gate("sessao-A-5678", "Write", proj, file_path=os.path.join(proj, "docs", "x.md"), content="x")
check("fora da area da outra sessao: segue livre", d == "allow", (d, why))
r = cli("claim", "--project", proj, "--session", "sessao-A-5678", "--paths", "src/**", "--note", "refatorar src")
check("reservar uma area que sobrepoe a da outra: avisa (sai 3) para combinar com o usuario",
      r.returncode == 3 and "sobrepoe" in r.stdout and "reforma do painel" in r.stdout, r.stdout)
cli("release", "--project", proj, "--session", "sessao-A-5678")
r = cli("claim", "--project", proj, "--session", "sessao-A-5678", "--paths", "docs/**", "--note", "documentacao")
check("area separada: reserva sem conflito", r.returncode == 0, r.stdout)
ctx = context("sessao-B-1234", wt2)
check("e a primeira sessao fica sabendo da area da nova", "sessao-A" in ctx and "documentacao" in ctx, ctx)
st = cli("status", "--project", proj, "--session", "sessao-A-5678").stdout
check("status lista as areas reservadas pelas outras sessoes", "reforma do painel" in st and "src/painel/**" in st, st)

# disparo de fatia: a sessao reserva o scope do Task Contract sozinha
tdir = os.path.join(proj, ".aisef", "contracts", "tasks")
os.makedirs(tdir, exist_ok=True)
write(os.path.join(tdir, "T-050.json"), json.dumps({"task_id": "T-050", "title": "API de pedidos",
                                                     "scope": {"included": ["x"], "excluded": [], "paths_allowed": ["src/api/**"],
                                                               "exclusive_files": ["src/routes.py"]}}))
hook("agent_events.py", {"hook_event_name": "PreToolUse", "tool_name": "Agent", "session_id": "sessao-B-1234", "cwd": wt2,
                         "tool_input": {"subagent_type": "aisef:backend", "description": "T-050: API de pedidos"}}, wt2)
d, why = gate("sessao-A-5678", "Write", proj, file_path=os.path.join(proj, "src", "api", "pedidos.py"), content="x")
check("disparar uma fatia reserva o scope.paths_allowed dela para a sessao", d == "ask" and ("T-050" in why or "API de pedidos" in why), (d, why))
d, why = gate("sessao-A-5678", "Edit", proj, file_path=os.path.join(proj, "src", "routes.py"), old_string="a", new_string="b")
check("e os exclusive_files tambem", d == "ask" and "API de pedidos" in why, (d, why))
cli("release", "--project", wt2, "--session", "sessao-B-1234")
d, why = gate("sessao-A-5678", "Write", proj, file_path=os.path.join(proj, "src", "painel", "x.py"), content="x")
check("release: a area volta a ficar livre", d == "allow", (d, why))
check("areas: globs que se cruzam sobrepoem; pastas irmas nao",
      ses.areas_overlap("src/**", "src/painel/*.py") and ses.areas_overlap("src/painel/", "src/painel/x.py")
      and not ses.areas_overlap("src/painel/**", "docs/**") and not ses.areas_overlap("src/a.py", "src/b.py"))

# ---- worktree de fatia do AISEF (.aisef/worktrees/<T>): da sessao que reservou a fatia
wt9 = os.path.join(proj, ".aisef", "worktrees", "T-090")
git(proj, "worktree", "add", "-q", "-b", "slice/T-090", wt9)
write(os.path.join(wt9, "src", "a.py"), "a = 90  # editado pelo shell, sem registro\n")
check("worktree de fatia sem reserva de outra sessao: e desta sessao, nao pergunta no commit",
      not [f for f in ses.concurrent(proj, "sessao-A-5678", proj) if ses._key(f["worktree"]) == ses._key(wt9)])
ses.claim(proj, "sessao-B-1234", ["src/**"], note="fatia da B", task_id="T-090")
check("worktree de fatia reservada por outra sessao: e dela, entra na lista",
      any(ses._key(f["worktree"]) == ses._key(wt9) and f["sessions"] for f in ses.concurrent(proj, "sessao-A-5678", proj)))
check("sem session_id: nao da para separar o trabalho desta sessao, entao nao lista nada", ses.concurrent(proj, None, proj) == [])

shutil.rmtree(work, ignore_errors=True)
print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
