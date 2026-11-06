#!/usr/bin/env python3
"""Testes do Approval Center no uso real (0.5.0):
- `request` valida o rascunho, anexa approval_requested e grava o pedido ja com a referencia do evento;
- `decide` recusa aprovar o que exige aprovacao reforcada sem uma autorizacao reforcada coerente
  (mesma operation exata), em vez de gravar um pedido aprovado que o gateway continuaria negando;
- a politica e o schema do Approval Center cobrem as mesmas operacoes Git (pull_request incluido)."""
import copy
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_project as ap  # noqa: E402
import check_policy_consistency as pol  # noqa: E402

fails = total = 0


def check(name, cond, detail=None):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name)
    if not cond and detail is not None:
        print("       ", str(detail)[:600])
    fails += not cond


def raises(fn):
    try:
        fn()
    except SystemExit as e:
        return str(e)
    return None


proj = os.path.join(work, "p")
os.makedirs(proj)
ap.init(proj, "PRJ-R", "request", "dev")
root = ap.aisef_dir(proj)
cli = os.path.join(HERE, "aisef_project.py")
ACKS = ["impact_read", "rollback_read", "diff_reviewed"]


def log_len():
    with open(os.path.join(root, "audit", "log.jsonl"), encoding="utf-8") as fh:
        return len([l for l in fh if l.strip()])


def git_request(rid, op, command, destructive):
    d = {
        "schema_version": "0.1.0", "request_id": rid, "request_type": "git_operation", "status": "pending",
        "title": "Operacao Git %s" % op, "summary": "Executar %s na branch da feature depois do merge do PR." % command,
        "requested_by": {"type": "orchestrator", "id": "orchestrator"},
        "project_id": "PRJ-R", "feature_id": "FEAT-1", "task_id": "T-1",
        "created_at": ap.now_iso(), "expires_at": ap.iso_in(minutes=30),
        "operation": {"environment": "dev", "resource_class": "git", "operation": command,
                      "destructive": destructive, "sensitive_content_shown": False},
        "git": {"operation": op, "branch": "feat/x", "covers_only_this_operation": True},
        "presented": {"impact": "Remove a branch feat/x ja integrada", "rollback_plan": "Recriar a branch a partir do commit de merge",
                      "justification": "Branch da feature ja integrada em main", "diff_ref": "git log main..feat/x (vazio)",
                      "evidence_ids": []},
        "risk": {"level": "medium", "items": []},
        "blocks": {"blocked_task_ids": [], "independent_work_continues": True},
        "policy_version": "0.1.0",
    }
    if destructive:
        d.update(validity_minutes=30, required_acknowledgements=ACKS)
    return d


def reinforced_draft(aid, command):
    return {"schema_version": "0.1.0", "kind": "reinforced", "approval_id": aid, "project_id": "PRJ-R", "feature_id": "FEAT-1",
            "task_id": "T-1", "requested_by_agent": "orchestrator", "environment": "dev", "resource_class": "git",
            "operation": command, "destructive": True,
            "presented": {"plan_or_diff_ref": "git log main..feat/x (vazio)", "impact": "Remove a branch feat/x ja integrada",
                          "rollback_plan": "Recriar a branch a partir do commit de merge", "justification": "Branch ja integrada"},
            "single_use": True, "scope_authorization_reused": False, "validity_minutes": 30,
            "issued_at": ap.now_iso(), "expires_at": ap.iso_in(minutes=30), "policy_version": "0.1.0"}


def write_tmp(name, doc):
    path = os.path.join(work, name)
    ap.write_json(path, doc)
    return path


print("--- request: cria o pedido pendente com o evento")
draft = git_request("APR-001", "branch_delete", "git push origin --delete feat/x", True)
n0 = log_len()
req = ap.request(proj, write_tmp("d1.json", draft))
saved = json.load(open(os.path.join(root, "approvals", "APR-001.json"), encoding="utf-8"))
log = [json.loads(l) for l in open(os.path.join(root, "audit", "log.jsonl"), encoding="utf-8") if l.strip()]
ev = log[-1]
check("request grava o pedido com requested_event_ref apontando para approval_requested",
      log_len() == n0 + 1 and ev["event_type"] == "approval_requested" and saved["audit"]["requested_event_ref"] == "events/%d" % ev["sequence"]
      and ev.get("feature_id") == "FEAT-1" and ev.get("task_id") == "T-1" and ev["data"]["request_id"] == "APR-001", saved)
check("pedido gravado valido no schema", not ap.validate(saved, "approval-request.schema.v0.1.json"))
n0 = log_len()
check("request recusa id que ja existe, sem evento", raises(lambda: ap.request(proj, write_tmp("d1b.json", draft))) and log_len() == n0)
bad = dict(copy.deepcopy(draft), request_id="APR-002", status="approved")
check("request recusa rascunho ja decidido (so cria pendente), sem evento",
      raises(lambda: ap.request(proj, write_tmp("d2.json", bad))) and log_len() == n0
      and not os.path.exists(os.path.join(root, "approvals", "APR-002.json")))
