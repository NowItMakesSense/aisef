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

`guide` diz a fase (discovery, specify, approve_plan, execute, review, decide, done) e o proximo passo com a
skill certa, tambem antes da execucao; mapeia os comandos do Matt Pocock para o equivalente no AISEF.

`stop_reason` diz quando o loop deve parar: critical_risk (para na hora), budget_exhausted (L-01: tempo, tokens ou
despachos da feature passaram do limite; para logo em seguida), attempts_exhausted e
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


# Guia de fases (SDD + TDD). Cada passo cita a skill que o executa. Os nomes do Matt Pocock (plugin
# mattpocock-skills) sao as skills que o modelo pode chamar; to-spec/to-tickets/implement-spec sao so do usuario
# (disable-model-invocation) e por isso o AISEF faz o mesmo papel nas fases Spec e Fatias da aisef-feature.
MATT_EQUIVALENTS = {"/grill-me": "fase Grill (skill grilling)", "/grill-with-docs": "fase Grill + domain-modeling",
                    "/to-spec": "fase Spec da aisef-feature", "/to-tickets": "fase Fatias da aisef-feature",
                    "/implement-spec": "modo continuo (next) com o agente implementer + tdd",
                    "/implement": "modo continuo (next) com o agente implementer + tdd", "/tdd": "skill tdd no implementer",
                    "/code-review": "revisao da feature antes do aceite"}
STEPS = {
    "discovery": ["aisef-discovery: investigar o projeto e gravar .aisef/discovery.md (investigar antes de perguntar)",
                  "aisef-tooling: sugerir skills, plugins e MCPs a partir do discovery"],
    "specify": ["Grill: entrevistar o usuario ate fechar cada ramo da ideia (skill grilling; vocabulario no GLOSSARY.md com domain-modeling)",
                "Spec: aisef-feature fase Spec (solucao, historias, decisoes, seams de teste confirmados com o usuario)",
                "Fatias: aisef-feature fase Fatias (fatias verticais com blocking edges; aisef_new.py feature)",
                "Aprovar o plano: aisef-approve"],
    "approve_plan": ["aisef-approve: apresentar o plano pendente (requisitos, fatias, seams, riscos) e registrar a decisao do usuario"],
    "execute": ["modo continuo: dispatch da onda (implementer com tdd, vermelho antes do verde) -> validador independente -> complete"],
    "review": ["code-review da feature inteira (skill code-review: padroes + aderencia a spec), correcoes como novas tentativas",
               "relatorio final planejado x executado e pedido feature_acceptance (aisef_project.py request)"],
    "decide": ["aisef-approve: levar ao usuario as decisoes pendentes listadas em await_decision"],
    "done": ["Nada pendente. Nova ideia? Comece pelo Grill (skill grilling) e siga Spec -> Fatias."],
}


def tooling_review_due(cfg, approvals, log):
    """Revisao periodica das skills/plugins/MCPs (aisef-tooling secao 8): devida depois de N features aceitas
    (config tooling.review_every, padrao 1) desde a ultima revisao registrada (evidence_recorded com
    data.kind = tooling_review). 0 desliga."""
    every = (cfg.get("tooling") or {}).get("review_every", 1)
    if not isinstance(every, int) or isinstance(every, bool) or every <= 0:
        return False
    reviews = [_parse(e["timestamp"]) for e in log if e["event_type"] == "evidence_recorded"
               and (e.get("data") or {}).get("kind") == "tooling_review"]
    last = max((r for r in reviews if r), default=None)
    accepted = 0
    for a in approvals:
        if a.get("request_type") != "feature_acceptance" or a.get("status") != "approved" or a.get("feature_id") == "FEAT-MAINT":
            continue
        when = _parse((a.get("decision") or {}).get("decided_at") or a.get("created_at"))
        if last is None or (when and when > last):
            accepted += 1
    return accepted >= every


