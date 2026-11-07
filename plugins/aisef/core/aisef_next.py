#!/usr/bin/env python3
"""AISEF: proximas acoes do orquestrador no modo continuo (0.5.0). Usado por `aisef_project.py next`.

Le contratos, aprovacoes, relatorios e o log de auditoria e devolve o que fazer agora, sem executar nada:

    dispatch             onda atual de tarefas prontas, com os comandos de rota (modelo/effort) e de pack
    validate             tarefa executed sem task_validated (validacao independente)
    complete             tarefa validated sem task_completed (o orquestrador aceita e integra)
    wait                 tarefas em andamento (delegadas ou iniciadas): esperar a notificacao do agente
    await_decision       decisao humana pendente: pedido pending, scope_discovery sem pedido, intervencao
                         pedida em relatorio, limite de tentativas atingido ou risco critico
    feature_acceptance   feature com todas as tarefas concluidas e sem pedido de aceite
    create_branch        (git.branch_per_feature) a feature vai comecar fora da branch dela
    delete_merged_branch (git.delete_branch_after_merge) feature aceita com a branch ainda local
    idle                 nada a fazer

`stop_reason` diz quando o loop deve parar: critical_risk (para na hora), attempts_exhausted e
user_decision_pending (so quando nao resta trabalho automatizavel), nothing_ready (idle). None = seguir.

Estado efetivo da tarefa: o do contrato combinado com o ultimo evento de ciclo de vida no log
(delegation/task_started/task_resumed -> in_progress, task_paused -> blocked, task_executed -> executed,
task_validated -> validated, task_rejected -> rejected, task_completed -> completed). O log costuma estar
a frente do contrato; cancelled e blocked no contrato prevalecem.
"""
import copy
import datetime
import glob
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_project as ap  # noqa: E402
import audit_chain  # noqa: E402

EVENT_STATE = {"delegation": "in_progress", "task_started": "in_progress", "task_resumed": "in_progress",
               "task_paused": "blocked", "task_executed": "executed", "task_validated": "validated",
               "task_rejected": "rejected", "task_completed": "completed"}
RANK = {"draft": 0, "ready": 1, "rejected": 1, "in_progress": 2, "executed": 3, "validated": 4, "completed": 5}
DONE = ("completed", "cancelled")
ACCEPTED_FEATURE_STATES = ("closed",)
DEFAULTS_PATH = os.path.join(HERE, "orchestration-defaults.v0.1.json")


def _load_dir(project, sub):
    out = []
    for f in sorted(glob.glob(os.path.join(ap.aisef_dir(project), sub, "*.json"))):
        try:
            with open(f, encoding="utf-8") as fh:
                out.append(json.load(fh))
        except (OSError, ValueError):
            continue
    return out


def _parse(ts):
    try:
        return datetime.datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


def effective_state(contract_status, event_status):
    if contract_status in ("cancelled", "blocked") or event_status is None:
        return contract_status
    if contract_status == "completed":
        return "completed"
    if event_status == "rejected":
        return "rejected"
    return event_status if RANK.get(event_status, 0) >= RANK.get(contract_status, 0) else contract_status


def feature_branch(feature_id, prefix="feat/"):
    """FEAT-LOGIN -> feat/login (id sem o prefixo FEAT-, minusculas, so [a-z0-9-])."""
    slug = re.sub(r"^feat[-_]", "", feature_id.strip(), flags=re.I).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-") or "feature"
    return prefix + slug


def git_state(project):
    """Branch atual e branches locais (somente leitura). Fora de um repositorio: {current: None, branches: None}."""
    def run(*args):
        try:
            r = subprocess.run(["git", "-C", project] + list(args), capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.SubprocessError):
            return None
        return r.stdout if r.returncode == 0 else None
    cur = run("rev-parse", "--abbrev-ref", "HEAD")
    if cur is None:
        return {"current": None, "branches": None}
    heads = run("for-each-ref", "--format=%(refname:short)", "refs/heads")
    return {"current": cur.strip(), "branches": set((heads or "").split())}


def _cmd(script, *args):
    return 'python -I "%s" %s' % (os.path.join(HERE, script), " ".join(args))


