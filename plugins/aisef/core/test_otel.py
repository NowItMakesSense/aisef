#!/usr/bin/env python3
"""T-03: exportacao OTLP/JSON. Formato OTLP (ids, tempos, pai, atributos tipados), convencoes GenAI nos spans de
agente e de ferramenta, tentativas com status, tokens do usage.jsonl e decisoes como eventos do span raiz."""
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_otel as ot  # noqa: E402
import aisef_project as ap  # noqa: E402
import aisef_telemetry as tm  # noqa: E402

fails = total = 0


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)[:500]))
    fails += not cond


proj = os.path.join(work, "proj")
os.makedirs(proj)
ap.init(proj, "PRJ-OT")
ap.write_json(os.path.join(proj, ".aisef", "contracts", "tasks", "T-1.json"),
              {"task_id": "T-1", "feature_id": "FEAT-1", "contract_version": 1,
               "assigned_agent": {"agent_id": "implementer", "role": "implementer"}})
ap.write_json(os.path.join(proj, ".aisef", "contracts", "features", "FEAT-1.json"),
              {"feature_id": "FEAT-1", "title": "Cupom", "state": {"status": "in_execution"},
               "task_plan": [{"task_id": "T-1", "contract_version": 1}]})


def ev(etype, actor=("orchestrator", "orchestrator"), **extra):
    return ap.append(proj, dict({"event_type": etype, "actor": {"type": actor[0], "id": actor[1]}, "feature_id": "FEAT-1",
                                 "task_id": "T-1", "summary": "%s T-1" % etype}, **extra))


ev("delegation", data={"model": "sonnet", "level": 3})
ev("task_started", ("agent", "implementer"))
tm.append(proj, {"event_type": "tool_used", "summary": "Edit: src/a.py", "data": {"tool": "Edit", "subagent": "aisef:implementer"}})
ev("task_executed", ("agent", "implementer"))
ev("task_rejected", ("validator", "validator"))
ev("delegation", data={"model": "opus", "level": 4})
ev("task_executed", ("agent", "implementer"))
ev("task_validated", ("validator", "validator"))
ap.append(proj, {"event_type": "approval_granted", "actor": {"type": "user", "id": "user"}, "feature_id": "FEAT-1",
                 "summary": "plano aprovado"})
rdir = os.path.join(proj, ".aisef", "runtime")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "usage.jsonl"), "w", encoding="utf-8") as fh:
    fh.write(json.dumps({"at": "2999-01-01T00:00:00+00:00", "task_id": "T-1",
                         "usage": {"input_tokens": 120, "output_tokens": 30}}) + "\n")

doc = ot.export(proj, "FEAT-1")
spans = doc["resourceSpans"][0]["scopeSpans"][0]["spans"]
ids = {s["spanId"] for s in spans}
check("formato OTLP: resourceSpans -> scopeSpans -> spans com resource service.name",
      any(a["key"] == "service.name" for a in doc["resourceSpans"][0]["resource"]["attributes"]) and spans)
check("ids hexadecimais (trace 32, span 16) e tempos em nanossegundos como texto", all(
    re.fullmatch(r"[0-9a-f]{32}", s["traceId"]) and re.fullmatch(r"[0-9a-f]{16}", s["spanId"])
    and re.fullmatch(r"\d{18,20}", s["startTimeUnixNano"]) and int(s["endTimeUnixNano"]) >= int(s["startTimeUnixNano"])
    for s in spans), spans[:2])
check("todo parentSpanId aponta para um span exportado", all(s.get("parentSpanId", ids and next(iter(ids))) in ids for s in spans))
check("atributos tipados (stringValue, intValue...)", all(len(a["value"]) == 1 and next(iter(a["value"])) in
                                                       ("stringValue", "intValue", "doubleValue", "boolValue")
                                                       for s in spans for a in s["attributes"]))
agent = [s for s in spans if s["name"] == "invoke_agent implementer"]


def a(span, key):
    return next((list(x["value"].values())[0] for x in span["attributes"] if x["key"] == key), None)


check("um span invoke_agent por tentativa (2), kind INTERNAL", len(agent) == 2 and all(s["kind"] == 1 for s in agent), [s["name"] for s in spans])
check("convencoes GenAI: operation, agent.name e request.model", a(agent[0], "gen_ai.operation.name") == "invoke_agent"
      and a(agent[0], "gen_ai.agent.name") == "implementer" and a(agent[0], "gen_ai.request.model") == "sonnet"
      and a(agent[1], "gen_ai.request.model") == "opus")
check("tentativa reprovada com status de erro; a validada com ok", a(agent[0], "aisef.outcome") == "rejected"
      and agent[0]["status"]["code"] == 2 and a(agent[1], "aisef.outcome") == "validated" and agent[1]["status"]["code"] == 1)
check("tokens do usage.jsonl na tentativa em que o subagente rodou (a ultima)", a(agent[1], "gen_ai.usage.input_tokens") == "120"
      and a(agent[1], "gen_ai.usage.output_tokens") == "30" and a(agent[0], "gen_ai.usage.input_tokens") is None)
tools = [s for s in spans if s["name"].startswith("execute_tool")]
check("chamada de ferramenta do subagente (telemetria) vira span filho da tentativa certa",
      len(tools) == 1 and tools[0]["parentSpanId"] == agent[0]["spanId"] and a(tools[0], "gen_ai.tool.name") == "Edit", tools)
root = spans[0]
check("decisao do usuario como evento do span raiz", any(e["name"] == "approval_granted" for e in root.get("events", [])))
check("ids estaveis: exportar de novo da os mesmos ids", [s["spanId"] for s in ot.export(proj, "FEAT-1")["resourceSpans"][0]
                                                         ["scopeSpans"][0]["spans"]] == [s["spanId"] for s in spans])
out = os.path.join(work, "traces.json")
check("CLI grava o arquivo", ot.main(["export", "--project", proj, "--out", out]) == 0 and json.load(open(out))["resourceSpans"])

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
