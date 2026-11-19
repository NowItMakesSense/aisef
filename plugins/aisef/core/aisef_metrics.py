#!/usr/bin/env python3
"""AISEF: metricas do projeto (0.11.0). Usado por `aisef_project.py metrics`.

Mede o custo e o retorno do processo a partir do que o AISEF ja registra (log, contratos, aprovacoes,
relatorios), sem modelo e sem escrever nada:

    atencao humana   pedidos de aprovacao por tarefa concluida, por tipo, e a fatia que e Git
    qualidade        tentativas por tarefa, taxa de aprovacao na 1a validacao, reprovacoes do precheck x validador,
                     reaberturas, correcoes no log e erros do aisef-check
    tempo            lead time (1a delegacao -> task_completed) e espera pela validacao (executed -> validated)
    ruido            fracao do log assinado que e tool_used e quantas chamadas o gateway negou ou perguntou

Somente leitura: pode rodar em qualquer projeto, inclusive com o log arquivado (archive/ entra na conta).
"""
import datetime
import glob
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_project as ap  # noqa: E402
import aisef_runtime  # noqa: E402
import audit_chain  # noqa: E402

GIT_REQUESTS = ("git_operation",)
DEFAULT_POLICY = os.path.join(HERE, "permission-policy.v0.1.json")
DEFAULT_DEFAULTS = os.path.join(HERE, "orchestration-defaults.v0.1.json")


def _parse(ts):
    try:
        d = datetime.datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)


def _load_dir(project, sub):
    out = []
    for f in sorted(glob.glob(os.path.join(ap.aisef_dir(project), sub, "*.json"))):
        try:
            with open(f, encoding="utf-8") as fh:
                out.append(json.load(fh))
        except (OSError, ValueError):
            continue
    return out


def _minutes(a, b):
    return round((b - a).total_seconds() / 60.0, 1) if a and b and b >= a else None


