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
import aisef_runtime  # noqa: E402

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
    # Cores de tom medio com texto escuro explicito: legiveis no tema claro e no escuro, sem re-renderizar na troca.
    lines += ["  classDef done fill:#4FC395,stroke:#0B6E4F,color:#06251a", "  classDef now fill:#F0A637,stroke:#9A5B00,stroke-width:3px,color:#2b1a00",
              "  classDef todo fill:#C9D3CD,stroke:#6B7A72,color:#15201B"]
    for i, k in enumerate(keys):
        lines.append("  class %s %s" % (k, "done" if i < cur else ("now" if i == cur else "todo")))
    return "\n".join(lines)


def _task_rows(log, tasks, now):
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
    return rows


def timeline_rows(log, tasks, now):
    """Linhas {task_id, wave, start, end, state} para a raia de ondas nativa. Onda = delegacoes feitas juntas (ate 120 s)."""
    rows = sorted(_task_rows(log, tasks, now), key=lambda r: r[2])
    out, wave_start, wave = [], None, 0
    for _f, tid, start, end, st in rows:
        if wave_start is None or (start - wave_start).total_seconds() > 120:
            wave, wave_start = wave + 1, start
        out.append({"task_id": tid, "wave": wave, "start": start.isoformat(timespec="seconds"),
                    "end": end.isoformat(timespec="seconds"), "state": st})
    return out


def gantt_mermaid(log, tasks, now):
    rows = _task_rows(log, tasks, now)
    if not rows:
        return None
    fmt = "%Y-%m-%dT%H:%M:%S"
    lines = ["gantt", "  dateFormat YYYY-MM-DDTHH:mm:ss", "  axisFormat %H:%M", "  todayMarker off"]
    for fid in sorted({r[0] for r in rows}):
        lines.append("  section %s" % _mid(fid))
        for _f, tid, start, end, st in sorted((r for r in rows if r[0] == fid), key=lambda r: r[2]):
            tag = {"completed": "done", "in_progress": "active", "rejected": "crit"}.get(st, "")
            label = _mid(tid).replace("_", "-")  # so o ID: a barra fica legivel; o titulo aparece na raia nativa
            lines.append("  %s :%s%s, %s, %s" % (label, tag + ", " if tag else "", _mid(tid),
                                                 start.astimezone().strftime(fmt),
                                                 end.astimezone().strftime(fmt)))
    return "\n".join(lines)


# ---------------------------------------------------------------------------- mapa de execucao (painel v3)
# Estado visual de cada fatia: run (rodando), val (validando), dep (esperando outra fatia), you (esperando voce),
# done (concluida), fail (reprovada, aguardando retrabalho), todo (pronta, ainda nao despachada), off (cancelada).
_role = aisef_runtime.role
_match_parents = aisef_runtime.match_parents


def _lane(evs, st, denied):
    """Barras e marcadores de uma fatia no tempo, a partir dos eventos de ciclo de vida do log."""
    bars, marks, cur, kind = [], [], None, None
    for e in evs:
        et, ts = e["event_type"], e["timestamp"]
        if et in ("delegation", "task_started", "task_resumed"):
            if cur is None or kind == "fail":
                cur, kind = ts, "run"
        elif et == "task_executed" and cur is not None:
            bars.append({"kind": "done", "start": cur, "end": ts})
            cur, kind = ts, "val"
        elif et == "task_rejected":
            if cur is not None:
                bars.append({"kind": "fail", "start": cur, "end": ts})
            marks.append({"at": ts, "kind": "fail"})
            cur, kind = None, None
        elif et in ("task_validated", "task_completed"):
            if cur is not None and kind in ("run", "val"):
                bars.append({"kind": "done" if kind == "run" else "val", "start": cur, "end": ts})
            if et == "task_completed":
                marks.append({"at": ts, "kind": "done"})
            cur, kind = None, None
        elif et == "approval_requested" and cur is not None:
            bars.append({"kind": kind or "run", "start": cur, "end": ts})
            marks.append({"at": ts, "kind": "you"})
            cur, kind = ts, "you"
        elif et in ("approval_granted", "approval_denied") and kind == "you":
            bars.append({"kind": "you", "start": cur, "end": ts})
            cur, kind = ts, "run"
    if cur is not None and st in ("run", "val", "you"):
        bars.append({"kind": st, "start": cur, "end": None})
    if denied:
        marks.append({"at": denied["at"], "kind": "deny"})
    return bars, marks