def project_phase(project, feats, tasks, approvals, actions):
    """Em que fase o projeto esta e qual o proximo passo, com a skill certa (inclusive antes da execucao)."""
    kinds = {a["kind"] for a in actions}
    real = {fid: f for fid, f in feats.items() if fid != "FEAT-MAINT"}
    if not os.path.exists(os.path.join(ap.aisef_dir(project), "discovery.md")):
        phase = "discovery"
    elif kinds & {"dispatch", "validate", "complete", "wait", "create_branch"}:
        phase = "execute"
    elif "feature_acceptance" in kinds:
        phase = "review"
    elif any(a.get("request_type") == "plan_approval" for a in actions if a["kind"] == "await_decision"):
        phase = "approve_plan"
    elif "await_decision" in kinds:
        phase = "decide"
    elif not real or all((f.get("state") or {}).get("status") in ACCEPTED_FEATURE_STATES + ("cancelled",) for f in real.values()):
        phase = "specify" if not real else "done"
    else:
        phase = "done"
    compact = phase in ("approve_plan", "review", "decide", "done") and "wait" not in kinds
    return {"phase": phase, "steps": STEPS[phase], "matt_equivalents": MATT_EQUIVALENTS,
            "compact_hint": ("Marco de fase sem agente em voo: bom momento para /compact (o estado esta no disco e o "
                             "AISEF o reinjeta depois)") if compact else None}


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

    # ---- orcamento, falta de progresso e agente parado (L-01, L-06)
    import aisef_budget
    import aisef_runtime
    plimits = aisef_budget.project_limits(cfg)
    budget_stop = []
    usage_runs = aisef_runtime.read_usage(ap.aisef_dir(project))
    for fid, f in sorted(feats.items()):
        if not in_scope(fid) or fid == "FEAT-MAINT":
            continue
        tids = [i["task_id"] for i in f.get("task_plan", []) if i["task_id"] in tasks]
        open_ids = [t for t in tids if state[t] not in DONE]
        if not open_ids:
            continue
        lim = aisef_budget.feature_limits(cfg, f)
        used = aisef_budget.feature_usage(fid, set(tids), log, usage_runs, now)
        over = aisef_budget.exhausted(lim, used)
        if over:
            for t in open_ids:
                block(t, "orcamento da feature esgotado")
            budget_stop.append({"kind": "await_decision", "source": "budget_exhausted", "feature_id": fid,
                                "task_ids": open_ids, "used": used, "limits": {k: lim[k] for k in aisef_budget.KEYS},
                                "title": "%s passou do orcamento: %s" % (fid, ", ".join(
                                    "%s %s de %s" % (k.replace("max_", ""), u, l) for k, u, l in over)),
                                "independent_work_continues": False,
                                "hint": "subir o limite e decisao do usuario (config.json -> budget, o gateway pergunta); "
                                        "ou reduzir o escopo da feature"})
    for tid, t in sorted(tasks.items()):
        if not in_scope(t.get("feature_id")) or tid in blocked:
            continue
        if state[tid] == "rejected" and aisef_budget.no_progress(log, tid, plimits["no_progress_repeats"]):
            block(tid, "sem progresso")
            decisions.append({"kind": "await_decision", "source": "no_progress", "feature_id": t.get("feature_id"),
                              "task_ids": [tid], "independent_work_continues": True,
                              "title": "%s reprovada %d vezes seguidas pelo mesmo motivo" % (tid, plimits["no_progress_repeats"]),
                              "hint": "subir de modelo nao resolve: traga contexto novo (code-explorer, docs-lookup, "
                                      "o que faltou no relatorio) ou mude o contrato; so entao redelegue"})
        elif state[tid] == "in_progress" and last_started.get(tid):
            timeout = (t.get("limits") or {}).get("timeout_minutes") or plimits["agent_timeout_minutes"]
            age = (now - last_started[tid]).total_seconds() / 60
            if age > timeout:
                block(tid, "agente parado")
                decisions.append({"kind": "await_decision", "source": "stale_agent", "feature_id": t.get("feature_id"),
                                  "task_ids": [tid], "independent_work_continues": True,
                                  "title": "%s em andamento ha %d min (limite %d)" % (tid, age, timeout),
                                  "hint": "veja se o agente ainda roda; se nao, redelegue ou pause a tarefa"})

    # ---- agente terminou sem Execution Report (F-04: o hook marca no_report no runtime)
    no_report = {}
    try:
        with open(os.path.join(ap.aisef_dir(project), "runtime", "agents.jsonl"), encoding="utf-8") as fh:
            for line in fh:
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if ev.get("event") == "no_report" and ev.get("task_id"):
                    no_report[ev["task_id"]] = ev.get("after_seq")
    except OSError:
        pass
    last_delegation = {}
    for e in log:
        if e.get("task_id") and e["event_type"] == "delegation":
            last_delegation[e["task_id"]] = e.get("sequence", 0)
    for tid, after_seq in sorted(no_report.items()):
        t = tasks.get(tid)
        if not t or not in_scope(t.get("feature_id")) or state[tid] != "in_progress" or tid in blocked:
            continue
        if not isinstance(after_seq, int) or after_seq < last_delegation.get(tid, 0):
            continue  # o aviso e de uma tentativa anterior (houve delegacao depois dele)
        block(tid, "agente terminou sem Execution Report")
        decisions.append({"kind": "await_decision", "source": "no_report", "feature_id": t.get("feature_id"),
                          "task_ids": [tid], "title": "%s: o agente terminou sem gravar o Execution Report" % tid,
                          "independent_work_continues": True,
                          "hint": "veja o que o agente fez e decida: redelegar (nova tentativa) ou pausar a tarefa"})

    # ---- requisito mudou (F-07): a tarefa nao segue com a versao antiga do requisito
    req_changed = []
    for tid, t in sorted(tasks.items()):
        if not in_scope(t.get("feature_id")) or state[tid] in DONE or tid in blocked:
            continue
        cur = {r["id"]: r["version"] for r in (feats.get(t.get("feature_id")) or {}).get("requirements", [])}
        refs = (t.get("requirements") or {}).get("requirement_ids") or []
        stale = [x["id"] for x in refs if isinstance(x, dict) and x.get("id") in cur and x.get("version") != cur[x["id"]]]
        if not stale:
            continue
        block(tid, "requisito %s mudou" % ", ".join(stale))
        started = state[tid] not in ("draft", "ready", "rejected", "blocked")
        req_changed.append({"kind": "requirement_changed", "feature_id": t.get("feature_id"), "task_ids": [tid],
                            "requirements": stale, "started": started,
                            "cmd": _cmd("aisef_new.py", "rebase-req --project . --feature %s" % t.get("feature_id")),
                            "hint": ("a tarefa ja comecou: reabra a feature (aisef-feature) para mudar o que foi feito"
                                     if started else "rode o comando: nova versao da tarefa com o requisito atual")})

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

    rebase_now = [a for a in req_changed if not a["started"]]  # o orquestrador resolve sozinho (rebase-req)
    decisions += [a for a in req_changed if a["started"]]        # reabrir e decisao do usuario
    automatable = rebase_now + complete + validate + acceptance + branch_actions + dispatch_actions
    actions = critical + budget_stop + exhausted + decisions + rebase_now + complete + validate + acceptance + branch_actions + dispatch_actions + wait_actions + cleanup
    if critical:
        stop, detail = "critical_risk", "risco critico: pare na hora e leve ao usuario"
    elif budget_stop:
        stop, detail = "budget_exhausted", "orcamento da feature esgotado: pare e leve ao usuario"
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
    guide = project_phase(project, feats, tasks, approvals, actions)
    guide["tooling_review_due"] = tooling_review_due(cfg, approvals, log)
    guide["graph_refresh"] = graph_refresh(project, cfg, guide["phase"], actions)
    return {"feature": feature, "actions": actions, "stop_reason": stop, "stop_detail": detail, "guide": guide,
            "deferred": deferred, "wave_error": wave_error, "warnings": warnings,
            "states": {tid: state[tid] for tid in sorted(state) if in_scope(tasks[tid].get("feature_id"))}}


