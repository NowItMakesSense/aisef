#!/usr/bin/env python3
"""AISEF graph nudge: hook PreToolUse (Grep|Glob), CONSULTIVO. Lembra o agente de consultar o grafo de codigo
antes de varrer o repositorio com grep/glob. Nunca bloqueia, nunca decide permissao: so devolve contexto adicional.

So atua se o projeto tem .aisef/config.json E um graph MCP configurado no .mcp.json (codebase-memory ou graphify).
Falha aberto: qualquer erro termina em silencio e exit 0. Rapido: stdlib leve, sem jsonschema nem cryptography.
Limite por sessao (padrao 3 lembretes; config.json -> "graph_nudge": {"enabled": true, "max_per_session": 3}),
para nao gastar tokens a cada busca. Somente stdlib."""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "core"))
DEFAULT_CAP = 3
PREFERRED = {"codebase-memory": ("search_graph", "trace_path", "get_file_outline"),
             "graphify": ("query_graph", "get_neighbors", "shortest_path")}


def message(servers, tool, tool_input):
    lines = []
    for s in servers:
        names = ", ".join(s["tools"][t] for t in PREFERRED[s["profile"]] if t in s["tools"])
        lines.append("%s: %s" % (s["label"], names))
    what = tool_input.get("pattern") or tool_input.get("query") or ""
    return ("AISEF: este projeto tem grafo configurado. Antes de varrer com %s%s, consulte o grafo (menos tokens, resposta "
            "estruturada). Ferramentas de leitura: %s. Se o grafo nao cobrir a duvida (ou nao estiver indexado), siga com "
            "%s normalmente." % (tool, " por '%s'" % what[:60] if what else "", "; ".join(lines), tool))


def under_cap(session, cap):
    """Conta lembretes por sessao num arquivo temporario. Qualquer falha de I/O = nao lembrar (fail-open silencioso)."""
    safe = "".join(c for c in str(session) if c.isalnum() or c in "-_")[:64] or "nosession"
    path = os.path.join(tempfile.gettempdir(), "aisef-graph-nudge-" + safe)
    try:
        try:
            with open(path, encoding="utf-8") as fh:
                n = int(fh.read().strip() or 0)
        except FileNotFoundError:
            n = 0
        if n >= cap:
            return False
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(str(n + 1))
        return True
    except Exception:
        return False


def main():
    data = json.load(sys.stdin)
    if data.get("tool_name") not in ("Grep", "Glob"):
        return
    project = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    cfg_path = os.path.join(project, ".aisef", "config.json")
    if not os.path.isfile(cfg_path):
        return
    with open(cfg_path, encoding="utf-8") as fh:
        opts = json.load(fh).get("graph_nudge", {})
    if opts.get("enabled", True) is False:
        return
    from aisef_context import detect_graph_servers
    servers = detect_graph_servers(project)
    if not servers:
        return
    cap = opts.get("max_per_session", DEFAULT_CAP)
    if not isinstance(cap, int) or isinstance(cap, bool) or not under_cap(data.get("session_id", ""), cap):
        return
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                              "additionalContext": message(servers, data["tool_name"], data.get("tool_input") or {})}}))


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        pass  # consultivo: nunca atrapalha a chamada da ferramenta
    sys.exit(0)
