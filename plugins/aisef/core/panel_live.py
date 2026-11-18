#!/usr/bin/env python3
"""AISEF: visao "Agora" do painel (0.8.0) e servidor local que a mantem atualizada.

Deriva, sem nunca ser fonte de verdade:
  agents_in_flight  subagentes em execucao (eventos SubagentStart/SubagentStop em .aisef/runtime/agents.jsonl,
                    gravados pelo hook agent_events.py), com a tarefa provavel (ultimo `delegation` daquele papel),
                    o tempo decorrido e a ultima acao registrada;
  next              o resultado do `next`: fase, proximo passo, acoes e criterio de parada;
  flow              para cada feature, as etapas Spec -> Plano -> Execucao -> Validacao -> Revisao/Aceite -> Encerrada,
                    com a atual destacada (Mermaid flowchart);
  gantt             ondas no tempo real do log: de `delegation` ate o ultimo evento de ciclo de vida de cada tarefa
                    (Mermaid gantt), mostrando o que rodou em paralelo.

`serve()` sobe um http.server da stdlib em 127.0.0.1 que regenera os dados quando .aisef/ muda; a pagina consulta
panel-data.json a cada poucos segundos. No Windows o navegador nao le arquivo local por file://, dai o servidor.
"""
import datetime
import functools
import http.server
import json
import os
import re
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

STAGES = [("spec", "Spec"), ("plan", "Plano"), ("execute", "Execução"), ("validate", "Validação"),
          ("review", "Revisão e aceite"), ("closed", "Encerrada")]
LIFECYCLE = ("delegation", "task_started", "task_resumed", "task_executed", "task_validated", "task_rejected",
             "task_completed", "task_paused")


def _parse(ts):
    try:
        d = datetime.datetime.fromisoformat(ts)
        return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError):
        return None


def runtime_path(aisef_dir):
    return os.path.join(aisef_dir, "runtime", "agents.jsonl")


def read_runtime(aisef_dir):
    out = []
    try:
        with open(runtime_path(aisef_dir), encoding="utf-8") as fh:
            for line in fh:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def agents_in_flight(aisef_dir, log, tasks, now):
    events = read_runtime(aisef_dir)
    started, stopped, last_tool = {}, set(), {}
    for e in events:
        aid = e.get("agent_id") or ""
        if e.get("event") == "start":
            started[aid] = e
        elif e.get("event") == "stop":
            stopped.add(aid)
        elif e.get("event") == "tool":
            last_tool[aid] = e
    in_progress = {t["task_id"]: t for t in tasks if t["state"]["status"] == "in_progress"}
    delegated = [e for e in log if e["event_type"] == "delegation" and e.get("task_id") in in_progress]
    used, rows = set(), []
    for aid, e in sorted(started.items(), key=lambda kv: kv[1].get("at") or ""):
        if aid in stopped:
            continue
        role = (e.get("agent_type") or "").split(":")[-1]
        task = next((d["task_id"] for d in delegated
                     if d["task_id"] not in used and in_progress[d["task_id"]]["assigned_agent"]["agent_id"] == role), None)
        if task:
            used.add(task)
        at = _parse(e.get("at"))
        tool = last_tool.get(aid, {})
        rows.append({"agent_id": aid, "agent_type": e.get("agent_type"), "task_id": task,
                     "task_title": in_progress[task].get("title") if task else None,
                     "started_at": e.get("at"), "elapsed_s": int((now - at).total_seconds()) if at else None,
                     "last_action": tool.get("summary"), "last_action_at": tool.get("at")})
    return rows


def feature_stage(feature, tasks):
    st = (feature.get("state") or {}).get("status")
    if st == "closed":
        return "closed"
    plan = ((feature.get("approval") or {}).get("plan") or {}).get("status")
    mine = [t["state"]["status"] for t in tasks if t["feature_id"] == feature["feature_id"]]
    if plan != "approved":
        return "plan" if feature.get("spec") or mine else "spec"
    if mine and all(s in ("completed", "cancelled") for s in mine):
        return "review"
    if any(s in ("executed", "validated") for s in mine) and not any(s in ("ready", "in_progress", "rejected") for s in mine):
        return "validate"
    return "execute"


def _mid(raw):
    return re.sub(r"[^A-Za-z0-9_]", "_", raw)


def flow_mermaid(stage):
    keys = [k for k, _ in STAGES]
    cur = keys.index(stage)
    lines = ["flowchart LR"]
    for i, (k, label) in enumerate(STAGES):
        mark = "✓ " if i < cur else ("▶ " if i == cur else "")
        lines.append('  %s["%s%s"]' % (k, mark, label))
    for a, b in zip(keys, keys[1:]):
        lines.append("  %s --> %s" % (a, b))
    lines += ["  classDef done fill:#d1fae5,stroke:#059669,color:#064e3b", "  classDef now fill:#fde68a,stroke:#b45309,stroke-width:3px,color:#451a03",
              "  classDef todo fill:#f3f4f6,stroke:#9ca3af,color:#374151"]
    for i, k in enumerate(keys):
        lines.append("  class %s %s" % (k, "done" if i < cur else ("now" if i == cur else "todo")))
    return "\n".join(lines)


