#!/usr/bin/env python3
"""AISEF OTel (0.15, T-03): exporta o trabalho de uma feature como traces OpenTelemetry (OTLP/JSON), sem modelo e sem
rede. Envie o arquivo a um coletor OTLP/HTTP (ex.: curl -X POST -H 'Content-Type: application/json'
--data @traces.json http://<coletor>:4318/v1/traces) ou importe num backend que leia OTLP/JSON.

    python -I aisef_otel.py export --project . [--feature FEAT-001] --out traces.json

Um trace por feature (traceId derivado do projeto e da feature, entao reexportar da o mesmo id):
- span raiz `aisef feature <FEAT>`, do primeiro ao ultimo evento da feature; decisoes do usuario e do gateway (aprovacoes,
  aceite, negacoes, perguntas) entram como span events;
- um span por tentativa de tarefa, `invoke_agent <papel>` (kind INTERNAL), da delegation ate o resultado, com as
  convencoes GenAI: gen_ai.operation.name=invoke_agent, gen_ai.agent.name, gen_ai.request.model e
  gen_ai.usage.input_tokens/output_tokens (do usage.jsonl), mais aisef.task_id, aisef.attempt, aisef.level e
  aisef.outcome;
- spans filhos `execute_tool <ferramenta>` (gen_ai.operation.name=execute_tool, gen_ai.tool.name) para as chamadas de
  ferramenta do subagente daquela tarefa durante a tentativa (log assinado e telemetria).
As convencoes GenAI do OpenTelemetry ainda estao em desenvolvimento (Development); gen_ai.provider.name nao e usado
porque saiu dos spans internos de agente. Somente stdlib.
"""
import argparse
import datetime
import glob
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import audit_chain  # noqa: E402

KIND_INTERNAL = 1
STATUS_OK, STATUS_ERROR = 1, 2
OUTCOME = {"task_executed": "executed", "task_validated": "validated", "task_rejected": "rejected",
           "task_completed": "completed", "task_paused": "paused"}
DECISION_EVENTS = ("approval_granted", "approval_rejected", "authorization_granted", "authorization_revoked",
                   "feature_accepted", "decision_recorded", "scope_discovery")


def _ns(ts):
    try:
        dt = datetime.datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None
    return str(int(dt.timestamp() * 1_000_000_000))


def _trace_id(project_id, fid):
    return hashlib.sha256(("trace|%s|%s" % (project_id, fid)).encode()).hexdigest()[:32]


def _span_id(*parts):
    return hashlib.sha256(("span|" + "|".join(str(p) for p in parts)).encode()).hexdigest()[:16]


def _dt(ts):
    try:
        return datetime.datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


def _within(ts, start, end, open_end=False):
    """ts entre start e end, comparando datas (o log e a telemetria gravam a hora em formatos diferentes)."""
    t, a, b = _dt(ts), _dt(start), _dt(end)
    if t is None or a is None:
        return False
    return a <= t and (open_end or b is None or t <= b)


def _attr(key, value):
    if isinstance(value, bool):
        v = {"boolValue": value}
    elif isinstance(value, int):
        v = {"intValue": str(value)}
    elif isinstance(value, float):
        v = {"doubleValue": value}
    else:
        v = {"stringValue": str(value)}
    return {"key": key, "value": v}


def _attrs(d):
    return [_attr(k, v) for k, v in d.items() if v is not None]


def _load_dir(root, sub):
    out = []
    for p in sorted(glob.glob(os.path.join(root, sub, "*.json"))):
        try:
            with open(p, encoding="utf-8") as fh:
                out.append(json.load(fh))
        except (OSError, ValueError):
            continue
    return out


def _usage(root):
    try:
        import aisef_runtime
        return aisef_runtime.read_usage(root)
    except Exception:
        return []


def _telemetry(project):
    try:
        import aisef_telemetry
        return aisef_telemetry.read(project)
    except Exception:
        return []


