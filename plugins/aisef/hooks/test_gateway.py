#!/usr/bin/env python3
"""Testes do Execution Gateway e do hook de auditoria: cada caso envia o JSON de hook pelo stdin
e exige a decisao esperada (allow = sem decisao, ask, deny)."""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "core"))
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_project  # noqa: E402

proj = os.path.join(work, "proj")
os.makedirs(proj)
aisef_project.init(proj, "PRJ-T", "Projeto de teste", "dev")
fails = total = 0


def run(script, payload, project=proj):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=project)
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, script)], input=json.dumps(payload),
                       capture_output=True, text=True, encoding="utf-8", env=env, timeout=30)
    return r


def decision(tool, _agent=None, **inp):
    payload = {"tool_name": tool, "tool_input": inp, "cwd": proj}
    if _agent:
        payload["agent_type"] = _agent
    r = run("gateway.py", payload)
    if not r.stdout.strip():
        return "allow", ""
    out = json.loads(r.stdout)["hookSpecificOutput"]
    return out["permissionDecision"], out["permissionDecisionReason"]


def case(name, tool, expected, _agent=None, **inp):
    global fails, total
    total += 1
    got, reason = decision(tool, _agent, **inp)
    ok = got == expected
    print(("OK    " if ok else "FALHA ") + "%s -> %s" % (name, got))
    if not ok:
        print("      ", reason)
    fails += not ok


print("--- git (cada operacao exige a propria aprovacao)")
case("git status", "Bash", "allow", command="git status")
case("git log | diff", "Bash", "allow", command="git log --oneline -5 && git diff HEAD~1")
case("git branch (listar)", "Bash", "allow", command="git branch -a")
case("git commit", "Bash", "ask", command='git commit -m "feat: x"')
case("git push", "Bash", "ask", command="git push origin main")
case("git merge", "Bash", "ask", command="git merge feature/x")
case("git tag (release)", "Bash", "ask", command="git tag v1.0.0")
case("gh release create", "Bash", "ask", command="gh release create v1.0.0")
case("git add && git commit em cadeia", "Bash", "ask", command="git add . && git commit -m wip")
case("force push: reforcada sem aprovacao -> deny", "Bash", "deny", command="git push --force origin main")
case("commit --amend reescreve historico -> deny", "Bash", "deny", command="git commit --amend --no-edit")
case("reset --hard -> deny", "Bash", "deny", command="git reset --hard HEAD~3")
case("apagar branch -> deny", "Bash", "deny", command="git branch -D feature/x")
case("subcomando git nao classificado -> ask", "Bash", "ask", command="git stash")

print("--- banco e segredos (ambiente desconhecido = producao)")
case("psql -> deny", "Bash", "deny", command="psql -h db -U app")
case("connection string -> deny", "Bash", "deny", command="node x.js postgres://u@h/db")
case("prisma migrate -> deny", "Bash", "deny", command="npx prisma migrate deploy")
case("docker exec -> deny", "Bash", "deny", command="docker exec -it db bash")
case("terraform apply -> deny", "Bash", "deny", command="terraform apply -auto-approve")
case("cat .env -> ask (aprovacao por operacao em dev)", "Bash", "ask", command="cat .env")
case("printenv -> ask", "Bash", "ask", command="printenv")
case("Read .env -> ask", "Read", "ask", file_path=os.path.join(proj, ".env"))
case("Read .env.example -> allow", "Read", "allow", file_path=os.path.join(proj, ".env.example"))
case("Read id_rsa -> ask", "Read", "ask", file_path="/home/u/.ssh/id_rsa")
case("Write .env -> ask", "Write", "ask", file_path=os.path.join(proj, ".env"))

print("--- codigo, config e destrutivos")
case("Edit codigo -> allow", "Edit", "allow", file_path=os.path.join(proj, "src", "app.py"))
case("Read codigo -> allow", "Read", "allow", file_path=os.path.join(proj, "src", "app.py"))
case("npm test -> allow", "Bash", "allow", command="npm test")
case("Edit workflow de CI sem escopo -> ask", "Edit", "ask", file_path=os.path.join(proj, ".github", "workflows", "ci.yml"))
case("Write Dockerfile sem escopo -> ask", "Write", "ask", file_path=os.path.join(proj, "Dockerfile"))
case("rm -rf (T1 em dev) -> ask", "Bash", "ask", command="rm -rf build/")