bad = dict(copy.deepcopy(draft), request_id="APR-003")
bad.pop("presented")
msg = raises(lambda: ap.request(proj, write_tmp("d3.json", bad)))
check("request recusa rascunho invalido no schema, sem evento", msg and "presented" in msg and log_len() == n0, msg)
bad = dict(copy.deepcopy(draft), request_id="APR-004", project_id="OUTRO")
check("request recusa pedido de outro projeto", raises(lambda: ap.request(proj, write_tmp("d4.json", bad))) and log_len() == n0)
r = subprocess.run([sys.executable, "-I", cli, "request", "--project", proj, "--file",
                    write_tmp("d5.json", git_request("APR-005", "commit", "git commit -m x", False))],
                   capture_output=True, text=True, env=dict(os.environ))
check("CLI request grava e informa o evento", r.returncode == 0 and "APR-005" in r.stdout
      and os.path.exists(os.path.join(root, "approvals", "APR-005.json")), r.stdout + r.stderr)

print("--- decide: aprovacao reforcada exige autorizacao reforcada coerente")
n0 = log_len()
msg = raises(lambda: ap.decide(proj, "APR-001", "approve", ack=ACKS))
still = json.load(open(os.path.join(root, "approvals", "APR-001.json"), encoding="utf-8"))
check("branch_delete aprovado sem --authorization e recusado, nada gravado",
      msg and "reforcada" in msg and still["status"] == "pending" and log_len() == n0, msg)
msg = raises(lambda: ap.decide(proj, "APR-001", "approve", ack=ACKS,
                               authorization_draft=write_tmp("a1.json", reinforced_draft("RA-1", "git push origin --delete outra"))))
check("autorizacao reforcada com outra operation e recusada",
      msg and "operation" in msg and log_len() == n0 and not os.path.exists(os.path.join(root, "authorizations", "RA-1.json")), msg)
scope_draft = {"kind": "scope", "authorization_id": "AUTH-X"}
msg = raises(lambda: ap.decide(proj, "APR-001", "approve", ack=ACKS, authorization_draft=write_tmp("a2.json", scope_draft)))
check("autorizacao de escopo nao serve para operacao reforcada", msg and log_len() == n0, msg)
other = reinforced_draft("RA-2", "git push origin --delete feat/x")
other["task_id"] = "T-9"
msg = raises(lambda: ap.decide(proj, "APR-001", "approve", ack=ACKS, authorization_draft=write_tmp("a3.json", other)))
check("autorizacao reforcada de outra tarefa e recusada", msg and log_len() == n0, msg)
done = ap.decide(proj, "APR-001", "approve", ack=ACKS,
                 authorization_draft=write_tmp("a4.json", reinforced_draft("RA-3", "git push origin --delete feat/x")))
auth = json.load(open(os.path.join(root, "authorizations", "RA-3.json"), encoding="utf-8"))
check("com a autorizacao coerente: aprovado e autorizacao reforcada gerada",
      done["status"] == "approved" and done["resulting_ref"] == {"kind": "reinforced_approval", "id": "RA-3"}
      and auth["status"] == "approved" and auth["operation"] == "git push origin --delete feat/x")
ap.request(proj, write_tmp("d6.json", git_request("APR-006", "branch_delete", "git branch -d feat/x", True)))
check("recusar operacao reforcada nao exige autorizacao", ap.decide(proj, "APR-006", "reject")["status"] == "rejected")
check("git commit (nao reforcado) aprova sem autorizacao", ap.decide(proj, "APR-005", "approve")["status"] == "approved")

print("--- politica x schemas: operacoes Git")
P = json.load(open(os.path.join(HERE, "permission-policy.v0.1.json"), encoding="utf-8"))
AUTH = json.load(open(os.path.join(HERE, "authorization.schema.v0.1.json"), encoding="utf-8"))
APR = json.load(open(os.path.join(HERE, "approval-request.schema.v0.1.json"), encoding="utf-8"))
AGENT = json.load(open(os.path.join(HERE, "agent-contract.schema.v0.1.json"), encoding="utf-8"))
check("politica atual consistente", pol.check(P, AUTH, APR) == [], pol.check(P, AUTH, APR))
check("pull_request na politica (aprovacao por operacao)", P["matrix"]["git"].get("pull_request") == "approve_operation")
p2 = copy.deepcopy(P)
p2["matrix"]["git"]["tag_sign"] = "approve_operation"
check("operacao Git da politica sem tipo no Approval Center e conflito",
      any("tag_sign" in c for c in pol.check(p2, AUTH, APR)), pol.check(p2, AUTH, APR))
a2 = copy.deepcopy(APR)
a2["properties"]["git"]["properties"]["operation"]["enum"].remove("pull_request")
check("operacao da politica que o schema nao aceita (pull_request) e conflito", any("pull_request" in c for c in pol.check(P, AUTH, a2)))
check("Agent Contract aceita pull_request no teto Git",
      "pull_request" in AGENT["properties"]["permission_ceiling"]["properties"]["git_operations"]["items"]["enum"])
check("orquestrador pode pedir pull_request", "pull_request" in ap.AGENT_PROFILES["orchestrator"][4])
check("regra nativa de segunda camada para gh pr create", "Bash(gh pr create:*)" in ap.NATIVE_ASK_RULES)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