def gantt_mermaid(log, tasks, now):
    by_task = {}
    for e in log:
        if e["event_type"] in LIFECYCLE and e.get("task_id"):
            by_task.setdefault(e["task_id"], []).append(e)
    title = {t["task_id"]: (t.get("title") or "")[:40] for t in tasks}
    feat = {t["task_id"]: t["feature_id"] for t in tasks}
    status = {t["task_id"]: t["state"]["status"] for t in tasks}
    rows = []
    for tid, evs in by_task.items():
        start = next((_parse(e["timestamp"]) for e in evs if e["event_type"] in ("delegation", "task_started")), None)
        if not start:
            continue
        end = _parse(evs[-1]["timestamp"]) if status.get(tid) in ("completed", "cancelled", "executed", "validated") else now
        if not end or (end - start).total_seconds() < 60:  # barra visivel mesmo para tarefa recem-iniciada
            end = start + datetime.timedelta(minutes=1)
        rows.append((feat.get(tid, "?"), tid, start, end, status.get(tid)))
    if not rows:
        return None
    fmt = "%Y-%m-%dT%H:%M:%S"
    lines = ["gantt", "  dateFormat YYYY-MM-DDTHH:mm:ss", "  axisFormat %H:%M", "  todayMarker off"]
    for fid in sorted({r[0] for r in rows}):
        lines.append("  section %s" % _mid(fid))
        for _f, tid, start, end, st in sorted((r for r in rows if r[0] == fid), key=lambda r: r[2]):
            tag = {"completed": "done", "in_progress": "active", "rejected": "crit"}.get(st, "")
            label = ("%s %s" % (tid, title.get(tid, ""))).replace(":", " ").replace("#", " ").strip()
            lines.append("  %s :%s%s, %s, %s" % (label, tag + ", " if tag else "", _mid(tid),
                                                 start.astimezone().strftime(fmt),
                                                 end.astimezone().strftime(fmt)))
    return "\n".join(lines)


def derive_live(aisef_dir, loaded, log, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    project = os.path.dirname(os.path.abspath(aisef_dir))
    tasks = loaded["tasks"]
    try:
        import aisef_next as nx
        res = nx.compute_next(project, now=now)
        nxt = {"phase": res["guide"]["phase"], "steps": res["guide"]["steps"], "stop_reason": res["stop_reason"],
               "stop_detail": res["stop_detail"], "warnings": res.get("warnings", []),
               "actions": [{"kind": a["kind"],
                            "detail": ", ".join(t["task_id"] for t in a["tasks"]) if a["kind"] == "dispatch"
                            else a.get("task_id") or a.get("request_id") or ", ".join(a.get("task_ids") or []) or a.get("feature_id") or ""}
                           for a in res["actions"]]}
    except Exception as exc:  # o painel nunca quebra por causa do `next`
        nxt = {"phase": None, "steps": [], "stop_reason": None, "stop_detail": "next indisponivel: %s" % exc,
               "warnings": [], "actions": []}
    flow = []
    for f in loaded["features"]:
        stage = feature_stage(f, tasks)
        flow.append({"feature_id": f["feature_id"], "title": f.get("title"), "stage": stage,
                     "stage_label": dict(STAGES)[stage], "mermaid": flow_mermaid(stage)})
    try:
        import aisef_learn
        learning = [{"id": e["id"], "trigger": e["lesson"]["trigger"], "action": e["lesson"]["action"],
                     "confidence": e["lesson"]["confidence"], "status": e["status"], "applied": e["lesson"].get("applied", 0),
                     "succeeded": e["lesson"].get("succeeded", 0), "failed": e["lesson"].get("failed", 0)}
                    for e in aisef_learn.lessons(project)]
    except Exception:
        learning = []
    model_runs = {}
    for e in log:
        if e["event_type"] == "delegation" and (e.get("data") or {}).get("model"):
            m = e["data"]["model"]
            model_runs[m] = model_runs.get(m, 0) + 1
    return {"generated_at": now.isoformat(timespec="seconds"), "learning": learning, "model_runs": model_runs,
            "agents_in_flight": agents_in_flight(aisef_dir, log, tasks, now),
            "next": nxt, "flow": flow, "gantt": gantt_mermaid(log, tasks, now)}


# ---------------------------------------------------------------------------- servidor local
def _latest_mtime(aisef_dir):
    latest = 0.0
    for dp, dn, fn in os.walk(aisef_dir):
        dn[:] = [d for d in dn if d != "panel"]
        for f in fn:
            try:
                latest = max(latest, os.path.getmtime(os.path.join(dp, f)))
            except OSError:
                pass
    return latest


def serve(aisef_dir, out, rebuild, port=8765, open_browser=False, port_only=False):
    """Serve `out` em 127.0.0.1:port; antes de entregar panel-data.json/data.js, regenera se .aisef/ mudou."""
    state = {"mtime": None}
    lock = threading.Lock()

    def refresh():
        with lock:
            m = _latest_mtime(aisef_dir)
            if m != state["mtime"]:
                rebuild()
                state["mtime"] = m

    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path.split("?")[0] in ("/panel-data.json", "/data.js", "/"):
                try:
                    refresh()
                except Exception as exc:
                    sys.stderr.write("aviso: falha ao regenerar o painel (%s)\n" % exc)
            return super().do_GET()

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def log_message(self, *args):
            pass

    refresh()
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Handler, directory=out))
    url = "http://127.0.0.1:%d/" % httpd.server_address[1]
    if port_only:
        return httpd, url
    print("painel ao vivo em %s (Ctrl+C para parar)" % url, flush=True)
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return url