print("--- protecao do proprio AISEF")
case("Edit no log de auditoria -> deny", "Edit", "deny", file_path=os.path.join(proj, ".aisef", "audit", "log.jsonl"))
case("Bash escrevendo no log -> deny", "Bash", "deny", command="echo {} >> .aisef/audit/log.jsonl")
case("verificar o log -> allow", "Bash", "allow", command="python audit_chain.py verify .aisef/audit/log.jsonl")
case("Write em approvals -> ask", "Write", "ask", file_path=os.path.join(proj, ".aisef", "approvals", "APR-1.json"))
case("Write em authorizations -> ask", "Write", "ask", file_path=os.path.join(proj, ".aisef", "authorizations", "AUTH-1.json"))
case("Write em contrato de feature -> allow", "Write", "allow", file_path=os.path.join(proj, ".aisef", "contracts", "features", "FEAT-1.json"))
case("registrar evento como usuario -> ask", "Bash", "ask", command="python aisef_project.py append --type approval_granted --actor user --summary ok")

print("--- autorizacao de escopo e aprovacao reforcada")
now = datetime.datetime.now(datetime.timezone.utc)
iso = lambda d: (now + d).isoformat()
scope = {"schema_version": "0.1.0", "kind": "scope", "authorization_id": "AUTH-9", "project_id": "PRJ-T",
         "feature_id": "FEAT-1", "cycle": 1, "environment": "dev", "resources": ["config_ci_iac"],
         "operations": ["edit_files"], "limits": {"max_operations": 10},
         "validity": {"valid_from": iso(datetime.timedelta(hours=-1)), "valid_until": iso(datetime.timedelta(hours=1))},
         "status": "active"}
aisef_project.write_json(os.path.join(proj, ".aisef", "authorizations", "AUTH-9.json"), scope)
scope["validity"]["valid_until"] = iso(datetime.timedelta(days=8))
aisef_project.write_json(os.path.join(proj, ".aisef", "authorizations", "AUTH-9.json"), scope)
case("escopo acima de 7 dias nao vale -> ask", "Edit", "ask", file_path=os.path.join(proj, ".github", "workflows", "ci.yml"))
scope["validity"]["valid_until"] = iso(datetime.timedelta(hours=1))
aisef_project.write_json(os.path.join(proj, ".aisef", "authorizations", "AUTH-9.json"), scope)
case("CI coberto por escopo ativo -> allow", "Edit", "allow", file_path=os.path.join(proj, ".github", "workflows", "ci.yml"))
scope["validity"]["valid_until"] = iso(datetime.timedelta(minutes=-1))
aisef_project.write_json(os.path.join(proj, ".aisef", "authorizations", "AUTH-9.json"), scope)
case("escopo expirado -> ask", "Edit", "ask", file_path=os.path.join(proj, ".github", "workflows", "ci.yml"))
reinf = {"kind": "reinforced", "approval_id": "RA-1", "operation": "git push --force origin main",
         "status": "approved", "expires_at": iso(datetime.timedelta(minutes=20))}
aisef_project.write_json(os.path.join(proj, ".aisef", "authorizations", "RA-1.json"), reinf)
case("force push com reforcada aprovada para a operacao exata -> ask", "Bash", "ask", command="git push --force origin main")
case("reforcada nao cobre outra operacao -> deny", "Bash", "deny", command="git push --force origin dev")
reinf["consumed"] = {"at": iso(datetime.timedelta(0)), "operation_event_ref": "E9"}
aisef_project.write_json(os.path.join(proj, ".aisef", "authorizations", "RA-1.json"), reinf)
case("reforcada ja usada -> deny", "Bash", "deny", command="git push --force origin main")

print("--- Approval Center")
import make_demo_project  # noqa: E402
demo = os.path.join(work, "demo")
make_demo_project.make(demo)
pending = json.load(open(os.path.join(demo, "approvals", "APR-001.json"), encoding="utf-8"))
case("propor pedido novo e pendente -> allow", "Write", "allow",
     file_path=os.path.join(proj, ".aisef", "approvals", "APR-001.json"), content=json.dumps(pending))
