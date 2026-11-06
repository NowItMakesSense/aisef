#!/usr/bin/env python3
"""Testes do modo continuo (0.5.0): `aisef_project.py next` e a opcao git.branch_per_feature.

O `next` le contratos, aprovacoes, relatorios e o log e devolve as proximas acoes do orquestrador,
com um `stop_reason` quando o loop precisa parar para uma decisao humana."""
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
import aisef_next as nx  # noqa: E402

fails = total = 0


def check(name, cond, detail=None):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name)
    if not cond and detail is not None:
        print("       ", json.dumps(detail, ensure_ascii=False)[:900])
    fails += not cond


def task(tid, deps=(), paths=None, status="ready", feature="FEAT-LOGIN", agent="backend", limit=None, rejections=0):
    return {
        "task_id": tid, "feature_id": feature, "title": "Tarefa " + tid, "contract_version": 1,
        "assigned_agent": {"agent_id": agent, "agent_contract_version": 1, "role": agent},
        "scope": {"included": ["x"], "excluded": [], "paths_allowed": ["src/%s/**" % tid] if paths is None else list(paths)},
        "dependencies": {"depends_on": list(deps), "parallelizable": True, "shared_resources": []},
        "limits": {"max_fix_attempts": limit},
        "risk": {"level": "low"},
        "state": {"status": status, "rejection_count": rejections},
    }


def feature(fid="FEAT-LOGIN", tids=(), plan="approved", status="in_execution", cycle=1):
    return {"feature_id": fid, "title": "Feature " + fid, "cycle": {"number": cycle},
            "task_plan": [{"task_id": t} for t in tids],
            "approval": {"plan": {"status": plan}}, "state": {"status": status}}


def new_project(name, feats, tasks, config_extra=None):
    proj = os.path.join(work, name)
    os.makedirs(proj)
    ap.init(proj, "PRJ-" + name.upper(), name, "dev")
    root = ap.aisef_dir(proj)
    for f in feats:
        ap.write_json(os.path.join(root, "contracts", "features", f["feature_id"] + ".json"), f)
    for t in tasks:
        ap.write_json(os.path.join(root, "contracts", "tasks", t["task_id"] + ".json"), t)
    if config_extra:
        cfg = ap.load_config(proj)
        cfg.update(config_extra)
        ap.write_json(os.path.join(root, "config.json"), cfg)
    return proj


def ev(proj, etype, task_id=None, feature_id="FEAT-LOGIN", actor=("orchestrator", "orchestrator"), **extra):
    partial = {"event_type": etype, "actor": {"type": actor[0], "id": actor[1]}, "summary": "%s %s" % (etype, task_id or "")}
    if task_id:
        partial["task_id"] = task_id
    if feature_id:
        partial["feature_id"] = feature_id
    partial.update(extra)
    return ap.append(proj, partial)


def approval(proj, rid, rtype, status="pending", blocked=(), feature_id="FEAT-LOGIN", **extra):
    doc = {"request_id": rid, "request_type": rtype, "status": status, "feature_id": feature_id,
           "title": "Pedido " + rid, "created_at": ap.now_iso(), "expires_at": ap.iso_in(days=1),
           "blocks": {"blocked_task_ids": list(blocked), "independent_work_continues": True}}
    doc.update(extra)
    ap.write_json(os.path.join(ap.aisef_dir(proj), "approvals", rid + ".json"), doc)


def kinds(res):
    return [a["kind"] for a in res["actions"]]


def action(res, kind):
    return [a for a in res["actions"] if a["kind"] == kind]


def dispatched(res):
    return [t["task_id"] for a in action(res, "dispatch") for t in a["tasks"]]


NOGIT = {"current": None, "branches": None}

print("--- dispatch, validate, complete")
p = new_project("ciclo", [feature(tids=["T-1", "T-2", "T-3"])],
                [task("T-1"), task("T-2", deps=["T-1"]), task("T-3")])