def compute_next(project, feature=None, now=None, git_state=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    cfg = ap.load_config(project)
    gitcfg, _problems = ap.git_settings(cfg)
    feats = {f["feature_id"]: f for f in _load_dir(project, "contracts/features")}
    tasks = {t["task_id"]: t for t in _load_dir(project, "contracts/tasks")}
    approvals = _load_dir(project, "approvals")
    reports = _load_dir(project, "reports")
    log = audit_chain.read_log_dir(os.path.join(ap.aisef_dir(project), "audit"))
    try:
        with open(DEFAULTS_PATH, encoding="utf-8") as fh:
            default_limit = json.load(fh)["failure_handling"]["max_fix_attempts"]
    except (OSError, ValueError, KeyError):
        default_limit = 3

    def in_scope(fid):
        return feature is None or fid == feature

    # ---- estado efetivo a partir do log
    ev_state, rejections, started_at, last_started = {}, {}, {}, {}
    for e in log:
        tid = e.get("task_id")
        if tid and e["event_type"] in EVENT_STATE:
            ev_state[tid] = EVENT_STATE[e["event_type"]]
            if e["event_type"] == "task_rejected":
                rejections[tid] = rejections.get(tid, 0) + 1
            if e["event_type"] in ("task_started", "delegation"):
                started_at.setdefault(tid, e["timestamp"])
                last_started[tid] = _parse(e["timestamp"])
    state = {tid: effective_state(t["state"]["status"], ev_state.get(tid)) for tid, t in tasks.items()}

    actions, decisions, blocked, critical, warnings = [], [], {}, [], []

    def block(tid, why):
        blocked.setdefault(tid, why)

    # ---- pedidos pendentes
    for a in approvals:
        if a.get("status") != "pending" or not in_scope(a.get("feature_id")):
            continue
        tids = list(a.get("blocks", {}).get("blocked_task_ids", []))
        for tid in tids:
            block(tid, "aguarda %s" % a["request_id"])
        exp = _parse(a.get("expires_at"))
        decisions.append({"kind": "await_decision", "source": "approval", "request_id": a["request_id"],
                          "request_type": a.get("request_type"), "feature_id": a.get("feature_id"),
                          "title": a.get("title"), "task_ids": tids,
                          "independent_work_continues": a.get("blocks", {}).get("independent_work_continues", True),
                          "expired": bool(exp and exp < now)})

    # ---- scope_discovery sem pedido registrado depois (mesma feature)
    for i, e in enumerate(log):
        if e["event_type"] != "scope_discovery" or not in_scope(e.get("feature_id")):
            continue
        later = log[i + 1:]
        if any(x["event_type"] in ("approval_requested", "decision_recorded") and x.get("feature_id") == e.get("feature_id")
               for x in later):
            continue
        tids = [e["task_id"]] if e.get("task_id") else []
        for tid in tids:
            block(tid, "scope_discovery %s sem decisao" % e["event_id"])
        decisions.append({"kind": "await_decision", "source": "scope_discovery", "event_id": e["event_id"],
                          "feature_id": e.get("feature_id"), "title": e.get("summary"), "task_ids": tids,
                          "independent_work_continues": True,
                          "hint": "crie um pedido scope_change_decision (aisef_project.py request) e leve ao usuario"})

    # ---- intervencao pedida no relatorio mais recente de cada tarefa aberta
    latest = {}
    for r in reports:
        tid = r.get("task_id")
        fin = _parse((r.get("timing") or {}).get("finished_at"))
        if tid in tasks and fin and (tid not in latest or fin >= latest[tid][0]):
            latest[tid] = (fin, r)
    for tid, (fin, r) in sorted(latest.items()):
        t = tasks[tid]
        if state[tid] in DONE or not in_scope(t.get("feature_id")):
            continue
        if last_started.get(tid) and last_started[tid] > fin:
            continue  # tarefa ja redespachada depois do relatorio
        inter = r.get("intervention") if isinstance(r.get("intervention"), dict) else {}
        risks = r.get("risks") if isinstance(r.get("risks"), list) else []
        if not isinstance(r.get("intervention"), (dict, type(None))) or any(not isinstance(x, dict) for x in risks):
            warnings.append("relatorio %s fora do schema (risks/intervention): rode o aisef-check e corrija o relatorio"
                            % r.get("report_id"))
        is_critical = inter.get("reason") == "critical_risk_operation" or any(
            isinstance(x, dict) and x.get("severity") == "critical" for x in risks)
        if not (inter.get("needed") or is_critical):
            continue
        block(tid, "intervencao pedida em %s" % r.get("report_id"))
        item = {"kind": "await_decision", "source": "critical_risk" if is_critical else "intervention",
                "report_id": r.get("report_id"), "feature_id": t.get("feature_id"), "task_ids": [tid],
                "reason": inter.get("reason"), "title": inter.get("details") or "intervencao pedida pelo agente",
                "independent_work_continues": not is_critical}
        (critical if is_critical else decisions).append(item)

    # ---- tentativas
    exhausted = []
    for tid, t in sorted(tasks.items()):
        if not in_scope(t.get("feature_id")) or state[tid] != "rejected":
            continue
        n = max(t["state"].get("rejection_count", 0) or 0, rejections.get(tid, 0))
        limit = (t.get("limits") or {}).get("max_fix_attempts") or default_limit
        if n > limit:
            block(tid, "limite de %d correcoes atingido" % limit)
            exhausted.append({"kind": "await_decision", "source": "attempts_exhausted", "feature_id": t.get("feature_id"),
                              "task_ids": [tid], "title": "%s reprovada %d vez(es); limite %d" % (tid, n, limit),
                              "independent_work_continues": True,
                              "hint": "escale ao usuario: mudar o contrato, trocar de agente ou cancelar"})

    # ---- validate e complete
    def executor_level(tid):
        agent = tasks[tid]["assigned_agent"]["agent_id"]
        prof = [r for r in reports if r.get("task_id") == tid and r.get("agent", {}).get("agent_id") == agent
                and r.get("execution_profile")]
        return prof[-1]["execution_profile"]["level"] if prof else None

    validate, complete, wait = [], [], []
    for tid, t in sorted(tasks.items()):
        if not in_scope(t.get("feature_id")) or tid in blocked:
            continue
        if state[tid] == "executed":
            lvl = executor_level(tid)
            validate.append({"kind": "validate", "task_id": tid, "feature_id": t.get("feature_id"),
                             "route_cmd": _cmd("aisef_route.py", "--project . --task %s --validator --executor-level %s"
                                               % (tid, "L%d" % lvl if lvl is not None else "<nivel do executor>"))})
        elif state[tid] == "validated":
            complete.append({"kind": "complete", "task_id": tid, "feature_id": t.get("feature_id"),
                             "append_cmd": _cmd("aisef_project.py", 'append --project . --type task_completed --feature %s '
                                                '--task %s --summary "%s concluida e integrada"' % (t.get("feature_id"), tid, tid))})
        elif state[tid] == "in_progress":
            wait.append(tid)

    # ---- dispatch: ondas sobre o estado efetivo (reprovada = pronta para retrabalho; bloqueada fica fora)
    sim = []
    for tid, t in tasks.items():
        c = copy.deepcopy(t)
        st = state[tid]
        if tid in blocked and st not in DONE:
            st = "blocked"
        elif st == "rejected":
            st = "ready"
        c["state"]["status"] = st
        sim.append(c)
    deferred = []
    try:
        waves = ap.compute_waves(sim, feature)
        wave_error = None
    except ap.WaveError as e:
        waves, wave_error = {"waves": [], "deferred": []}, str(e)
    deferred.extend(d for d in waves["deferred"] if d.get("wave") is None or d.get("wave") == 1)
    flying = [tasks[x] for x in wait]
    dispatch = []
    if waves["waves"]:
        for item in waves["waves"][0]["tasks"]:
            tid = item["task_id"]
            clash = next((o["task_id"] for o in flying if ap.tasks_conflict(o, tasks[tid])), None)
            if clash:
                deferred.append({"task": tid, "reason": "conflito com %s, em andamento" % clash, "wave": 1})
                continue
            attempt = (max(tasks[tid]["state"].get("rejection_count", 0) or 0, rejections.get(tid, 0)) + 1
                       if state[tid] == "rejected" else 1)
            dispatch.append({
                "task_id": tid, "feature_id": item["feature_id"], "title": item["title"], "role": item["role"],
                "agent_id": item["agent_id"], "attempt": attempt, "paths": item["paths"],
                "route_cmd": _cmd("aisef_route.py", "--project . --task %s%s" % (tid, " --attempt %d" % attempt if attempt > 1 else "")),
                "pack_cmd": _cmd("aisef_context.py", "pack --project . --task %s" % tid)})
    for tid, why in sorted(blocked.items()):
        if in_scope(tasks.get(tid, {}).get("feature_id")) and state.get(tid) not in DONE:
            deferred.append({"task": tid, "reason": why, "wave": None})

    # ---- aceite da feature
    acceptance = []
    accepted = set()
    for fid, f in sorted(feats.items()):
        if not in_scope(fid):
            continue
        cycle = (f.get("cycle") or {}).get("number", 1)
        reqs = sorted((a for a in approvals if a.get("request_type") == "feature_acceptance" and a.get("feature_id") == fid
                       and a.get("cycle", 1) == cycle), key=lambda a: a.get("created_at") or "")
        if (f.get("state", {}).get("status") in ACCEPTED_FEATURE_STATES
                or (f.get("approval", {}).get("acceptance") or {}).get("status") == "accepted"
                or any(a.get("status") == "approved" for a in reqs)):
            accepted.add(fid)
            continue
        if f.get("state", {}).get("status") == "cancelled":
            continue
        plan = [x["task_id"] for x in f.get("task_plan", [])] or [t for t, d in tasks.items() if d.get("feature_id") == fid]
        if not plan or not all(state.get(t) in DONE for t in plan) or not any(state.get(t) == "completed" for t in plan):
            continue
        if any(a.get("status") == "pending" for a in reqs):
            continue  # ja aparece em await_decision
        if reqs and reqs[-1].get("status") in ("rejected", "changes_requested"):
            decisions.append({"kind": "await_decision", "source": "acceptance_changes_requested", "feature_id": fid,
                              "request_id": reqs[-1]["request_id"], "task_ids": [], "independent_work_continues": True,
                              "title": "aceite de %s voltou como %s" % (fid, reqs[-1]["status"]),
                              "hint": "reabra com novo ciclo (aisef-feature) e leve o novo plano ao usuario"})
            continue
        acceptance.append({"kind": "feature_acceptance", "feature_id": fid,
                           "hint": "monte o relatorio final e crie o pedido feature_acceptance (aisef_project.py request)"})

    # ---- branch por feature
    branch_actions, cleanup = [], []
    gs = git_state if git_state is not None else (git_state_fn(project) if gitcfg["branch_per_feature"] or gitcfg["delete_branch_after_merge"] else None)
    if gs and gs.get("current") is not None:
        if gitcfg["branch_per_feature"]:
            for fid in sorted({d["feature_id"] for d in dispatch}):
                if any(tasks[t].get("feature_id") == fid for t in started_at):
                    continue  # a feature ja comecou: a branch foi decidida antes
                b = feature_branch(fid, gitcfg["branch_prefix"])
                if gs["current"] == b:
                    continue
                exists = b in (gs.get("branches") or set())
                branch_actions.append({"kind": "create_branch", "feature_id": fid, "branch": b,
                                       "command": ("git switch %s" if exists else "git switch -c %s") % b,
                                       "hint": "rode antes de despachar a primeira onda da feature"})
        if gitcfg["delete_branch_after_merge"]:
            for fid in sorted(accepted):
                b = feature_branch(fid, gitcfg["branch_prefix"])
                if b not in (gs.get("branches") or set()):
                    continue
                ops = []
                for scope, command in (("remote", "git push %s --delete %s" % (gitcfg["remote"], b)),
                                       ("local", "git branch -d %s" % b)):
                    req = next((a for a in approvals if a.get("request_type") in ("git_operation", "reinforced_approval")
                                and (a.get("operation") or {}).get("operation", "").strip() == command), None)
                    ops.append({"scope": scope, "command": command,
                                "request": {"request_id": req["request_id"], "status": req["status"]} if req else None})
                cleanup.append({"kind": "delete_merged_branch", "feature_id": fid, "branch": b, "operations": ops,
                                "requires": "merge do PR confirmado pelo usuario (gh pr view %s --json state,mergedAt)" % b,
                                "hint": "cada exclusao e operacao Git reforcada: um pedido git_operation branch_delete "
                                        "+ autorizacao reforcada com a operation exata"
                                        + ("; saia da branch antes (git switch <base>)" if gs["current"] == b else "")})

    if dispatch:
        dispatch_actions = [{"kind": "dispatch", "wave": 1, "tasks": dispatch}]
    else:
        dispatch_actions = []
    wait_actions = [{"kind": "wait", "task_ids": wait,
                     "hint": "aguarde a notificacao dos agentes em background antes do proximo ciclo"}] if wait else []

    automatable = complete + validate + acceptance + branch_actions + dispatch_actions
    actions = critical + exhausted + decisions + complete + validate + acceptance + branch_actions + dispatch_actions + wait_actions + cleanup
    if critical:
        stop, detail = "critical_risk", "risco critico: pare na hora e leve ao usuario"
    elif automatable or wait:
        stop, detail = None, None
    elif exhausted:
        stop, detail = "attempts_exhausted", "limite de tentativas atingido: escale ao usuario"
    elif decisions:
        stop, detail = "user_decision_pending", "so restam decisoes do usuario (aisef-approve)"
    elif cleanup:
        stop, detail = "user_decision_pending", "limpeza de branch depende de confirmacao e aprovacao do usuario"
    else:
        stop, detail = "nothing_ready", "nada pronto para executar"
    if not actions:
        actions = [{"kind": "idle"}]
    return {"feature": feature, "actions": actions, "stop_reason": stop, "stop_detail": detail,
            "deferred": deferred, "wave_error": wave_error, "warnings": warnings,
            "states": {tid: state[tid] for tid in sorted(state) if in_scope(tasks[tid].get("feature_id"))}}


git_state_fn = git_state


def format_next(res):
    lines = ["Proximas acoes%s:" % (" (%s)" % res["feature"] if res["feature"] else "")]
    for a in res["actions"]:
        k = a["kind"]
        if k == "dispatch":
            lines.append("- dispatch (onda %d, %d tarefa(s) em paralelo)" % (a["wave"], len(a["tasks"])))
            for t in a["tasks"]:
                lines.append("    %s [%s] %s (tentativa %d)" % (t["task_id"], t["agent_id"], t["title"], t["attempt"]))
                lines.append("      rota: %s" % t["route_cmd"])
                lines.append("      pack: %s" % t["pack_cmd"])
        elif k in ("validate", "complete"):
            lines.append("- %s %s: %s" % (k, a["task_id"], a.get("route_cmd") or a.get("append_cmd")))
        elif k == "wait":
            lines.append("- wait: em andamento %s" % ", ".join(a["task_ids"]))
        elif k == "await_decision":
            ref = a.get("request_id") or a.get("event_id") or a.get("report_id") or ""
            lines.append("- await_decision [%s] %s %s%s" % (a["source"], ref, a.get("title") or "",
                                                           " (bloqueia %s)" % ", ".join(a["task_ids"]) if a.get("task_ids") else ""))
        elif k == "feature_acceptance":
            lines.append("- feature_acceptance %s: %s" % (a["feature_id"], a["hint"]))
        elif k == "create_branch":
            lines.append("- create_branch %s: %s" % (a["feature_id"], a["command"]))
        elif k == "delete_merged_branch":
            lines.append("- delete_merged_branch %s (%s)" % (a["branch"], a["requires"]))
            for o in a["operations"]:
                lines.append("    %s: %s%s" % (o["scope"], o["command"],
                                               " [pedido %s: %s]" % (o["request"]["request_id"], o["request"]["status"]) if o["request"] else ""))
        else:
            lines.append("- " + k)
    if res["deferred"]:
        lines.append("Fora da onda atual:")
        for d in res["deferred"]:
            lines.append("  %s: %s" % (d["task"], d["reason"]))
    if res.get("wave_error"):
        lines.append("ERRO nas ondas: " + res["wave_error"])
    for w in res.get("warnings", []):
        lines.append("AVISO " + w)
    lines.append("stop_reason: %s%s" % (res["stop_reason"], " (%s)" % res["stop_detail"] if res["stop_detail"] else ""))
    return "\n".join(lines)
