#!/usr/bin/env python3
"""AISEF prompt mode: hook UserPromptSubmit (0.9.0). No modo Ask (.aisef/session/mode.json), lembra o modelo, a cada
pergunta, de que deve responder sem editar nem executar. A aplicacao de verdade e do gateway (nega escrita e comando
que nao seja de leitura); isto so evita que o modelo tente. Em modo Exec, silencio (zero tokens). Somente stdlib."""
import json
import os
import sys


def main():
    data = json.load(sys.stdin)
    project = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    path = os.path.join(project, ".aisef", "session", "mode.json")
    if not os.path.exists(os.path.join(project, ".aisef", "config.json")) or not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        mode = json.load(fh).get("mode")
    if mode != "ask":
        return
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext":
                      "AISEF em modo Ask: responda a pergunta lendo o projeto e pesquisando na internet (WebSearch/WebFetch, fontes "
                      "oficiais primeiro, cite as URLs) quando a resposta depender de algo de fora, sem editar arquivos nem executar "
                      "comandos que mudem algo (o gateway nega). Se a resposta pedir uma mudanca, descreva-a e diga que, "
                      "para executar, o usuario troca o modo com /aisef:modo exec."}}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