r = nx.compute_next(p, git_state=NOGIT)
check("plano aprovado: dispatch da onda atual (T-1 e T-3; T-2 espera T-1)", dispatched(r) == ["T-1", "T-3"] and r["stop_reason"] is None, r)
d = action(r, "dispatch")[0]["tasks"][0]
check("dispatch traz comando de rota e de pack da tarefa",
      "aisef_route.py" in d["route_cmd"] and "--task T-1" in d["route_cmd"] and "aisef_context.py" in d["pack_cmd"]
      and "pack" in d["pack_cmd"] and d["attempt"] == 1 and d["agent_id"] == "backend", d)

ev(p, "delegation", "T-1")
r = nx.compute_next(p, git_state=NOGIT)
check("delegada sem task_started ja conta como em andamento (nao e despachada de novo)",
      dispatched(r) == ["T-3"] and action(r, "wait") and action(r, "wait")[0]["task_ids"] == ["T-1"], r)

ev(p, "task_started", "T-1", actor=("agent", "backend"))
ev(p, "task_executed", "T-1", actor=("agent", "backend"))
r = nx.compute_next(p, git_state=NOGIT)
v = action(r, "validate")
check("executed sem task_validated vira 'validate' com rota do validador",
      [a["task_id"] for a in v] == ["T-1"] and "--validator" in v[0]["route_cmd"], r)

ev(p, "task_validated", "T-1", actor=("validator", "validator"))
r = nx.compute_next(p, git_state=NOGIT)
c = action(r, "complete")
check("validated sem task_completed vira 'complete'", [a["task_id"] for a in c] == ["T-1"] and "task_completed" in c[0]["append_cmd"], r)
check("validada libera a dependente (T-2 entra na onda)", "T-2" in dispatched(r), r)

ev(p, "task_completed", "T-1")
r = nx.compute_next(p, git_state=NOGIT)
check("concluida some das acoes", not any(a.get("task_id") == "T-1" for a in r["actions"]) and "T-1" not in dispatched(r), r)

print("--- retrabalho e limite de tentativas")
ev(p, "delegation", "T-3")
ev(p, "task_started", "T-3", actor=("agent", "backend"))
ev(p, "task_executed", "T-3", actor=("agent", "backend"))
ev(p, "task_rejected", "T-3", actor=("validator", "validator"))
r = nx.compute_next(p, git_state=NOGIT)
t3 = [t for a in action(r, "dispatch") for t in a["tasks"] if t["task_id"] == "T-3"]
check("reprovada volta para dispatch com --attempt 2", t3 and t3[0]["attempt"] == 2 and "--attempt 2" in t3[0]["route_cmd"], r)

p2 = new_project("limite", [feature(tids=["T-1"])], [task("T-1", limit=2)])
for _ in range(3):
    ev(p2, "task_started", "T-1", actor=("agent", "backend"))
    ev(p2, "task_executed", "T-1", actor=("agent", "backend"))
    ev(p2, "task_rejected", "T-1", actor=("validator", "validator"))
r = nx.compute_next(p2, git_state=NOGIT)
check("acima do limite de correcoes: nao despacha, escala e para (attempts_exhausted)",
      not dispatched(r) and r["stop_reason"] == "attempts_exhausted"
      and any(a.get("source") == "attempts_exhausted" and "T-1" in a["task_ids"] for a in action(r, "await_decision")), r)

print("--- decisoes humanas")
p3 = new_project("decisao", [feature(tids=["T-1", "T-2"])], [task("T-1"), task("T-2")])
approval(p3, "APR-001", "scope_authorization", blocked=["T-2"])
r = nx.compute_next(p3, git_state=NOGIT)
aw = action(r, "await_decision")
check("pedido pendente bloqueia so a tarefa citada; o resto continua",
      dispatched(r) == ["T-1"] and aw and aw[0]["request_id"] == "APR-001" and aw[0]["task_ids"] == ["T-2"]
      and r["stop_reason"] is None, r)
