#!/usr/bin/env python3
"""Git por risco (F-03, ADR 0025): commit e preparo livres na branch de feature, push da feature pelo escopo dela,
main/merge/release/force como antes. A branch vem do .git/HEAD (simulado aqui, sem rodar git)."""
import datetime
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "core"))
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_git  # noqa: E402
import aisef_project as ap  # noqa: E402
import check_project as cp  # noqa: E402
import gateway  # noqa: E402

fails = total = 0


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)))
    fails += not cond


proj = os.path.join(work, "proj")
os.makedirs(os.path.join(proj, ".git"))
ap.init(proj, "PRJ-GIT")
policy = gateway.load_json(gateway.POLICY_PATH)
patterns = gateway.load_patterns()
now = datetime.datetime.now(datetime.timezone.utc)


def head(branch):
    with open(os.path.join(proj, ".git", "HEAD"), "w", encoding="utf-8") as fh:
        fh.write(("ref: refs/heads/%s\n" % branch) if branch else "3f2a9c0d1e\n")


def decide(cmd, agent=None, env="dev"):
    cfg = gateway.load_json(os.path.join(proj, ".aisef", "config.json"))
    cfg["environment"] = env
    data = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": proj}
    if agent:
        data["agent_type"] = agent
    try:
        d, r = gateway.decide(data, proj, policy, patterns, cfg, now)
        return d or "allow"
    except gateway.Decision as e:
        return e.level


# ------------------------------------------------------------------ aisef_git
check("branch pelo .git/HEAD", (head("feat/login"), aisef_git.current_branch(proj))[1] == "feat/login")
check("branch de dentro de uma subpasta", aisef_git.current_branch(os.path.join(proj, ".aisef")) == "feat/login")
check("HEAD solto: branch desconhecida", (head(None), aisef_git.current_branch(proj))[1] is None)
wt = os.path.join(work, "wt")
os.makedirs(os.path.join(work, "gitdirs", "wt"))
os.makedirs(wt)
open(os.path.join(wt, ".git"), "w").write("gitdir: %s\n" % os.path.join(work, "gitdirs", "wt"))
open(os.path.join(work, "gitdirs", "wt", "HEAD"), "w").write("ref: refs/heads/feat/wt\n")
check("worktree: segue o gitdir do arquivo .git", aisef_git.current_branch(wt) == "feat/wt")
check("sem repositorio: None", aisef_git.current_branch(os.path.join(work, "home")) is None)
check("feat/x e de feature; main, feat/ vazio e release/x nao",
      aisef_git.is_feature_branch("feat/x") and not aisef_git.is_feature_branch("main")
      and not aisef_git.is_feature_branch("feat/") and not aisef_git.is_feature_branch("release/x", "release/"))
check("alvos do push: sem refspec = branch atual", aisef_git.push_targets(["origin"], "feat/a") == [("feat/a", "feat/a")])
check("alvos do push: HEAD:feat/a", aisef_git.push_targets(["origin", "HEAD:feat/a"], "feat/a") == [("feat/a", "feat/a")])
check("alvos do push: feat/a:main", aisef_git.push_targets(["-u", "origin", "feat/a:main"], "feat/a") == [("feat/a", "main")])
check("alvos do push: -o valor nao vira remoto", aisef_git.push_targets(["-o", "ci.skip", "origin", "feat/a"], "x")
      == [("feat/a", "feat/a")])

# ------------------------------------------------------------------ commit e preparo
head("feat/login")
check("commit em feat/x -> allow", decide('git commit -m "feat: login"') == "allow")
check("git add e switch -c -> allow", decide("git add -A && git switch -c feat/outra") == "allow")
check("checkout -b -> allow", decide("git checkout -b feat/nova") == "allow")
check("checkout de arquivo continua destrutivo -> ask", decide("git checkout -- src/a.py") == "ask")
check("commit --amend continua reforcado -> deny", decide("git commit --amend --no-edit") == "deny")
check("commit em feat/x com --no-verify -> deny", decide("git commit --no-verify -m x") == "deny")
check("commit em feat/x no ambiente prod -> nao e livre", decide('git commit -m "x"', env="prod") != "allow")
head("main")
check("commit em main -> ask", decide('git commit -m "x"') == "ask")
head(None)
check("branch indetectavel (HEAD solto) -> ask", decide('git commit -m "x"') == "ask")
head("feat/login")
check("cd no comando: branch desconhecida -> ask", decide('cd ../outro && git commit -m "x"') == "ask")
check("git -C outro repo: branch desconhecida -> ask", decide('git -C ../outro commit -m "x"') == "ask")