def _summary(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return {"n": 0, "median": None, "p90": None}
    vals.sort()
    p90 = vals[min(len(vals) - 1, int(round(0.9 * (len(vals) - 1))))]
    return {"n": len(vals), "median": round(statistics.median(vals), 1), "p90": round(p90, 1)}


def _ratio(num, den):
    return round(num / den, 2) if den else None


def compute_metrics(project, feature=None, since=None, run_check=True, now=None):
    """Devolve um dicionario com as metricas. `since` (ISO 8601) corta eventos e pedidos mais antigos."""
    since_dt = _parse(since) if since else None
    log = audit_chain.read_log_dir(os.path.join(ap.aisef_dir(project), "audit"))
    tasks = {t["task_id"]: t for t in _load_dir(project, "contracts/tasks") if t.get("task_id")}
    approvals = _load_dir(project, "approvals")

    def in_feature(fid):
        return feature is None or fid == feature

    def in_window(ts):
        return since_dt is None or ((_parse(ts) or since_dt) >= since_dt)

    events = [e for e in log if in_window(e.get("timestamp"))]
    if feature is not None:
        # eventos sem feature (tool_used, genesis...) so entram na visao do projeto inteiro
        events = [e for e in events if e.get("feature_id") == feature]

    # ---- por tarefa, na ordem do log
    per = {}

    def slot(tid):
        return per.setdefault(tid, {"delegations": 0, "rejections": 0, "precheck_rejections": 0,
                                    "validator_rejections": 0, "first_delegation": None, "completed_at": None,
                                    "context_mode": None,
                                    "executed_at": None, "validation_waits": [], "first_verdict": None,
                                    "feature_id": (tasks.get(tid) or {}).get("feature_id")})

    for e in events:
        tid, et = e.get("task_id"), e.get("event_type")
        if not tid:
            continue
        s = slot(tid)
        if e.get("feature_id") and not s["feature_id"]:
            s["feature_id"] = e["feature_id"]
        ts = _parse(e.get("timestamp"))
        if et == "delegation":
            s["delegations"] += 1
            if s["context_mode"] is None:
                s["context_mode"] = (e.get("data") or {}).get("context_mode") or "unknown"
            s["first_delegation"] = s["first_delegation"] or ts
        elif et == "task_started":
            s["first_delegation"] = s["first_delegation"] or ts
        elif et == "task_executed":
            s["executed_at"] = ts
        elif et == "task_rejected":
            s["rejections"] += 1
            if isinstance(e.get("data"), dict) and "precheck" in e["data"]:
                s["precheck_rejections"] += 1
            else:
                s["validator_rejections"] += 1
            s["first_verdict"] = s["first_verdict"] or "rejected"
            s["executed_at"] = None
        elif et == "task_validated":
            s["first_verdict"] = s["first_verdict"] or "validated"
            if s["executed_at"]:
                s["validation_waits"].append(_minutes(s["executed_at"], ts))
                s["executed_at"] = None
        elif et == "task_completed":
            s["completed_at"] = ts

    per = {tid: s for tid, s in per.items() if in_feature(s["feature_id"])}
    completed = [tid for tid, s in per.items() if s["completed_at"]]
    verdicts = [s["first_verdict"] for s in per.values() if s["first_verdict"]]

    # ---- aprovacoes
    appr = [a for a in approvals if in_feature(a.get("feature_id")) and in_window(a.get("created_at"))]
    by_type, by_status = {}, {}
    for a in appr:
        by_type[a.get("request_type") or "?"] = by_type.get(a.get("request_type") or "?", 0) + 1
        by_status[a.get("status") or "?"] = by_status.get(a.get("status") or "?", 0) + 1
    git_n = sum(n for t, n in by_type.items() if t in GIT_REQUESTS)

    # ---- log e gateway
    count = {}
    for e in events:
        count[e.get("event_type")] = count.get(e.get("event_type"), 0) + 1
    gw = {"deny": 0, "ask": 0}
    for e in events:
        if e.get("event_type") == "tool_used":
            d = (e.get("data") or {}).get("gateway")
            if d in gw:
                gw[d] += 1

    out = {
        "project": os.path.basename(os.path.abspath(project)),
        "feature": feature,
        "since": since,
        "window": {"first_event": events[0]["timestamp"] if events else None,
                   "last_event": events[-1]["timestamp"] if events else None},
        "attention": {
            "approval_requests": len(appr),
            "by_type": dict(sorted(by_type.items(), key=lambda x: -x[1])),
            "by_status": by_status,
            "git_share": _ratio(git_n, len(appr)),
            "per_completed_task": _ratio(len(appr), len(completed)),
            "per_task": _ratio(len(appr), len(per)),
        },
        "quality": {
            "tasks_seen": len(per),
            "tasks_completed": len(completed),
            "attempts_per_task": _summary([s["delegations"] or 1 for s in per.values() if s["delegations"]]),
            "rejections": sum(s["rejections"] for s in per.values()),
            "rejected_by_precheck": sum(s["precheck_rejections"] for s in per.values()),
            "rejected_by_validator": sum(s["validator_rejections"] for s in per.values()),
            "first_pass_validation_rate": _ratio(verdicts.count("validated"), len(verdicts)),
            "scope_discoveries": count.get("scope_discovery", 0),
            "features_reopened": count.get("feature_reopened", 0),
            "log_corrections": count.get("correction", 0),
        },
        "time_minutes": {
            "lead_time": _summary([_minutes(s["first_delegation"], s["completed_at"]) for s in per.values()]),
            "validation_wait": _summary([w for s in per.values() for w in s["validation_waits"]]),
        },
        "noise": {
            "events": len(events),
            "tool_used": count.get("tool_used", 0),
            "tool_used_share": _ratio(count.get("tool_used", 0), len(events)),
            "gateway_denied": gw["deny"],
            "gateway_asked": gw["ask"],
        },
        "tasks": {tid: {"feature_id": s["feature_id"], "delegations": s["delegations"], "rejections": s["rejections"],
                        "first_verdict": s["first_verdict"],
                        "lead_time_minutes": _minutes(s["first_delegation"], s["completed_at"])}
                  for tid, s in sorted(per.items())},
    }
    out["cost"] = _cost(project, per, completed, in_window, in_feature, tasks)
    for tid, row in out["tasks"].items():
        row["tokens"] = out["cost"].get("_per_task", {}).get(tid)
    out["context_modes"] = _by_context_mode(per, out["cost"].get("_per_task", {}))
    out["cost"].pop("_per_task", None)
    if run_check:
        import check_project
        rep = check_project.check(project, policy_path=DEFAULT_POLICY, defaults_path=DEFAULT_DEFAULTS, now=now)
        rules = {}
        for f in rep.findings:
            if f["severity"] == "error":
                rules[f["rule"]] = rules.get(f["rule"], 0) + 1
        out["consistency"] = {"errors": rep.count("error"), "warnings": rep.count("warning"),
                              "errors_by_rule": dict(sorted(rules.items(), key=lambda x: -x[1]))}
    return out


def _cost(project, per, completed, in_window, in_feature, tasks):
    """Tokens por tarefa a partir de .aisef/runtime/usage.jsonl (gravado pelo hook SubagentStop)."""
    runs = [r for r in aisef_runtime.read_usage(ap.aisef_dir(project)) if in_window(r.get("at"))]
    runs = [r for r in runs if r.get("task_id") is None and in_feature(None) or
            r.get("task_id") is not None and in_feature((tasks.get(r["task_id"]) or {}).get("feature_id"))]
    with_usage = [r for r in runs if isinstance(r.get("usage"), dict)]
    if not with_usage:
        return {"available": False, "subagent_runs": len(runs),
                "note": "sem uso registrado: o hook SubagentStop grava .aisef/runtime/usage.jsonl a partir da 0.11"}
    per_task, by_model, unlinked = {}, {}, 0
    total = cache_read = 0
    for r in with_usage:
        u = r["usage"]
        n = aisef_runtime.billable_tokens(u)
        total += n
        cache_read += u.get("cache_read_input_tokens") or 0
        model = (u.get("models") or ["?"])[0]
        by_model[model] = by_model.get(model, 0) + n
        if r.get("task_id"):
            per_task[r["task_id"]] = per_task.get(r["task_id"], 0) + n
        else:
            unlinked += 1
    return {"available": True, "subagent_runs": len(runs), "runs_with_usage": len(with_usage),
            "runs_without_task": unlinked, "billable_tokens": total, "cache_read_tokens": cache_read,
            "tokens_per_completed_task": _summary([per_task.get(t) for t in completed]),
            "by_model": dict(sorted(by_model.items(), key=lambda x: -x[1])),
            "duration_minutes": _summary([round(r["duration_ms"] / 60000.0, 1) for r in runs
                                          if isinstance(r.get("duration_ms"), int)]),
            "_per_task": per_task}


def _by_context_mode(per, tokens_per_task):
    """G-05: compara as tarefas pelo contexto que receberam na 1a delegacao (graphify, mcp, none). Sem modelo:
    so agrega o que o dispatch registrou. A decisao sobre o grafo sai daqui, com dado."""
    groups = {}
    for tid, s in per.items():
        if not s["context_mode"]:
            continue
        groups.setdefault(s["context_mode"], []).append((tid, s))
    out = {}
    for mode, items in sorted(groups.items()):
        verdicts = [s["first_verdict"] for _, s in items if s["first_verdict"]]
        out[mode] = {"tasks": len(items),
                     "first_pass_validation_rate": _ratio(verdicts.count("validated"), len(verdicts)),
                     "dispatches_median": _summary([s["delegations"] for _, s in items])["median"],
                     "lead_time_median": _summary([_minutes(s["first_delegation"], s["completed_at"]) for _, s in items])["median"],
                     "tokens_median": _summary([tokens_per_task.get(tid) for tid, _ in items])["median"]}
    return out


def _fmt(v, suffix=""):
    return "-" if v is None else ("%s%s" % (v, suffix))


def _pct(v):
    return "-" if v is None else "%d%%" % round(v * 100)


def format_metrics(m):
    a, q, t, n = m["attention"], m["quality"], m["time_minutes"], m["noise"]
    head = "Metricas AISEF: %s%s" % (m["project"], " / " + m["feature"] if m["feature"] else "")
    lines = [head, "=" * len(head)]
    if m["window"]["first_event"]:
        lines.append("Periodo: %s a %s" % (m["window"]["first_event"][:16], m["window"]["last_event"][:16]))
    lines += [
        "",
        "Atencao humana",
        "  pedidos de aprovacao     %d (%s por tarefa concluida, %s por tarefa)" % (
            a["approval_requests"], _fmt(a["per_completed_task"]), _fmt(a["per_task"])),
        "  fatia Git                %s" % _pct(a["git_share"]),
        "  por tipo                 " + (", ".join("%s %d" % kv for kv in a["by_type"].items()) or "-"),
        "",
        "Qualidade",
        "  tarefas                  %d vistas, %d concluidas" % (q["tasks_seen"], q["tasks_completed"]),
        "  aprovada na 1a validacao %s" % _pct(q["first_pass_validation_rate"]),
        "  reprovacoes              %d (precheck %d, validador %d)" % (
            q["rejections"], q["rejected_by_precheck"], q["rejected_by_validator"]),
        "  despachos por tarefa     mediana %s, p90 %s" % (
            _fmt(q["attempts_per_task"]["median"]), _fmt(q["attempts_per_task"]["p90"])),
        "  scope_discovery %d, reaberturas %d, correcoes no log %d" % (
            q["scope_discoveries"], q["features_reopened"], q["log_corrections"]),
        "",
        "Tempo (minutos)",
        "  lead time                mediana %s, p90 %s (n=%d)" % (
            _fmt(t["lead_time"]["median"]), _fmt(t["lead_time"]["p90"]), t["lead_time"]["n"]),
        "  espera pela validacao    mediana %s, p90 %s (n=%d)" % (
            _fmt(t["validation_wait"]["median"]), _fmt(t["validation_wait"]["p90"]), t["validation_wait"]["n"]),
        "",
        "Ruido do log",
        "  eventos                  %d, tool_used %d (%s)" % (n["events"], n["tool_used"], _pct(n["tool_used_share"])),
        "  gateway                  negou %d, perguntou %d" % (n["gateway_denied"], n["gateway_asked"]),
    ]
    k = m.get("cost") or {}
    lines += ["", "Custo (subagentes)"]
    if not k.get("available"):
        lines.append("  tokens                   nao disponivel (%d execucao(oes) sem uso registrado)" % k.get("subagent_runs", 0))
    else:
        lines += [
            "  tokens faturaveis        %d (leitura de cache %d) em %d execucao(oes)" % (
                k["billable_tokens"], k["cache_read_tokens"], k["runs_with_usage"]),
            "  por tarefa concluida     mediana %s, p90 %s (n=%d)" % (
                _fmt(k["tokens_per_completed_task"]["median"]), _fmt(k["tokens_per_completed_task"]["p90"]),
                k["tokens_per_completed_task"]["n"]),
            "  por modelo               " + (", ".join("%s %d" % kv for kv in k["by_model"].items()) or "-"),
            "  sem tarefa ligada        %d" % k["runs_without_task"],
        ]
    cm = m.get("context_modes") or {}
    if cm:
        lines += ["", "Contexto do agente (G-05: com e sem grafo)"]
        for mode, g in cm.items():
            lines.append("  %-24s %d tarefa(s), 1a validacao %s, despachos %s, lead time %s min, tokens %s" % (
                mode, g["tasks"], _pct(g["first_pass_validation_rate"]), _fmt(g["dispatches_median"]),
                _fmt(g["lead_time_median"]), _fmt(g["tokens_median"])))
        if sum(g["tasks"] for g in cm.values()) < 20:
            lines.append("  (menos de 20 tarefas: amostra pequena para decidir sobre o grafo)")
    c = m.get("consistency")
    if c is not None:
        lines += ["", "Consistencia (aisef-check)",
                  "  %d erro(s), %d aviso(s)%s" % (c["errors"], c["warnings"], (": " + ", ".join(
                      "%s %d" % kv for kv in c["errors_by_rule"].items())) if c["errors_by_rule"] else "")]
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project", default=os.getcwd())
    p.add_argument("--feature")
    p.add_argument("--since")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-check", action="store_true")
    a = p.parse_args()
    res = compute_metrics(os.path.abspath(a.project), a.feature, a.since, run_check=not a.no_check)
    print(json.dumps(res, ensure_ascii=False, indent=2) if a.json else format_metrics(res))
