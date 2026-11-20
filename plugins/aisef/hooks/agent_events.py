#!/usr/bin/env python3
"""AISEF agent events: hooks SubagentStart e SubagentStop (0.8.0) e PreToolUse Agent|Task (0.10.0, quem disparou
quem). Alimentam a visao "Agora" e o mapa de execucao do painel.

Grava uma linha por evento em .aisef/runtime/agents.jsonl (efemero, fora do Git: a pasta tem o proprio .gitignore).
Nao e o log de auditoria: a trilha assinada continua com `delegation`, `task_started` e `task_executed`. Barato,
somente stdlib, nunca bloqueia e falha em silencio (roda em segundo plano).

0.11.0:
- o disparo guarda a tarefa quando a descricao comeca com "T-xxx:" (como o `dispatch` escreve);
- o `start` guarda a tarefa e o disparo que o originou (`aisef_runtime.match_parents`);
- o `stop` soma os tokens do transcript do subagente (`agent_transcript_path`) e grava uma linha em
  .aisef/runtime/usage.jsonl (historico local, nao truncado), com tarefa, modelo e duracao. E daqui que o
  `metrics` tira tokens por tarefa.
"""
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "core"))
import aisef_runtime  # noqa: E402

MAX_BYTES = 2 * 1024 * 1024  # o arquivo e uma visao ao vivo, nao historico: passou disso, recomeca



def _aisef_root(project):
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core"))
        import aisef_git
        return aisef_git.aisef_root(project)
    except Exception:
        return project

def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _runtime_dir(project):
    rdir = os.path.join(project, ".aisef", "runtime")
    os.makedirs(rdir, exist_ok=True)
    ign = os.path.join(rdir, ".gitignore")
    if not os.path.exists(ign):
        with open(ign, "w", encoding="utf-8") as fh:
            fh.write("*\n")
    return rdir