# ------------------------------------------------------------------ push
check("push de feat/x sem escopo -> ask", decide("git push -u origin feat/login") == "ask")
check("push sem refspec (branch atual) sem escopo -> ask", decide("git push") == "ask")


def scope(branches, resources=("git_feature_branch",), env="dev", status="active"):
    t0 = now - datetime.timedelta(hours=1)
    doc = {"schema_version": "0.1.0", "kind": "scope", "authorization_id": "AUTH-GIT-1", "project_id": "PRJ-GIT",
           "feature_id": "FEAT-001", "cycle": 1, "environment": env, "resources": list(resources), "operations": ["push"],
           "resource_filters": {"branches": branches}, "limits": {"max_operations": 100},
           "excludes_destructive_operations": True,
           "validity": {"valid_from": t0.isoformat(), "valid_until": (t0 + datetime.timedelta(days=5)).isoformat()},
           "termination_condition": ["expiry", "feature_accepted"],
           "stop_conditions": ["scope_exceeded", "environment_changed", "unexpected_risk", "architectural_decision_needed",
                               "mandatory_approval_needed"], "policy_version": policy["policy_version"],
           "status": status, "granted_by": "user", "granted_at": t0.isoformat(), "revocable": True,
           "history": [{"event": "granted", "at": t0.isoformat(), "by": "user"}]}
    if status == "revoked":
        doc["revocation"] = {"revoked_at": now.isoformat(), "revoked_by": "user", "reason": "teste"}
    if not branches:
        doc.pop("resource_filters")
    ap.write_json(os.path.join(proj, ".aisef", "authorizations", "AUTH-GIT-1.json"), doc)
    return doc


doc = scope(["feat/login"])
problems = ap.validate(doc, "authorization.schema.v0.1.json")
check("autorizacao de escopo com git_feature_branch e valida no schema", problems == [], problems)
check("push de feat/x com escopo -> allow", decide("git push -u origin feat/login") == "allow")
check("push sem refspec com escopo -> allow", decide("git push") == "allow")
check("push HEAD:feat/x com escopo -> allow", decide("git push origin HEAD:feat/login") == "allow")
check("feat/x:main -> ask", decide("git push origin feat/login:main") == "ask")
check("push de outra branch de feature fora do escopo -> ask", decide("git push origin feat/outra") == "ask")
check("push --force -> deny", decide("git push --force origin feat/login") == "deny")
check("push --tags -> nao e livre", decide("git push --tags") != "allow")
check("subagente nao faz push da feature -> deny", decide("git push", agent="aisef:implementer") == "deny")
for role in ("implementer", "validator"):
    p = os.path.join(proj, ".aisef", "contracts", "agents", role + ".json")
    d = json.load(open(p, encoding="utf-8"))
    d["status"] = "active"
    ap.write_json(p, d)
check("implementer (contrato antigo com 'commit') commita na feature -> allow",
      decide('git commit -m "x"', agent="aisef:implementer") == "allow")
check("validator (so leitura de Git) nao prepara commit -> deny", decide("git add -A", agent="aisef:validator") == "deny")
scope(["feat/*"])
check("escopo com glob feat/* cobre a outra branch de feature", decide("git push origin feat/outra") == "allow")
scope([])
check("escopo sem filtro de branches nao cobre push -> ask", decide("git push") == "ask")
scope(["feat/login"], status="revoked")
check("escopo revogado -> ask", decide("git push") == "ask")


def rules():
    rep = cp.check(proj, policy_path=gateway.POLICY_PATH,
                   defaults_path=os.path.join(os.path.dirname(HERE), "core", "orchestration-defaults.v0.1.json"))
    return {f["rule"] for f in rep.findings if f["severity"] == "error"}


scope(["main"])
check("check: escopo de push para main -> AUTH-GIT-BRANCH", "AUTH-GIT-BRANCH" in rules())
scope([])
check("check: escopo de push sem branches -> AUTH-GIT-BRANCH", "AUTH-GIT-BRANCH" in rules())
scope(["feat/login"])
check("check: escopo de push de feat/x sem AUTH-GIT-BRANCH", "AUTH-GIT-BRANCH" not in rules())

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
