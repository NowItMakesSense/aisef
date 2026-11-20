#!/usr/bin/env python3
"""Uso dos agentes em varios projetos AISEF (C-04): insumo da revisao do catalogo (C-05). Sem modelo, so leitura.

    python tools/agent_usage.py <projeto> [<projeto> ...] [--json]

Soma a secao `agents` do `metrics` de cada projeto e lista, por papel do catalogo: tarefas, revisoes, execucoes e
tokens. No fim, os papeis que nunca trabalharam em nenhum dos projetos (candidatos a juntar ou remover, decisao sua).
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "plugins", "aisef", "core"))
import aisef_catalog  # noqa: E402
import aisef_metrics  # noqa: E402


def collect(projects):
    total = {}
    for proj in projects:
        ag = aisef_metrics.compute_metrics(os.path.abspath(proj), run_check=False).get("agents") or {}
        for role, r in (ag.get("by_role") or {}).items():
            t = total.setdefault(role, {"projects": 0, "tasks": 0, "reviews": 0, "runs": 0, "billable_tokens": 0})
            t["projects"] += 1
            t["tasks"] += r["tasks"]
            t["reviews"] += sum(r["reviews"].values())
            t["runs"] += r["runs"]
            t["billable_tokens"] += r["billable_tokens"]
    roles = [r for r in aisef_catalog.roles() if r["kind"] != "orchestrator"]
    unused = [r["id"] for r in roles if not any(total.get(r["id"], {}).get(k) for k in ("tasks", "reviews", "runs"))]
    return {"projects": len(projects), "by_role": dict(sorted(total.items())), "never_used": unused}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("projects", nargs="+")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    missing = [x for x in a.projects if not os.path.isfile(os.path.join(x, ".aisef", "config.json"))]
    if missing:
        print("sem .aisef/config.json: " + ", ".join(missing))
        return 2
    res = collect(a.projects)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    print("Uso dos agentes em %d projeto(s)" % res["projects"])
    for role, t in res["by_role"].items():
        print("  %-26s %d tarefa(s), %d revisao(oes), %d execucao(oes), %d tokens" % (
            role, t["tasks"], t["reviews"], t["runs"], t["billable_tokens"]))
    print("\nNunca usados (%d): %s" % (len(res["never_used"]), ", ".join(res["never_used"]) or "-"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