def runtime_append(project, record):
    path = os.path.join(_runtime_dir(project), "agents.jsonl")
    mode = "w" if os.path.exists(path) and os.path.getsize(path) > MAX_BYTES else "a"
    record["at"] = _now().isoformat(timespec="seconds")
    with open(path, mode, encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_runtime(project):
    out = []
    try:
        with open(os.path.join(project, ".aisef", "runtime", "agents.jsonl"), encoding="utf-8") as fh:
            for line in fh:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def _parse(ts):
    try:
        return datetime.datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ ciclo de vida pelo hook (F-04)
LIFECYCLE = ("delegation", "task_started", "task_resumed", "task_paused", "task_executed", "task_validated",
             "task_rejected", "task_completed")


def _task(project, tid):
    try:
        with open(os.path.join(project, ".aisef", "contracts", "tasks", tid + ".json"), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError, TypeError):
        return None


def _last_lifecycle(project, tid):
    import audit_chain
    last = None
    for e in audit_chain.read_log_dir(os.path.join(project, ".aisef", "audit")):
        if e.get("task_id") == tid and e.get("event_type") in LIFECYCLE:
            last = e
    return last


def _exact_task(project, rec):
    """Tarefa do subagente so quando a ligacao e exata: "T-xxx:" no disparo, sem duvida de qual disparo, e o papel
    do subagente e o assigned_agent do contrato. Senao None (o hook nao grava no log assinado por palpite)."""
    tid = rec.get("task_id")
    if not tid or rec.get("spawn_inferred"):
        return None, None
    t = _task(project, tid)
    if not t:
        return None, None
    agent = t.get("assigned_agent") or {}
    if aisef_runtime.role(rec.get("agent_type")) not in (agent.get("agent_id"), agent.get("role")):
        return None, None
    return tid, t


def _record(project, t, etype, summary, data):
    import aisef_project as ap
    ap.append(project, {"event_type": etype, "actor": {"type": "agent", "id": t["assigned_agent"]["agent_id"]},
                        "feature_id": t["feature_id"], "task_id": t["task_id"], "summary": summary,
                        "data": dict(data, recorded_by="hook")})


def lifecycle_start(project, rec):
    """SubagentStart com ligacao exata: task_started, se o ultimo evento da tarefa ainda nao e esse (idempotente)."""
    tid, t = _exact_task(project, rec)
    if not tid:
        return None
    last = _last_lifecycle(project, tid)
    if last is not None and last["event_type"] not in ("delegation", "task_rejected", "task_paused"):
        return None
    _record(project, t, "task_started", "%s iniciada pelo %s" % (tid, t["assigned_agent"]["agent_id"]),
            {"agent_run_id": rec.get("agent_id")})
    return "task_started"


def _executed_report(project, t, since):
    """Execution Report do executor, desta versao do contrato, terminado depois do inicio do subagente."""
    import glob
    best = None
    for path in glob.glob(os.path.join(project, ".aisef", "reports", "*.json")):
        try:
            with open(path, encoding="utf-8") as fh:
                r = json.load(fh)
        except (OSError, ValueError):
            continue
        if r.get("task_id") != t["task_id"] or (r.get("agent") or {}).get("agent_id") != t["assigned_agent"]["agent_id"]:
            continue
        if r.get("status") != "executed" or r.get("contract_version") != t.get("contract_version") or r.get("review"):
            continue
        fin = _parse((r.get("timing") or {}).get("finished_at"))
        if since and fin and fin < since:
            continue
        best = r
    return best


def lifecycle_stop(project, start, usage):
    """SubagentStop: com relatorio executado, task_executed (com os tokens); sem relatorio, marca no runtime para o
    `next` levar ao usuario (await_decision, no_report). Idempotente."""
    tid, t = _exact_task(project, start)
    if not tid:
        return None
    last = _last_lifecycle(project, tid)
    if last is None or last["event_type"] not in ("delegation", "task_started", "task_resumed"):
        return None
    rep = _executed_report(project, t, _parse(start.get("at")))
    if rep is None:
        runtime_append(project, {"event": "no_report", "task_id": tid, "agent_id": start.get("agent_id"),
                                 "after_seq": last.get("sequence")})
        return "no_report"
    _record(project, t, "task_executed", "%s executada (%s)" % (tid, rep.get("report_id")),
            {"report_id": rep.get("report_id"),
             **({"billable_tokens": aisef_runtime.billable_tokens(usage)} if isinstance(usage, dict) else {})})
    return "task_executed"


def on_start(project, data):
    rec = {"event": "start", "agent_id": data.get("agent_id"), "agent_type": data.get("agent_type"),
           "session_id": data.get("session_id")}
    events = read_runtime(project)
    rec_at = dict(rec, at=_now().isoformat(timespec="seconds"))
    link = aisef_runtime.match_parents(events + [rec_at]).get(rec["agent_id"])
    if link:
        rec["task_id"] = link[4]
        rec["spawn_inferred"] = link[2]
    runtime_append(project, rec)
    try:
        lifecycle_start(project, dict(rec, at=rec.get("at")))
    except Exception:
        pass  # o registro no log nunca derruba o hook; o next ainda ve a tarefa pela delegation


def on_stop(project, data):
    aid = data.get("agent_id")
    runtime_append(project, {"event": "stop", "agent_id": aid, "agent_type": data.get("agent_type"),
                             "session_id": data.get("session_id")})
    start = next((e for e in reversed(read_runtime(project)) if e.get("event") == "start" and e.get("agent_id") == aid), {})
    started, ended = _parse(start.get("at")), _now()
    usage = aisef_runtime.transcript_usage(data.get("agent_transcript_path"))
    rec = {"at": ended.isoformat(timespec="seconds"), "agent_id": aid, "agent_type": data.get("agent_type"),
           "task_id": start.get("task_id"), "task_link_inferred": start.get("spawn_inferred"),
           "session_id": data.get("session_id"),
           "duration_ms": int((ended - started).total_seconds() * 1000) if started else None,
           "usage": usage}
    with open(aisef_runtime.usage_path(os.path.join(project, ".aisef")), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    try:
        lifecycle_stop(project, start, usage)
    except Exception:
        pass


def main():
    data = json.load(sys.stdin)
    project = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    project = _aisef_root(project)  # L-02a: worktree grava no .aisef do repositorio principal
    if not os.path.exists(os.path.join(project, ".aisef", "config.json")):
        return
    event = data.get("hook_event_name")
    if event == "PreToolUse":
        # Disparo de subagente (ferramenta Agent/Task): guarda quem pediu. O painel liga este registro ao
        # SubagentStart seguinte do mesmo tipo; sem como ter certeza, a ligacao sai marcada como inferida.
        if data.get("tool_name") not in ("Agent", "Task"):
            return
        inp = data.get("tool_input") or {}
        desc = inp.get("description") or ""
        stype = inp.get("subagent_type") or "general-purpose"
        runtime_append(project, {"event": "spawn", "parent_id": data.get("agent_id"), "parent_type": data.get("agent_type"),
                                 "subagent_type": stype, "description": desc[:200], "model": inp.get("model"),
                                 "task_id": aisef_runtime.task_from_description(desc) if stype.startswith("aisef:") else None,
                                 "background": bool(inp.get("run_in_background")), "session_id": data.get("session_id")})
    elif event == "SubagentStart":
        on_start(project, data)
    elif event == "SubagentStop":
        on_stop(project, data)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