case("pedido ja decidido escrito pelo agente -> ask", "Write", "ask",
     file_path=os.path.join(proj, ".aisef", "approvals", "APR-001.json"), content=json.dumps(dict(pending, status="approved")))
case("decidir pedido -> ask (prompt nativo)", "Bash", "ask",
     command="python aisef_project.py decide --project . --request APR-001 --choice approve")
aisef_project.write_json(os.path.join(proj, ".aisef", "approvals", "APR-001.json"), pending)
case("reescrever pedido existente, mesmo pendente -> ask", "Write", "ask",
     file_path=os.path.join(proj, ".aisef", "approvals", "APR-001.json"), content=json.dumps(pending))
draft = json.load(open(os.path.join(demo, "authorizations", "AUTH-1.json"), encoding="utf-8"))
for k in ("status", "granted_by", "granted_at"):
    draft.pop(k, None)
draft.update(authorization_id="AUTH-2", history=[])
draft_path = os.path.join(work, "draft.json")
aisef_project.write_json(draft_path, draft)
req = aisef_project.decide(proj, "APR-001", "approve", note="ok", authorization_draft=draft_path)
auth = json.load(open(os.path.join(proj, ".aisef", "authorizations", "AUTH-2.json"), encoding="utf-8"))
total += 1
ok = (req["status"] == "approved" and req["resulting_ref"] == {"kind": "scope_authorization", "id": "AUTH-2"}
      and auth["status"] == "active" and auth["granted_by"] == "user" and not aisef_project.validate(req, "approval-request.schema.v0.1.json")
      and not aisef_project.validate(auth, "authorization.schema.v0.1.json"))
print(("OK    " if ok else "FALHA ") + "decide: pedido aprovado, autorizacao de escopo gerada, ambos validos no schema")
fails += not ok
total += 1
try:
    aisef_project.decide(proj, "APR-001", "reject")
    ok = False
except SystemExit:
    ok = True
print(("OK    " if ok else "FALHA ") + "decisao tomada nao muda (novo pedido e necessario)")
fails += not ok
for f in ("APR-001.json",):
    os.remove(os.path.join(proj, ".aisef", "approvals", f))
os.remove(os.path.join(proj, ".aisef", "authorizations", "AUTH-2.json"))

print("--- T1 ampliada (decisao de 2026-11-05)")
case("git clean -fdx -> ask (destrutivo em dev)", "Bash", "ask", command="git clean -fdx")
case("git checkout -- arquivo -> ask", "Bash", "ask", command="git checkout -- src/app.py")
case("git restore -> ask", "Bash", "ask", command="git restore src/app.py")
case("git stash drop -> ask", "Bash", "ask", command="git stash drop")
case("docker volume rm -> ask", "Bash", "ask", command="docker volume rm dados")
case("docker compose down -v -> ask", "Bash", "ask", command="docker compose down -v")
case("kubectl delete -> deny (ambiente desconhecido)", "Bash", "deny", command="kubectl delete ns app")
case("terraform destroy -> deny", "Bash", "deny", command="terraform destroy")

print("--- teto do Agent Contract nos subagentes")
case("agente em draft -> deny", "Edit", "deny", _agent="aisef:backend", file_path=os.path.join(proj, "src", "app.py"))
aisef_project.activate_agents(proj)
case("backend ativo edita codigo -> allow", "Edit", "allow", _agent="aisef:backend", file_path=os.path.join(proj, "src", "app.py"))
case("backend pode solicitar commit -> ask", "Bash", "ask", _agent="aisef:backend", command="git commit -m x")
case("backend nao pode push (fora do teto) -> deny", "Bash", "deny", _agent="aisef:backend", command="git push")
case("backend le .env (fora do teto) -> deny", "Read", "deny", _agent="aisef:backend", file_path=os.path.join(proj, ".env"))
case("validator: git status -> allow", "Bash", "allow", _agent="aisef:validator", command="git status")
case("validator: git commit -> deny (Git so leitura)", "Bash", "deny", _agent="aisef:validator", command="git commit -m x")
case("subagente registrando decisao do usuario -> deny", "Bash", "deny", _agent="aisef:backend",
     command="python aisef_project.py decide --request APR-1 --choice approve")