ev(p3, "delegation", "T-1")
ev(p3, "task_started", "T-1", actor=("agent", "backend"))
ev(p3, "task_executed", "T-1", actor=("agent", "backend"))
ev(p3, "task_validated", "T-1", actor=("validator", "validator"))
ev(p3, "task_completed", "T-1")
r = nx.compute_next(p3, git_state=NOGIT)
check("so restam decisoes do usuario: stop_reason user_decision_pending",
      r["stop_reason"] == "user_decision_pending" and kinds(r) == ["await_decision"], r)

p4 = new_project("descoberta", [feature(tids=["T-1", "T-2"])], [task("T-1"), task("T-2")])
ev(p4, "scope_discovery", "T-2", summary="T-2 precisa de tabela nao prevista")
r = nx.compute_next(p4, git_state=NOGIT)
sd = [a for a in action(r, "await_decision") if a["source"] == "scope_discovery"]
check("scope_discovery sem pedido correspondente: aguarda decisao e bloqueia a tarefa",
      sd and sd[0]["task_ids"] == ["T-2"] and dispatched(r) == ["T-1"], r)
ev(p4, "approval_requested", None, summary="APR-001 aguardando decisao")
r = nx.compute_next(p4, git_state=NOGIT)
check("scope_discovery com pedido registrado depois nao aparece mais",
      not [a for a in action(r, "await_decision") if a["source"] == "scope_discovery"], r)

p5 = new_project("critico", [feature(tids=["T-1", "T-2"])], [task("T-1"), task("T-2")])
ev(p5, "delegation", "T-1")
ev(p5, "task_started", "T-1", actor=("agent", "backend"))
ap.write_json(os.path.join(ap.aisef_dir(p5), "reports", "RPT-001.json"), {
    "report_id": "RPT-001", "task_id": "T-1", "agent": {"agent_id": "backend", "agent_contract_version": 1},
    "status": "needs_intervention", "timing": {"started_at": ap.now_iso(), "finished_at": ap.now_iso()},
    "risks": [], "intervention": {"needed": True, "reason": "critical_risk_operation", "details": "migration apaga dados"}})
r = nx.compute_next(p5, git_state=NOGIT)
check("risco critico em relatorio: para na hora (critical_risk), mesmo com trabalho pronto",
      r["stop_reason"] == "critical_risk" and any(a.get("source") == "critical_risk" for a in action(r, "await_decision")), r)

print("--- paralelismo com tarefas em voo")
p6 = new_project("voo", [feature(tids=["T-1", "T-2", "T-3"])],
                 [task("T-1", paths=["src/api/**"]), task("T-2", paths=["src/api/users.py"]), task("T-3", paths=["web/**"])])
ev(p6, "delegation", "T-1")
r = nx.compute_next(p6, git_state=NOGIT)
check("tarefa com paths em conflito com uma em andamento nao e despachada",
      dispatched(r) == ["T-3"] and any(d["task"] == "T-2" for d in r["deferred"]), r)

print("--- aceite da feature")
p7 = new_project("aceite", [feature(tids=["T-1"])], [task("T-1", status="completed")])
r = nx.compute_next(p7, git_state=NOGIT)
check("todas concluidas e sem pedido de aceite: feature_acceptance", kinds(r) == ["feature_acceptance"]
      and r["stop_reason"] is None and action(r, "feature_acceptance")[0]["feature_id"] == "FEAT-LOGIN", r)
approval(p7, "APR-009", "feature_acceptance")
r = nx.compute_next(p7, git_state=NOGIT)
check("aceite pedido e pendente: aguarda o usuario", r["stop_reason"] == "user_decision_pending"
      and not action(r, "feature_acceptance"), r)
approval(p7, "APR-009", "feature_acceptance", status="approved")
r = nx.compute_next(p7, git_state=NOGIT)
check("feature aceita e nada mais: idle com stop_reason nothing_ready", kinds(r) == ["idle"] and r["stop_reason"] == "nothing_ready", r)

print("--- filtro por feature")
p8 = new_project("filtro", [feature(tids=["T-1"]), feature("FEAT-OUTRA", tids=["T-9"])],
                 [task("T-1"), task("T-9", feature="FEAT-OUTRA")])
