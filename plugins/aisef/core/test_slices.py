#!/usr/bin/env python3
"""L-02: worktree por fatia, de ponta a ponta com git de verdade. Duas fatias editam o mesmo arquivo: entram na mesma
onda, cada uma no seu worktree; a primeira integra pelo escopo da feature; a segunda da conflito, vira nova tentativa
e reaproveita o worktree. O gateway decide cada comando. Sem git no PATH, o teste e pulado."""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(os.path.dirname(HERE), "hooks")
sys.path.insert(0, HERE)
sys.path.insert(0, HOOKS)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_new as an  # noqa: E402
import aisef_next as nx  # noqa: E402
import aisef_project as ap  # noqa: E402
import check_project as cp  # noqa: E402
import gateway  # noqa: E402

fails = total = 0


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)[:500]))
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
open(os.path.join(proj, "src", "shared.py"), "w").write("VALOR = 0\n")
ap.init(proj, "PRJ-SL")
ap.activate_agents(proj)
cfg = ap.load_config(proj)
cfg["parallel"] = {"mode": "worktree"}
ap.write_json(os.path.join(proj, ".aisef", "config.json"), cfg)
check(".aisef/.gitignore do init ignora worktrees/", "worktrees/" in open(os.path.join(proj, ".aisef", ".gitignore")).read())
git(proj, "add", "-A")
git(proj, "commit", "-qm", "init")
git(proj, "switch", "-qc", "feat/010")
SPEC = {"solution": "Duas mudancas no mesmo modulo", "user_stories": ["Como dev quero duas fatias"], "test_seams": ["VALOR"]}
an.cmd_feature(proj, {"id": "FEAT-010", "title": "Duas fatias", "objective": "Testar fatias em paralelo no mesmo arquivo",
                      "problem": "Fatias com arquivo em comum ficavam em ondas separadas",
                      "requirements": {"REQ-1": "Primeira mudanca", "REQ-2": "Segunda mudanca"}, "scope_in": ["shared"],
                      "spec": SPEC,
                      "tasks": [{"id": "T-1", "title": "primeira mudanca em shared", "reqs": ["REQ-1"], "criteria": {"AC-1": "testes da primeira"},
                                 "paths": ["src/shared.py"], "parallelizable": True},
                                {"id": "T-2", "title": "segunda mudanca em shared", "reqs": ["REQ-2"], "criteria": {"AC-2": "testes da segunda"},
                                 "paths": ["src/shared.py"], "parallelizable": True}]})
apr = os.path.join(proj, ".aisef", "approvals", "APR-001.json")
ap.write_json(apr, dict(json.load(open(apr, encoding="utf-8")), status="approved"))
for tid in ("T-1", "T-2"):
    tp = os.path.join(proj, ".aisef", "contracts", "tasks", tid + ".json")
    ap.write_json(tp, dict(json.load(open(tp, encoding="utf-8")), state={"status": "ready"}))
GS = {"current": "feat/010", "branches": {"main", "feat/010"}}


def dispatched(res):
    return {t["task_id"]: t for a in res["actions"] if a["kind"] == "dispatch" for t in a["tasks"]}


d = dispatched(nx.compute_next(proj, git_state=GS))
check("modo worktree: duas fatias com o mesmo arquivo na mesma onda", set(d) == {"T-1", "T-2"}, list(d))
check("cada fatia traz worktree, branch e o comando de criar", d["T-1"]["worktree"]["path"] == ".aisef/worktrees/T-1"
      and d["T-1"]["worktree"]["branch"] == "slice/010/T-1" and d["T-1"]["worktree"]["create_cmd"].startswith("git worktree add"),
      d["T-1"].get("worktree"))
cfg["parallel"] = {"mode": "paths"}
ap.write_json(os.path.join(proj, ".aisef", "config.json"), cfg)
check("modo paths (padrao): a segunda fatia fica para a onda seguinte", set(dispatched(nx.compute_next(proj, git_state=GS))) == {"T-1"})
cfg["parallel"] = {"mode": "worktree"}
ap.write_json(os.path.join(proj, ".aisef", "config.json"), cfg)

policy = gateway.load_json(gateway.POLICY_PATH)
patterns = gateway.load_patterns()
now = datetime.datetime.now(datetime.timezone.utc)


def decide(cmd, agent=None):
    data = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": proj}
    if agent:
        data["agent_type"] = agent
    try:
        r, _why = gateway.decide(data, proj, policy, patterns, ap.load_config(proj), now)
        return r or "allow"
    except gateway.Decision as e:
        return e.level


for tid in ("T-1", "T-2"):
    c = d[tid]["worktree"]["create_cmd"]
    check("gateway: criar o worktree de %s e livre" % tid, decide(c) == "allow")
    check("criou o worktree de %s" % tid, git(proj, *c.split()[1:]).returncode == 0)