case("subagente sem Agent Contract segue so a politica", "Bash", "ask", _agent="Explore", command="git commit -m x")
case("ativar agentes -> ask (decisao do usuario)", "Bash", "ask", command="python aisef_project.py agents --project . --activate")
case("editar Agent Contract -> ask", "Edit", "ask", file_path=os.path.join(proj, ".aisef", "contracts", "agents", "qa.json"))

print("--- politica local e falha fechada")
aisef_project.write_json(os.path.join(proj, ".aisef", "policy.local.json"), {"matrix": {"git": {"status_log_diff": "approve_operation"}}})
case("politica local pode endurecer (status vira ask)", "Bash", "ask", command="git status")
aisef_project.write_json(os.path.join(proj, ".aisef", "policy.local.json"), {"matrix": {"git": {"push": "allow"}}})
case("politica local NAO pode afrouxar (push continua ask)", "Bash", "ask", command="git push")
os.remove(os.path.join(proj, ".aisef", "policy.local.json"))
with open(os.path.join(proj, ".aisef", "config.json"), "a", encoding="utf-8") as fh:
    fh.write("lixo")
case("config corrompido -> deny (falha fechada)", "Bash", "deny", command="npm test")
with open(os.path.join(proj, ".aisef", "config.json"), encoding="utf-8") as fh:
    fixed = fh.read().rsplit("lixo", 1)[0]
with open(os.path.join(proj, ".aisef", "config.json"), "w", encoding="utf-8") as fh:
    fh.write(fixed)
total += 1
r = run("gateway.py", {"tool_name": "Bash", "tool_input": {"command": "psql"}}, project=os.path.join(work, "outro"))
ok = r.returncode == 0 and not r.stdout.strip()
print(("OK    " if ok else "FALHA ") + "projeto sem .aisef: gateway nao interfere")
fails += not ok

print("--- hook de auditoria")
for payload in ({"tool_name": "Bash", "tool_input": {"command": "npm test"}, "session_id": "s1"},
                {"tool_name": "Edit", "tool_input": {"file_path": os.path.join(proj, "src", "app.py")}},
                {"tool_name": "Bash", "tool_input": {"command": "curl -H 'Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456' x"}}):
    run("audit_hook.py", payload)
log = [json.loads(line) for line in open(os.path.join(proj, ".aisef", "audit", "log.jsonl"), encoding="utf-8")]
errors, warnings = aisef_project.verify(proj)


def check(name, cond):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name)
    fails += not cond


tools = [e for e in log if e["event_type"] == "tool_used"]
check("eventos do Approval Center registrados pelo usuario",
      [(e["event_type"], e["actor"]["type"]) for e in log[1:3]] == [("approval_granted", "user"), ("authorization_granted", "user")])
check("3 eventos tool_used anexados", len(tools) == 3 and log[0]["event_type"] == "genesis")
check("caminho gravado relativo ao projeto", tools[1]["data"]["file"] == "src/app.py")
check("comando com token nao vai para o log", "abcdefghijklmnop" not in json.dumps(log) and tools[2]["data"]["command"].startswith("[omitido"))
check("nenhum evento registra raciocinio do modelo", all(e["contains_model_reasoning"] is False for e in log))
check("cadeia e assinaturas integras (head externo)", not errors)
check("head externo fica fora do projeto", os.path.exists(aisef_project.external_head_path("PRJ-T"))
      and not aisef_project.external_head_path("PRJ-T").startswith(proj))
check("chave privada fica fora do projeto", os.path.exists(aisef_project.private_key_path("PRJ-T"))
      and not any(f.endswith(".pem") and "PRIVATE" in open(os.path.join(dp, f), encoding="utf-8").read()
                  for dp, _, fs in os.walk(proj) for f in fs))
lines = open(os.path.join(proj, ".aisef", "audit", "log.jsonl"), encoding="utf-8").read().splitlines()
with open(os.path.join(proj, ".aisef", "audit", "log.jsonl"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines[:-1]) + "\n")
errors, _ = aisef_project.verify(proj)
check("truncar o fim do log e detectado pelo head externo", any("truncado" in e for e in errors))

shutil.rmtree(work, ignore_errors=True)
print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