approval(p8, "APR-002", "plan_approval", feature_id="FEAT-OUTRA")
r = nx.compute_next(p8, feature="FEAT-LOGIN", git_state=NOGIT)
check("--feature limita acoes e pedidos a feature", dispatched(r) == ["T-1"] and not action(r, "await_decision"), r)
r = nx.compute_next(p8, git_state=NOGIT)
check("sem filtro: todas as features", dispatched(r) == ["T-1", "T-9"] and action(r, "await_decision"), r)

print("--- branch por feature (git.branch_per_feature)")
GIT = {"git": {"branch_per_feature": True, "delete_branch_after_merge": True, "branch_prefix": "feat/"}}
check("config git valida sem problemas", ap.git_settings(GIT)[1] == [])
check("config git com tipo errado e acusada",
      ap.git_settings({"git": {"branch_per_feature": "sim"}})[1] and ap.git_settings({"git": {"chave": 1}})[1])
check("nome da branch: prefixo + id sem FEAT-, em minusculas", nx.feature_branch("FEAT-LOGIN", "feat/") == "feat/login"
      and nx.feature_branch("FEAT-001 x", "feature/") == "feature/001-x")
p9 = new_project("branch", [feature(tids=["T-1"])], [task("T-1")], GIT)
r = nx.compute_next(p9, git_state={"current": "main", "branches": {"main"}})
cb = action(r, "create_branch")
check("feature comecando com branch_per_feature: create_branch antes do dispatch (sem executar)",
      cb and cb[0]["branch"] == "feat/login" and cb[0]["command"] == "git switch -c feat/login"
      and kinds(r).index("create_branch") < kinds(r).index("dispatch"), r)
r = nx.compute_next(p9, git_state={"current": "feat/login", "branches": {"main", "feat/login"}})
check("ja na branch da feature: nao sugere criar", not action(r, "create_branch"), r)
r = nx.compute_next(p9, git_state={"current": "main", "branches": {"main", "feat/login"}})
check("branch existe mas nao e a atual: sugere trocar (git switch)",
      action(r, "create_branch") and action(r, "create_branch")[0]["command"] == "git switch feat/login", r)
p10 = new_project("semgit", [feature(tids=["T-1"])], [task("T-1")])
r = nx.compute_next(p10, git_state={"current": "main", "branches": {"main"}})
check("sem a opcao no config: nada de branch", not action(r, "create_branch"), r)

p11 = new_project("merge", [feature(tids=["T-1"])], [task("T-1", status="completed")], GIT)
approval(p11, "APR-010", "feature_acceptance", status="approved")
r = nx.compute_next(p11, git_state={"current": "main", "branches": {"main", "feat/login"}})
dm = action(r, "delete_merged_branch")
check("feature aceita com a branch ainda local: sugere apagar remota e local, cada uma com pedido reforcado",
      dm and [o["command"] for o in dm[0]["operations"]] == ["git push origin --delete feat/login", "git branch -d feat/login"]
      and all(o["request"] is None for o in dm[0]["operations"]) and "merge" in dm[0]["requires"], r)
r = nx.compute_next(p11, git_state={"current": "main", "branches": {"main"}})
check("branch local ja apagada: nada a sugerir", not action(r, "delete_merged_branch"), r)

print("--- CLI")
cli = os.path.join(HERE, "aisef_project.py")
pr = subprocess.run([sys.executable, "-I", cli, "next", "--project", p3, "--json"], capture_output=True, text=True, env=dict(os.environ))
j = json.loads(pr.stdout) if pr.returncode == 0 else {}
check("CLI --json devolve acoes e stop_reason", pr.returncode == 0 and j.get("stop_reason") == "user_decision_pending" and j.get("actions"), pr.stdout + pr.stderr)
pr = subprocess.run([sys.executable, "-I", cli, "next", "--project", p, "--feature", "FEAT-LOGIN"], capture_output=True, text=True, env=dict(os.environ))
check("CLI humano lista as acoes", pr.returncode == 0 and "dispatch" in pr.stdout and "T-2" in pr.stdout, pr.stdout + pr.stderr)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
