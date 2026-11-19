#!/usr/bin/env python3
"""AISEF agent events: hooks SubagentStart e SubagentStop (0.8.0) e PreToolUse Agent|Task (0.10.0, quem disparou
quem). Alimentam a visao "Agora" e o mapa de execucao do painel.

Grava uma linha por evento em .aisef/runtime/agents.jsonl (efemero, fora do Git: a pasta tem o proprio .gitignore).
Nao e o log de auditoria: a trilha assinada continua com `delegation`, `task_started` e `task_executed`. Barato,
somente stdlib, nunca bloqueia e falha em silencio (roda em segundo plano).
"""
import datetime
import json
import os
import sys

MAX_BYTES = 2 * 1024 * 1024  # o arquivo e uma visao ao vivo, nao historico: passou disso, recomeca


def runtime_append(project, record):
    rdir = os.path.join(project, ".aisef", "runtime")
    os.makedirs(rdir, exist_ok=True)
    ign = os.path.join(rdir, ".gitignore")
    if not os.path.exists(ign):
        with open(ign, "w", encoding="utf-8") as fh:
            fh.write("*\n")
    path = os.path.join(rdir, "agents.jsonl")
    mode = "w" if os.path.exists(path) and os.path.getsize(path) > MAX_BYTES else "a"
    record["at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    with open(path, mode, encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def main():
    data = json.load(sys.stdin)
    project = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    if not os.path.exists(os.path.join(project, ".aisef", "config.json")):
        return
    if data.get("hook_event_name") == "PreToolUse":
        # Disparo de subagente (ferramenta Agent/Task): guarda quem pediu. O painel liga este registro ao
        # SubagentStart seguinte do mesmo tipo; sem como ter certeza, a ligacao sai marcada como inferida.
        if data.get("tool_name") not in ("Agent", "Task"):
            return
        inp = data.get("tool_input") or {}
        runtime_append(project, {"event": "spawn", "parent_id": data.get("agent_id"), "parent_type": data.get("agent_type"),
                                 "subagent_type": inp.get("subagent_type") or "general-purpose",
                                 "description": (inp.get("description") or "")[:200], "model": inp.get("model"),
                                 "background": bool(inp.get("run_in_background")), "session_id": data.get("session_id")})
        return
    kind = {"SubagentStart": "start", "SubagentStop": "stop"}.get(data.get("hook_event_name"))
    if not kind:
        return
    runtime_append(project, {"event": kind, "agent_id": data.get("agent_id"), "agent_type": data.get("agent_type"),
                             "session_id": data.get("session_id")})


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
