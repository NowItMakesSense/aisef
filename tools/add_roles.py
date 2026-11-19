#!/usr/bin/env python3
"""Acrescenta ou atualiza papeis no catalogo de agentes a partir de um modulo Python de definicoes.

Cada modulo (tools/roles/*.py) define ROLES = [dict(...)] com os campos do catalogo mais `prompt_text`.
Os padroes por tipo (ferramentas, task_types, recursos, Git) vem de DEFAULTS; o prompt vai para
core/agents/prompts/<id>.md. Rodar de novo atualiza (idempotente); a ordem do catalogo e preservada.

Uso: python tools/add_roles.py tools/roles/core_team.py [...]
"""
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS_DIR = os.path.join(ROOT, "plugins", "aisef", "core", "agents")
CATALOG = os.path.join(AGENTS_DIR, "catalog.v0.1.json")

READ = ["Read", "Grep", "Glob", "Bash"]
EDIT = ["Read", "Grep", "Glob", "Edit", "Write", "Bash"]
DEFAULTS = {
    "evaluator": {"tools": READ, "task_types": ["review"], "resources": ["repo_code"], "git_operations": ["status_log_diff"]},
    "fixer": {"tools": EDIT, "task_types": ["implementation", "refactoring", "testing"], "resources": ["repo_code"],
              "git_operations": ["status_log_diff", "commit"]},
    "executor": {"tools": EDIT, "task_types": ["implementation", "testing"], "resources": ["repo_code"],
                 "git_operations": ["status_log_diff", "commit"]},
    "advisor": {"tools": READ, "task_types": ["investigation", "documentation"], "resources": ["repo_code"],
                "git_operations": ["status_log_diff"]},
}
ORDER = ["id", "name", "kind", "group", "activation", "level", "task_types", "tools", "resources", "git_operations",
         "responsibilities", "description", "prompt", "generate_agent", "preload_skills", "source"]


def load_module(path):
    spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ROLES


def build(r):
    entry = dict(DEFAULTS[r["kind"]])
    entry.update({k: v for k, v in r.items() if k != "prompt_text"})
    entry.setdefault("activation", "always")
    entry["prompt"] = "prompts/%s.md" % r["id"]
    return {k: entry[k] for k in ORDER if k in entry}


def main(paths):
    with open(CATALOG, encoding="utf-8") as fh:
        doc = json.load(fh)
    index = {r["id"]: i for i, r in enumerate(doc["roles"])}
    added = updated = 0
    for path in paths:
        for r in load_module(path):
            entry = build(r)
            with open(os.path.join(AGENTS_DIR, entry["prompt"]), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(r["prompt_text"].strip("\n") + "\n")
            if r["id"] in index:
                doc["roles"][index[r["id"]]] = entry
                updated += 1
            else:
                index[r["id"]] = len(doc["roles"])
                doc["roles"].append(entry)
                added += 1
    with open(CATALOG, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("catalogo: %d novos, %d atualizados, %d papeis" % (added, updated, len(doc["roles"])))


if __name__ == "__main__":
    main(sys.argv[1:])
