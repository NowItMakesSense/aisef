#!/usr/bin/env python3
"""AISEF workflow (0.14, L-03): le core/workflow.v0.1.json, a fonte unica do fluxo, e confere a coerencia.

    python -I aisef_workflow.py check    (schema + coerencia; sai 1 se houver problema)
    python -I aisef_workflow.py show     (o fluxo em texto)

Quem le: aisef_next (event_state, rank, terminal, contract_prevails), aisef_guide (steps), aisef_triage, aisef_new e
o check (profile). Mudar o fluxo e mudar o JSON; o check daqui pega o que ficar incoerente. Somente stdlib.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "workflow.v0.1.json")
SCHEMA = os.path.join(HERE, "workflow.schema.v0.1.json")
_cache = {}


def load(path=PATH):
    if path not in _cache:
        with open(path, encoding="utf-8") as fh:
            _cache[path] = json.load(fh)
    return _cache[path]


def event_state(path=PATH):
    return {e: v["state"] for e, v in load(path)["events"].items()}


def recorded_by(path=PATH):
    return {e: tuple(v["recorded_by"]) for e, v in load(path)["events"].items()}


def rank(path=PATH):
    return dict(load(path)["task_states"]["rank"])


def terminal(path=PATH):
    return tuple(load(path)["task_states"]["terminal"])


def contract_prevails(path=PATH):
    return tuple(load(path)["task_states"]["contract_prevails"])


def steps(path=PATH):
    return {p["id"]: list(p["steps"]) for p in load(path)["phases"]}


def phases(path=PATH):
    return [p["id"] for p in load(path)["phases"]]


def profiles(path=PATH):
    return {k: v for k, v in load(path)["profiles"].items() if not k.startswith("$")}


def profile(name, path=PATH):
    """Sobreposicao do perfil; perfil desconhecido cai no team (o comportamento anterior a 0.13)."""
    p = profiles(path)
    return p.get(name) or p["team"]


def gates(path=PATH):
    return {k: v for k, v in load(path)["gates"].items() if not k.startswith("$")}


def check(path=PATH):
    """Problemas do workflow: schema e coerencia com o resto do plugin. Lista vazia = ok."""
    wf = load(path)
    out = []
    try:
        import jsonschema
        with open(SCHEMA, encoding="utf-8") as fh:
            schema = json.load(fh)
        for e in sorted(jsonschema.Draft202012Validator(schema).iter_errors(wf), key=lambda e: list(e.path)):
            out.append("schema: %s: %s" % ("/".join(str(x) for x in e.path) or "(raiz)", e.message))
    except ImportError:
        pass
    known = set(wf["task_states"]["rank"]) | set(wf["task_states"]["terminal"]) | set(wf["task_states"]["contract_prevails"])
    for ev, v in wf["events"].items():
        if v["state"] not in known:
            out.append("evento %s leva ao estado %s, que nao esta em task_states" % (ev, v["state"]))
    try:
        with open(os.path.join(HERE, "audit-event.schema.v0.1.json"), encoding="utf-8") as fh:
            event_types = set(json.load(fh)["properties"]["event_type"]["enum"])
        for ev in wf["events"]:
            if ev not in event_types:
                out.append("evento %s nao existe no schema do log de auditoria" % ev)
    except (OSError, KeyError, ValueError):
        out.append("schema do log de auditoria ilegivel")
    try:
        with open(os.path.join(HERE, "approval-request.schema.v0.1.json"), encoding="utf-8") as fh:
            req_types = set(json.load(fh)["properties"]["request_type"]["enum"])
        g = set(gates(path))
        for x in sorted(req_types - g):
            out.append("tipo de pedido %s do Approval Center sem portao no workflow" % x)
        for x in sorted(g - req_types):
            out.append("portao %s nao e tipo de pedido do Approval Center" % x)
    except (OSError, KeyError, ValueError):
        out.append("schema do Approval Center ilegivel")
    ids = phases(path)
    if len(ids) != len(set(ids)):
        out.append("fase repetida")
    for p in wf["phases"]:
        if p.get("gate") and p["gate"] not in gates(path):
            out.append("fase %s usa o portao %s, que nao existe" % (p["id"], p["gate"]))
    import aisef_base
    if set(profiles(path)) != set(aisef_base.PROFILES):
        out.append("perfis do workflow %s diferentes dos aceitos no config %s" % (sorted(profiles(path)), sorted(aisef_base.PROFILES)))
    if "team" not in profiles(path):
        out.append("o perfil team e o padrao de projetos antigos e precisa existir")
    return out


def main(argv=None):
    cmd = (argv or sys.argv[1:] or ["check"])[0]
    if cmd == "show":
        wf = load()
        print("Fases: " + " -> ".join(p["id"] + ("[%s]" % p["gate"] if p.get("gate") else "") for p in wf["phases"]))
        print("Eventos: " + ", ".join("%s->%s (%s)" % (e, v["state"], "/".join(v["recorded_by"])) for e, v in wf["events"].items()))
        print("Perfis: " + ", ".join(profiles()))
        return 0
    problems = check()
    for p in problems:
        print("ERRO " + p)
    print("workflow: %d problema(s)" % len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    sys.exit(main())