def feature_spans(project, fid, feat, tasks, log, usage, tele, project_id):
    tids = {i["task_id"] for i in (feat or {}).get("task_plan", [])} or {t for t, x in tasks.items() if x.get("feature_id") == fid}
    evs = [e for e in log if e.get("feature_id") == fid or e.get("task_id") in tids]
    if not evs:
        return []
    trace = _trace_id(project_id, fid)
    root_id = _span_id(project_id, fid, "root")
    spans = []
    root_events = []
    for e in evs:
        if e.get("event_type") in DECISION_EVENTS or (e.get("event_type") == "tool_used" and
                                                       (e.get("data") or {}).get("gateway") in ("deny", "ask")):
            root_events.append({"timeUnixNano": _ns(e.get("timestamp")), "name": e["event_type"],
                                "attributes": _attrs({"aisef.event_id": e.get("event_id"), "aisef.actor": e["actor"]["id"],
                                                      "aisef.summary": (e.get("summary") or "")[:200],
                                                      "aisef.gateway": (e.get("data") or {}).get("gateway")})})
    by_task = {}
    for e in evs:
        if e.get("task_id"):
            by_task.setdefault(e["task_id"], []).append(e)
    tool_events = [e for e in log if e.get("event_type") == "tool_used" and (e.get("data") or {}).get("subagent")]
    tool_events += [dict(r, timestamp=r.get("at")) for r in tele if (r.get("data") or {}).get("subagent")]
    used_tools = set()  # cada chamada vai para uma tentativa so (a hora tem resolucao de segundo)
    for tid, items in sorted(by_task.items()):
        role = ((tasks.get(tid) or {}).get("assigned_agent") or {}).get("agent_id") or "?"
        attempt = 0
        # a tentativa comeca na delegation; projetos sem dispatch (sem delegation) comecam no task_started
        starter = "delegation" if any(x["event_type"] == "delegation" for x in items) else "task_started"
        for i, e in enumerate(items):
            if e["event_type"] != starter:
                continue
            attempt += 1
            nxt = next((k for k in range(i + 1, len(items)) if items[k]["event_type"] == starter), len(items))
            results = [x for x in items[i + 1:nxt] if x["event_type"] in OUTCOME]
            end_ev = results[-1] if results else None  # o resultado da tentativa e o ultimo antes da proxima
            outcome = OUTCOME[end_ev["event_type"]] if end_ev else "in_progress"
            start, end = e.get("timestamp"), (end_ev or items[nxt - 1]).get("timestamp")
            sid = _span_id(project_id, fid, tid, attempt)
            data = e.get("data") or {}
            inp = out = 0
            limit = items[nxt].get("timestamp") if nxt < len(items) else None  # uso vai ate a proxima tentativa
            for u in usage:
                if u.get("task_id") == tid and isinstance(u.get("usage"), dict) and \
                        _within(u.get("at"), start, limit, open_end=limit is None):
                    inp += int(u["usage"].get("input_tokens") or 0) + int(u["usage"].get("cache_creation_input_tokens") or 0)
                    out += int(u["usage"].get("output_tokens") or 0)
            spans.append({
                "traceId": trace, "spanId": sid, "parentSpanId": root_id, "name": "invoke_agent %s" % role,
                "kind": KIND_INTERNAL, "startTimeUnixNano": _ns(start), "endTimeUnixNano": _ns(end) or _ns(start),
                "attributes": _attrs({"gen_ai.operation.name": "invoke_agent", "gen_ai.agent.name": role,
                                      "gen_ai.request.model": data.get("model"),
                                      "gen_ai.usage.input_tokens": inp or None, "gen_ai.usage.output_tokens": out or None,
                                      "aisef.task_id": tid, "aisef.feature_id": fid, "aisef.attempt": attempt,
                                      "aisef.level": data.get("level"), "aisef.outcome": outcome}),
                "status": {"code": STATUS_ERROR if outcome == "rejected" else STATUS_OK}})
            for k, t in enumerate(tool_events):
                ts = t.get("timestamp") or ""
                if k in used_tools or (t.get("data") or {}).get("subagent", "").split(":")[-1] != role or                         not _within(ts, start, end):
                    continue
                used_tools.add(k)
                tool = (t.get("data") or {}).get("tool") or "?"
                spans.append({"traceId": trace, "spanId": _span_id(sid, t.get("event_id") or t.get("seq"), ts),
                              "parentSpanId": sid, "name": "execute_tool %s" % tool, "kind": KIND_INTERNAL,
                              "startTimeUnixNano": _ns(ts), "endTimeUnixNano": _ns(ts),
                              "attributes": _attrs({"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": tool,
                                                    "aisef.summary": (t.get("summary") or "")[:200]}),
                              "status": {"code": STATUS_OK}})
    first, last = evs[0].get("timestamp"), evs[-1].get("timestamp")
    spans.insert(0, {"traceId": trace, "spanId": root_id, "name": "aisef feature %s" % fid, "kind": KIND_INTERNAL,
                     "startTimeUnixNano": _ns(first), "endTimeUnixNano": _ns(last),
                     "attributes": _attrs({"aisef.feature_id": fid, "aisef.title": (feat or {}).get("title"),
                                           "aisef.state": ((feat or {}).get("state") or {}).get("status"),
                                           "aisef.tasks": len(by_task)}),
                     "events": root_events, "status": {"code": STATUS_OK}})
    return spans


def export(project, feature=None):
    root = os.path.join(project, ".aisef")
    try:
        with open(os.path.join(root, "config.json"), encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError):
        cfg = {}
    pid = cfg.get("project_id") or "aisef"
    feats = {f["feature_id"]: f for f in _load_dir(root, "contracts/features") if f.get("feature_id")}
    tasks = {t["task_id"]: t for t in _load_dir(root, "contracts/tasks") if t.get("task_id")}
    log = audit_chain.read_log_dir(os.path.join(root, "audit"))
    usage, tele = _usage(root), _telemetry(project)
    fids = [feature] if feature else sorted(feats)
    spans = []
    for fid in fids:
        spans += feature_spans(project, fid, feats.get(fid), tasks, log, usage, tele, pid)
    try:
        with open(os.path.join(os.path.dirname(HERE), ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
            version = json.load(fh)["version"]
    except (OSError, ValueError, KeyError):
        version = "0"
    return {"resourceSpans": [{
        "resource": {"attributes": _attrs({"service.name": "aisef", "aisef.project_id": pid})},
        "scopeSpans": [{"scope": {"name": "aisef", "version": version}, "spans": spans}]}]}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["export"])
    p.add_argument("--project", default=".")
    p.add_argument("--feature")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    doc = export(os.path.abspath(a.project), a.feature)
    with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
    n = len(doc["resourceSpans"][0]["scopeSpans"][0]["spans"])
    print("%d span(s) em %s" % (n, a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