open(os.path.join(proj, ".aisef", "worktrees", "T-1", "src", "shared.py"), "w").write("VALOR = 1\n")
open(os.path.join(proj, ".aisef", "worktrees", "T-2", "src", "shared.py"), "w").write("VALOR = 2\n")
for tid in ("T-1", "T-2"):
    w = ".aisef/worktrees/%s" % tid
    check("gateway: implementer commita no worktree da fatia (branch slice) sem prompt",
          decide("git -C %s add -A && git -C %s commit -m x" % (w, w), agent="aisef:implementer") == "allow")
    git(proj, "-C", w, "add", "-A")
    git(os.path.join(proj, w), "commit", "-qm", "fatia %s" % tid)
check("cd para o worktree tambem le a branch da fatia", decide('cd .aisef/worktrees/T-1 && git commit -m "x"') == "allow")
check("cd para fora do projeto: branch desconhecida, commit pede", decide('cd .. && git commit -m "x"') == "ask")

# integrar T-1: sem escopo pede; com o escopo da feature passa
cmds = nx.integrate_cmds("FEAT-010", "T-1")["commands"]
check("integrar a fatia sem escopo -> ask", decide(cmds[0]) == "ask")
t0 = now - datetime.timedelta(hours=1)
ap.write_json(os.path.join(proj, ".aisef", "authorizations", "AUTH-GIT.json"), {
    "schema_version": "0.1.0", "kind": "scope", "authorization_id": "AUTH-GIT", "project_id": "PRJ-SL",
    "feature_id": "FEAT-010", "cycle": 1, "environment": "dev", "resources": ["git_feature_branch"],
    "operations": ["push", "merge"], "resource_filters": {"branches": ["feat/010"]}, "limits": {"max_operations": 100},
    "excludes_destructive_operations": True,
    "validity": {"valid_from": t0.isoformat(), "valid_until": (t0 + datetime.timedelta(days=5)).isoformat()},
    "termination_condition": ["expiry"], "stop_conditions": ["scope_exceeded", "environment_changed", "unexpected_risk",
                                                             "architectural_decision_needed", "mandatory_approval_needed"],
    "policy_version": policy["policy_version"], "status": "active", "granted_by": "user", "granted_at": t0.isoformat(),
    "revocable": True, "history": [{"event": "granted", "at": t0.isoformat(), "by": "user"}]})
check("integrar a fatia com o escopo da feature -> allow", decide(cmds[0]) == "allow")
check("remover o worktree e apagar a branch da fatia integrada (-d) -> allow", decide(cmds[1]) == "allow" and decide(cmds[2]) == "allow")
check("apagar a branch da fatia a forca (-D) continua reforcado", decide("git branch -D slice/010/T-1") == "deny")
check("subagente nao integra (sem push no teto)", decide(cmds[0], agent="aisef:implementer") == "deny")
r = git(proj, "merge", "--no-ff", "slice/010/T-1", "-m", "integra T-1")
check("T-1 integrada sem conflito", r.returncode == 0, r.stdout + r.stderr)
git(proj, "worktree", "remove", ".aisef/worktrees/T-1")
git(proj, "branch", "-d", "slice/010/T-1")

# T-2 conflita
r = git(proj, "merge", "--no-ff", "slice/010/T-2", "-m", "integra T-2")
check("T-2 conflita ao integrar (mesma linha)", r.returncode != 0)
check("git merge --abort -> allow", decide("git merge --abort") == "allow")
git(proj, "merge", "--abort")
ap.append(proj, {"event_type": "task_executed", "actor": {"type": "agent", "id": "implementer"}, "feature_id": "FEAT-010",
                 "task_id": "T-2", "summary": "T-2 executada"})
ap.append(proj, {"event_type": "task_rejected", "actor": {"type": "orchestrator", "id": "orchestrator"}, "feature_id": "FEAT-010",
                 "task_id": "T-2", "summary": "T-2: conflito ao integrar", "data": {"merge_conflict": True}})
d = dispatched(nx.compute_next(proj, git_state=GS))
check("conflito vira nova tentativa da fatia, reaproveitando o worktree",
      "T-2" in d and d["T-2"]["attempt"] == 2 and d["T-2"]["worktree"]["exists"] and d["T-2"]["worktree"]["create_cmd"] is None, d.get("T-2"))
check("trazer a feature para a fatia, no worktree -> allow (local)", decide(d["T-2"]["worktree"]["sync_cmd"]) == "allow")
check("push da branch da fatia continua pedindo", decide("git push origin slice/010/T-2") == "ask")

cfg["parallel"] = {"mode": "lado-a-lado"}
ap.write_json(os.path.join(proj, ".aisef", "config.json"), cfg)
check("check: parallel.mode invalido -> CONFIG-PARALLEL", any(
    f["rule"] == "CONFIG-PARALLEL" for f in cp.check(proj, policy_path=gateway.POLICY_PATH).findings))

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
