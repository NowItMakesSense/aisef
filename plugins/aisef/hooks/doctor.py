#!/usr/bin/env python3
"""AISEF doctor: hook SessionStart. Confere o ambiente uma vez por sessao e so fala quando ha problema
(sem problema, nao gasta nenhum token). Nunca bloqueia nada. Somente stdlib."""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "core"))


def problems(project):
    found = []
    if sys.version_info < (3, 10):
        found.append("Python %d.%d e antigo para o AISEF (precisa de 3.10+)" % sys.version_info[:2])
    missing = [m for m in ("jsonschema", "cryptography") if importlib.util.find_spec(m) is None]
    if missing:
        found.append("faltam bibliotecas no Python dos hooks (%s): %s. Instale com `%s -m pip install %s` ou defina "
                     "AISEF_PYTHON para um Python que as tenha" % (sys.executable, ", ".join(missing), sys.executable,
                                                                  " ".join(missing)))
    root = os.path.join(project, ".aisef")
    try:
        import aisef_project as ap
        cfg = ap.load_config(project)
        key_id = ap.audit_settings(cfg)["key_id"]
        signed = any(n.endswith(".pem") for n in os.listdir(os.path.join(root, "keys")))
        if signed and not os.path.exists(ap.private_key_path(cfg["project_id"], key_id)):
            found.append("o log e assinado, mas a chave privada %s nao existe nesta maquina: nenhum evento sera "
                         "registrado (confira AISEF_HOME)" % ap.private_key_path(cfg["project_id"], key_id))
        head_path = ap.external_head_path(cfg["project_id"])
        last = ap.last_event(os.path.join(root, "audit"))
        if signed and last and os.path.exists(head_path):
            with open(head_path, encoding="utf-8") as fh:
                head = json.load(fh)
            if head.get("sequence") != last["sequence"] or head.get("hash") != last["hash"]:
                found.append("o fim do log nao confere com o head assinado externo: rode aisef-check antes de continuar")
        drafts = []
        agents_dir = os.path.join(root, "contracts", "agents")
        for name in sorted(os.listdir(agents_dir)) if os.path.isdir(agents_dir) else []:
            with open(os.path.join(agents_dir, name), encoding="utf-8") as fh:
                if json.load(fh).get("status") == "draft":
                    drafts.append(name[:-5])
        if drafts:
            found.append("agentes ainda em draft (bloqueados pelo gateway): %s. Peca ao usuario para aprova-los "
                         "(aisef-init, passo 4)" % ", ".join(drafts))
        settings = os.path.join(project, ".claude", "settings.json")
        have = []
        if os.path.exists(settings):
            with open(settings, encoding="utf-8") as fh:
                have = json.load(fh).get("permissions", {}).get("ask", [])
        if "Bash(git commit:*)" not in have:
            found.append("as regras nativas de segunda camada nao estao no .claude/settings.json: proponha ao usuario "
                         "`aisef_project.py settings --project . --apply`")
    except Exception as exc:
        found.append("nao foi possivel conferir o estado do AISEF (%s)" % exc)
    return found


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    project = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    if not os.path.exists(os.path.join(project, ".aisef", "config.json")):
        return
    found = problems(project)
    if found:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext":
                          "AISEF doctor encontrou problemas; avise o usuario:\n- " + "\n- ".join(found)}}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # diagnostico nunca atrapalha a sessao
    sys.exit(0)