def board(aisef_dir, loaded, log, now):
    """Dados do mapa de execucao, das raias em paralelo, da tabela de fatias e da gaveta de detalhe."""
    tasks = loaded["tasks"]
    by_id = {t["task_id"]: t for t in tasks}
    status = {t["task_id"]: t["state"]["status"] for t in tasks}
    deps = {t["task_id"]: list((t.get("dependencies") or {}).get("depends_on") or []) for t in tasks}

    holds = {}  # aprovacao pendente que segura a fatia
    for a in loaded["approvals"]:
        if a.get("status") != "pending":
            continue
        for tid in [a.get("task_id")] + list(a.get("blocked_task_ids") or []):
            if tid and tid not in holds:
                holds[tid] = a

    wave = {}  # onda = profundidade no grafo de dependencias: so roda depois das anteriores

    def depth(tid, seen=()):
        if tid not in wave:
            ds = [d for d in deps.get(tid, []) if d in by_id and d not in seen]
            wave[tid] = 1 + max((depth(d, seen + (tid,)) for d in ds), default=0)
        return wave[tid]
    for tid in by_id:
        depth(tid)

    life = {}
    for e in log:
        if e.get("task_id") in by_id and e["event_type"] in LIFECYCLE + ("approval_requested", "approval_granted", "approval_denied"):
            life.setdefault(e["task_id"], []).append(e)

    rt = read_runtime(aisef_dir)
    parents = _match_parents(rt)
    agents, order = {}, []
    for e in rt:
        aid = e.get("agent_id")
        if not aid:
            continue
        if e.get("event") == "start":
            pid, desc, inf, model, spawn_task = parents.get(aid, (None, None, True, None, None))
            agents[aid] = {"agent_id": aid, "agent_type": e.get("agent_type"), "role": _role(e.get("agent_type")),
                           "started_at": e.get("at"), "ended_at": None, "running": True, "last_action": None,
                           "last_action_at": None, "task_id": spawn_task if spawn_task in by_id else None, "parent_id": pid, "parent_inferred": inf,
                           "description": desc, "model": model, "validating": [], "actions": [], "tool_count": 0}
            order.append(aid)
        elif aid in agents and e.get("event") == "stop":
            agents[aid].update(ended_at=e.get("at"), running=False)
        elif aid in agents and e.get("event") == "tool":
            agents[aid].update(last_action=e.get("summary"), last_action_at=e.get("at"), tool_count=agents[aid]["tool_count"] + 1)
            agents[aid]["actions"] = (agents[aid]["actions"] + [{"at": e.get("at"), "text": e.get("summary")}])[-10:]
    for aid in order:
        if agents[aid]["parent_id"] not in agents:
            agents[aid]["parent_id"] = None

    # executor: a fatia em andamento do seu papel; subagente: a fatia do pai. Ligacoes exatas (pelo disparo) primeiro.
    taken = {a["task_id"] for a in agents.values() if a["task_id"]}
    for aid in order:
        a = agents[aid]
        if a["task_id"]:  # o disparo trouxe "T-xxx:" na descricao: ligacao exata, sem heuristica
            continue
        if a["parent_id"] or a["role"] == "validator" or not a["running"]:
            continue
        cand = [tid for tid in sorted(by_id) if status[tid] == "in_progress" and tid not in taken
                and a["role"] in (by_id[tid]["assigned_agent"]["agent_id"], by_id[tid]["assigned_agent"].get("role"))]
        if cand:
            a["task_id"] = cand[0]
            taken.add(cand[0])
    last_dele = {}
    for e in log:
        if e["event_type"] == "delegation" and e.get("task_id"):
            last_dele[e["task_id"]] = e.get("data") or {}
    for aid in order:
        a = agents[aid]
        if a["task_id"] and not a["model"]:
            d = last_dele.get(a["task_id"], {})
            a["model"] = "/".join(x for x in (d.get("model"), d.get("effort")) if x) or None
    for aid in order:
        a = agents[aid]
        p = agents.get(a["parent_id"]) if a["parent_id"] else None
        if p and p["task_id"]:
            a["task_id"] = p["task_id"]
        if a["role"] == "validator" and a["running"] and not a["parent_id"]:
            a["validating"] = [tid for tid in sorted(by_id) if status[tid] == "executed"]

    denies = {}  # negacao do gateway, presa a fatia do agente que tentou
    for e in log:
        d = e.get("data") or {}
        if e["event_type"] == "tool_used" and d.get("gateway") == "deny" and d.get("subagent"):
            role = _role(d["subagent"])
            exact = agents.get(d.get("agent_id") or "")
            tid = exact["task_id"] if exact and exact["task_id"] else None
            tid = tid or next((agents[a]["task_id"] for a in order if agents[a]["role"] == role and agents[a]["task_id"]), None)
            tid = tid or next((t for t in sorted(by_id) if status[t] == "in_progress"
                               and role in (by_id[t]["assigned_agent"]["agent_id"], by_id[t]["assigned_agent"].get("role"))), None)
            if tid:
                denies[tid] = {"at": e["timestamp"], "text": (d.get("target") or d.get("tool") or "")[:80]}

    tdd = {}
    for r in loaded.get("reports", []):
        cyc = (r.get("tdd_evidence") or {}).get("cycles") or []
        tdd[r.get("task_id")] = [sum(1 for c in cyc if (c.get("red") or {}).get("exit_code") not in (0, None)),
                                 sum(1 for c in cyc if (c.get("green") or {}).get("exit_code") == 0)]

    rows, events, lanes = [], {}, []
    for t in sorted(tasks, key=lambda t: (wave[t["task_id"]], t["task_id"])):
        tid, st = t["task_id"], status[t["task_id"]]
        evs = life.get(tid, [])
        dele = [e for e in evs if e["event_type"] == "delegation"]
        meta = (dele[-1].get("data") or {}) if dele else {}
        started = next((e["timestamp"] for e in evs if e["event_type"] in ("delegation", "task_started")), None)
        ended = evs[-1]["timestamp"] if evs and st in ("completed", "validated", "cancelled") else None
        waiting = [d for d in deps[tid] if status.get(d) != "completed"]
        hold = holds.get(tid)
        vs = ("off" if st == "cancelled" else "you" if hold else "run" if st == "in_progress" else "val" if st == "executed"
              else "done" if st in ("completed", "validated") else "fail" if st == "rejected" else "dep" if waiting else "todo")
        mine = [agents[a] for a in order if agents[a]["task_id"] == tid and not agents[a]["parent_id"]]
        last = next((a for a in reversed(mine) if a["last_action"]), None)
        row = {"task_id": tid, "feature_id": t["feature_id"], "title": t.get("title"), "wave": wave[tid], "st": vs,
               "status": st, "role": t["assigned_agent"]["agent_id"], "model": meta.get("model"), "effort": meta.get("effort"),
               "attempt": meta.get("attempt") or (t["state"].get("rejection_count", 0) or 0) + 1,
               "started_at": started, "ended_at": ended, "depends_on": deps[tid], "waiting_on": waiting,
               "unlocks": [x for x in sorted(by_id) if tid in deps[x]],
               "approval": hold["request_id"] if hold else None, "approval_title": hold.get("title") if hold else None,
               "approval_at": hold.get("created_at") if hold else None, "denied": denies.get(tid),
               "tdd": tdd.get(tid, [0, 0]), "rejections": t["state"].get("rejection_count", 0) or 0,
               "last_action": last["last_action"] if last else None, "last_action_at": last["last_action_at"] if last else None}
        rows.append(row)
        events[tid] = [{"at": e["timestamp"], "type": e["event_type"], "text": e.get("summary")} for e in evs][-8:]
        if started:
            bars, marks = _lane(evs, vs, row["denied"])
            lanes.append({"key": tid, "label": "%s · %s" % (row["role"], tid), "task_id": tid, "st": vs, "child": False,
                          "bars": bars, "marks": marks})
            for aid in order:
                a = agents[aid]
                if a["task_id"] == tid and a["parent_id"]:
                    lanes.append({"key": aid, "label": "%s (de %s)" % (a["role"] or "subagente", tid), "task_id": tid,
                                  "st": "run" if a["running"] else "done", "child": True, "marks": [],
                                  "bars": [{"kind": "run" if a["running"] else "done", "start": a["started_at"], "end": a["ended_at"]}]})
    for aid in order:
        a = agents[aid]
        if a["role"] == "validator" and not a["parent_id"]:
            lanes.append({"key": aid, "label": "validator", "task_id": None, "st": "val" if a["running"] else "done", "child": False,
                          "marks": [], "bars": [{"kind": "val" if a["running"] else "done", "start": a["started_at"], "end": a["ended_at"]}]})

    waves = {}
    for r in rows:
        w = waves.setdefault(r["wave"], {"wave": r["wave"], "dispatched_at": None, "tasks": []})
        w["tasks"].append(r["task_id"])
        if r["started_at"] and (w["dispatched_at"] is None or r["started_at"] < w["dispatched_at"]):
            w["dispatched_at"] = r["started_at"]

    count = {}
    for r in rows:
        count[r["st"]] = count.get(r["st"], 0) + 1
    n_val = max(count.get("val", 0), 1 if any(a["role"] == "validator" and a["running"] for a in agents.values()) else 0)
    parts = (["%d rodando" % count["run"]] if count.get("run") else []) + (["%d validando" % n_val] if n_val else [])
    head = ("%s." % " e ".join(parts)) if parts else "Nenhum agente rodando agora."
    detail = ["%s parada esperando a sua decisão %s" % (r["task_id"], r["approval"]) for r in rows if r["st"] == "you"][:2]
    wait = [r["task_id"] for r in rows if r["st"] == "dep"]
    if wait:
        detail.append("%s %s fatias que ainda não terminaram" % (" e ".join(wait[:3]) + ("…" if len(wait) > 3 else ""),
                                                             "espera" if len(wait) == 1 else "esperam"))
    starts = [r["started_at"] for r in rows if r["started_at"]] + [a["started_at"] for a in agents.values() if a["started_at"]]
    return {"tasks": rows, "events": events, "lanes": lanes, "waves": sorted(waves.values(), key=lambda w: w["wave"]),
            "agents": [agents[a] for a in order], "headline": head[0].upper() + head[1:],
            "detail": ("; ".join(detail) + ".").replace("; ", ". ", 1) if detail else "",
            "since": min(starts, key=lambda s: _parse(s) or now) if starts else None}


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
            "next": nxt, "flow": flow, "gantt": gantt_mermaid(log, tasks, now),
            "timeline": timeline_rows(log, tasks, now), "board": board(aisef_dir, loaded, log, now)}


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
