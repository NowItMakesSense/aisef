#!/usr/bin/env python3

"""AISEF check: grupo de regras do check_project (log; politica x schemas; memoria de projeto (0.4.0)).

H-01 (0.14): saiu da funcao check() do check_project.py sem mudar as regras. Cada funcao recebe `_cx`
(as variaveis do check: rep, feats, tasks, policy...), roda as regras e devolve o que definiu para as seguintes.
A ordem esta em check_project.RULE_GROUPS."""

from check_project import *  # noqa: F401,F403



def rules_telemetria(_cx):
    """Regras: telemetria (F-05): cadeia de hash integra."""
    project, rep = _cx.get("project"), _cx.get("rep")
    import aisef_telemetry
    for problem in aisef_telemetry.verify(os.path.dirname(project))[:5]:
        rep.warn("TELEMETRY-CHAIN", "telemetry/telemetry.jsonl", problem)


def rules_log(_cx):
    """Regras: log."""
    a, agents, approvals, e, feats, log, rep, t, tasks, where = _cx.get("a"), _cx.get("agents"), _cx.get("approvals"), _cx.get("e"), _cx.get("feats"), _cx.get("log"), _cx.get("rep"), _cx.get("t"), _cx.get("tasks"), _cx.get("where")
    last = None
    projects = {a["project_id"] for a in approvals.values()}
    # Correcoes (0.4.0): o log e imutavel; um evento 'correction' posterior registra que outro evento estava
    # errado. Erros de ATOR do evento corrigido viram aviso citando a correcao. Autovalidacao nunca e perdoada.
    seq_by_id = {e["event_id"]: e["sequence"] for e in log}
    corrected = {}
    for e in log:
        if e["event_type"] != "correction":
            continue
        target = e.get("corrects_event_id")
        where = "evento %d (%s)" % (e["sequence"], e["event_id"])
        if target not in seq_by_id:
            rep.err("LOG-CORRECTION-UNKNOWN", where, "corrige o evento inexistente %s" % target)
        elif seq_by_id[target] >= e["sequence"]:
            rep.err("LOG-CORRECTION-ORDER", where, "corrige %s, que nao e anterior a correcao" % target)
        else:
            corrected.setdefault(target, e["event_id"])

    def actor_issue(code, where, event_id, message):
        if event_id in corrected:
            rep.warn(code, where, "%s (corrigido por %s)" % (message, corrected[event_id]))
        else:
            rep.err(code, where, message)

    for e in log:
        where = "evento %d (%s)" % (e["sequence"], e["event_id"])
        t = parse_time(e["timestamp"])
        if last is not None and t < last:
            rep.err("LOG-TIME-ORDER", where, "timestamp anterior ao do evento anterior")
        last = t
        if e.get("feature_id") and e["feature_id"] not in feats:
            rep.err("LOG-UNKNOWN-FEATURE", where, "feature %s nao existe" % e["feature_id"])
        if e.get("task_id") and e["task_id"] not in tasks:
            rep.err("LOG-UNKNOWN-TASK", where, "tarefa %s nao existe" % e["task_id"])
        if e["actor"]["type"] in ("agent", "validator") and e["actor"]["id"] not in agents:
            actor_issue("LOG-UNKNOWN-AGENT", where, e["event_id"], "agente %s nao existe" % e["actor"]["id"])
        if e["actor"]["type"] == "validator" and e["actor"]["id"] in agents and agents[e["actor"]["id"]]["role"] != "validator":
            actor_issue("LOG-VALIDATOR-ROLE", where, e["event_id"], "ator 'validator' com agente de papel %s" % agents[e["actor"]["id"]]["role"])
        tk = tasks.get(e.get("task_id"))
        if tk and e["event_type"] in ("task_started", "task_executed") and e["actor"]["id"] != tk["assigned_agent"]["agent_id"]:
            actor_issue("LOG-TASK-ACTOR", where, e["event_id"], "%s por %s, mas a tarefa e de %s" % (e["event_type"], e["actor"]["id"], tk["assigned_agent"]["agent_id"]))
        if tk and e["event_type"] == "task_validated" and e["actor"]["id"] == tk["assigned_agent"]["agent_id"]:
            rep.err("VAL-SELF-ATTEST", where, "o executor validou a propria entrega")
        sub = e.get("subject")
        if sub:
            pool = {"feature_contract": feats, "task_contract": tasks, "agent_contract": agents}.get(sub["kind"])
            if pool is not None:
                cur = pool.get(sub["id"])
                if cur is None:
                    rep.err("LOG-SUBJECT", where, "%s %s nao existe" % (sub["kind"], sub["id"]))
                elif sub.get("version", 1) > cur["contract_version"]:
                    rep.err("LOG-SUBJECT", where, "%s %s v%d nao existe (atual v%d)" % (sub["kind"], sub["id"], sub["version"], cur["contract_version"]))
        if e.get("project_id") and projects and e["project_id"] not in projects:
            rep.warn("LOG-PROJECT", where, "projeto %s sem aprovacoes correspondentes" % e["project_id"])

    _cx.update({k: v for k, v in locals().items() if k != "_cx"})



def rules_politica_x_schemas(_cx):
    """Regras: politica x schemas."""
    c, fh, policy, rep, schemas_dir = _cx.get("c"), _cx.get("fh"), _cx.get("policy"), _cx.get("rep"), _cx.get("schemas_dir")
    if policy is not None:
        def sch(name):
            with open(os.path.join(schemas_dir, name), encoding="utf-8") as fh:
                return json.load(fh)
        for c in pol.check(policy, sch("authorization.schema.v0.1.json"), sch("approval-request.schema.v0.1.json")):
            rep.err("POLICY-SCHEMA", "politica", c)
    else:
        rep.warn("POLICY-SKIPPED", "(validador)", "politica nao fornecida: regras PERM/AUTH-NOT-SCOPABLE e POLICY-SCHEMA puladas")

    _cx.update({k: v for k, v in locals().items() if k != "_cx"})



def rules_memoria_de_projeto(_cx):
    """Regras: memoria de projeto (0.4.0)."""
    code, project, rep, where = _cx.get("code"), _cx.get("project"), _cx.get("rep"), _cx.get("where")
    import check_knowledge  # noqa: E402 (import tardio: so quando ha .aisef/knowledge)
    if os.path.isdir(os.path.join(project, "knowledge")):
        for code, where, msg in check_knowledge.validate(project):
            rep.add("warning" if code in check_knowledge.WARNINGS else "error", code, where, msg)
    _cx.update({k: v for k, v in locals().items() if k != "_cx"})