git_state_fn = git_state

GRAPH_MILESTONES = ("approve_plan", "review", "decide", "done")


def graph_refresh(project, cfg, phase, actions):
    """Sugere regenerar o grafo do Graphify (sem modelo) quando ele falta ou esta velho, nos marcos: antes de despachar
    uma onda (o pack le o grafo) e nos marcos de fase (plano, revisao, decisao, fim). None quando nao ha o que fazer."""
    try:
        st = ap.graphify_status(project, cfg)
    except Exception:
        return None
    if not st["enabled"] or (st["exists"] and not st["stale"]):
        return None
    dispatching = any(a["kind"] == "dispatch" for a in actions)
    if not dispatching and phase not in GRAPH_MILESTONES:
        return None
    why = "o grafo ainda nao foi gerado" if not st["exists"] else "%s mudou depois do grafo" % st["newer_source"]
    return {"reason": why, "before_dispatch": dispatching,
            "cmd": "GRAPHIFY_BACKEND=%s python -m graphify update ." % st["backend"]}


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
        elif k == "requirement_changed":
            lines.append("- requirement_changed %s (%s): %s" % (", ".join(a["task_ids"]), ", ".join(a["requirements"]),
                                                               a["hint"] if a["started"] else a["cmd"]))
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
    if res.get("guide"):
        lines.append("Fase: %s. Proximo passo:" % res["guide"]["phase"])
        lines += ["  %d. %s" % (i, s_) for i, s_ in enumerate(res["guide"]["steps"], 1)]
        if res["guide"].get("tooling_review_due"):
            lines.append("Revisao das ferramentas devida (aisef-tooling, secao 8): /skill-doctor, custo e uso das skills")
        if res["guide"].get("compact_hint"):
            lines.append(res["guide"]["compact_hint"])
        gr = res["guide"].get("graph_refresh")
        if gr:
            lines.append("Grafo do Graphify: %s. Regenere%s (sem modelo): %s" % (
                gr["reason"], " antes do dispatch" if gr["before_dispatch"] else "", gr["cmd"]))
    return "\n".join(lines)
