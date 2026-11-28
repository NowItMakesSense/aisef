#!/usr/bin/env python3
"""AISEF Audit & Evidence: hook PostToolUse do Claude Code (v0.1).

Anexa um evento 'tool_used' a .aisef/audit/log.jsonl para cada operacao que altera algo (Bash, PowerShell, Edit,
Write, MultiEdit, NotebookEdit). Com config.json -> audit.telemetry = "split" (F-05, padrao dos projetos novos),
Edit/Write/MCP vao para a telemetria (.aisef/telemetry/, cadeia de hash sem assinatura); Bash e PowerShell continuam
no log assinado. Registra o que foi feito, nunca o raciocinio do modelo (sempre
contains_model_reasoning=false). Se o comando parecer conter segredo, ele e substituido por um aviso
antes de gravar (regra T3). So atua em projetos com .aisef/config.json e nunca bloqueia a sessao:
uma falha vira aviso em stderr.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "core"))

MAX_COMMAND = 400



def _aisef_root(project):
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core"))
        import aisef_git
        return aisef_git.aisef_root(project)
    except Exception:
        return project

EXIT_LINE_RE = re.compile(r"^\s*Exit code (-?\d+)")


def shell_result(data):
    """E-01 (0.17): resultado do comando. O PostToolUse so dispara quando o comando da certo (exit 0); o
    PostToolUseFailure traz em `error` a primeira linha `Exit code N` (doc oficial dos hooks). Sem essa linha (o shell
    nem abriu) ou com interrupcao, fica `failed` sem codigo."""
    if data.get("hook_event_name") != "PostToolUseFailure":
        return {"exit_code": 0}
    out = {"failed": True}
    m = EXIT_LINE_RE.match(str(data.get("error") or ""))
    if m and not data.get("is_interrupt"):
        out["exit_code"] = int(m.group(1))
    if data.get("is_interrupt"):
        out["interrupted"] = True
    return out


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    project = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    project = _aisef_root(project)  # L-02a: worktree grava no .aisef do repositorio principal
    if not os.path.exists(os.path.join(project, ".aisef", "config.json")):
        return
    import aisef_project
    import audit_chain

    tool = data.get("tool_name", "")
    inp = data.get("tool_input") or {}
    detail = {"tool": tool}
    if tool in ("Bash", "PowerShell"):
        full = inp.get("command") or ""
        cmd = full[:MAX_COMMAND]
        probe = {"data": {"command": cmd}}
        detail["command"] = "[omitido: possivel segredo]" if audit_chain.find_secrets(probe) else cmd
        if len(full) > MAX_COMMAND:  # E-01b: o teste rodado depois do corte (heredoc grande) tambem fica no log
            import shell_test_runs
            runs = [r for r in shell_test_runs.extract(full) if not audit_chain.find_secrets({"data": {"command": r}})]
            if runs:
                detail["test_runs"] = runs
        detail.update(shell_result(data))  # E-01: o check cruza a evidencia de TDD com este resultado
        summary = tool + ": " + detail["command"].splitlines()[0][:120] if detail["command"] else tool
    elif tool.startswith("mcp__"):
        # so o nome dos campos: os valores podem carregar segredos ou dados pessoais
        detail["input_keys"] = sorted(inp)[:20]
        summary = "MCP: " + tool[:150]
    else:
        path = inp.get("file_path") or inp.get("notebook_path") or ""
        try:
            path = os.path.relpath(path, project)
        except ValueError:
            pass
        detail["file"] = path.replace("\\", "/")
        summary = "%s: %s" % (tool, detail["file"])
    if data.get("session_id"):
        detail["session_id"] = data["session_id"]
    # O ator e a sessao (orquestradora). Subagentes so viram ator 'agent' quando tiverem Agent Contract;
    # ate la o nome deles fica em data, para nao citar agente inexistente (regra LOG-UNKNOWN-AGENT).
    if data.get("agent_type") or data.get("agent_id"):
        detail["subagent"] = data.get("agent_type") or data.get("agent_id")
    if len(summary) < 3:
        summary = "tool_used"
    if data.get("session_id") and tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        try:  # outras sessoes passam a ver que esta mexeu no arquivo (aisef_sessions.overlap/concurrent)
            import aisef_sessions
            aisef_sessions.touch(project, data["session_id"], data.get("cwd"),
                                 inp.get("file_path") or inp.get("notebook_path"))
        except Exception:
            pass
    import aisef_telemetry
    if aisef_telemetry.routes_to_telemetry(aisef_project.load_config(project), tool):
        # F-05: edicao de arquivo e MCP liberados vao para a telemetria (cadeia de hash, sem assinatura)
        try:
            aisef_telemetry.append(project, {"event_type": "tool_used", "summary": summary[:500], "data": detail})
        except Exception as exc:
            sys.stderr.write("AISEF: telemetria NAO registrada (%s)\n" % exc)
        if data.get("agent_id") or data.get("agent_type"):
            try:
                sys.path.insert(1, HERE)
                import agent_events
                agent_events.runtime_append(project, {"event": "tool", "agent_id": data.get("agent_id"),
                                                      "agent_type": data.get("agent_type"), "summary": summary[:160]})
            except Exception:
                pass
        return
    try:
        event = aisef_project.append(project, {"event_type": "tool_used", "actor": {"type": "orchestrator", "id": "claude-code"},
                                               "summary": summary[:500], "data": detail, "panel_visible": False})
    except Exception as exc:
        sys.stderr.write("AISEF: evento de auditoria NAO registrado (%s)\n" % exc)
        sys.exit(1)  # nao bloqueia, mas o aviso aparece para o usuario
    if data.get("agent_id") or data.get("agent_type"):
        try:
            sys.path.insert(1, HERE)
            import agent_events
            agent_events.runtime_append(project, {"event": "tool", "agent_id": data.get("agent_id"),
                                                  "agent_type": data.get("agent_type"), "summary": summary[:160]})
        except Exception:
            pass  # visao ao vivo e acessoria
    if tool in ("Bash", "PowerShell"):
        try:
            consume_reinforced(project, inp.get("command") or "", data.get("cwd"), event)
        except Exception as exc:
            sys.stderr.write("AISEF: aprovacao reforcada NAO marcada como usada (%s)\n" % exc)


def consume_reinforced(project, command, cwd, event):
    """A operacao exata rodou (PostToolUse): a aprovacao reforcada que a liberou vira 'used', com o evento que
    a consumiu. Sem isso ela ficava 'approved' ate vencer e o aisef-check acusava AUTH-REINFORCED-EXPIRED."""
    import datetime
    import aisef_project
    sys.path.insert(1, HERE)
    import gateway
    now = datetime.datetime.now(datetime.timezone.utc)
    appr = gateway.reinforced_for(project, command, now, cwd)
    if not appr:
        return
    path = os.path.join(project, ".aisef", "authorizations", appr + ".json")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["status"] = "used"
    doc["consumed"] = {"at": event.get("timestamp") or now.isoformat(), "operation_event_ref": event["event_id"]}
    aisef_project.write_json(path, doc)


if __name__ == "__main__":
    main()
