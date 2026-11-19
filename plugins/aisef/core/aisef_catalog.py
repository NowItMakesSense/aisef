#!/usr/bin/env python3
"""AISEF Agent Catalog: fonte unica dos papeis de agente (core/agents/catalog.v0.1.json).

Antes os papeis estavam fixos em sete lugares (perfis do Agent Contract, enums dos schemas, padroes da Model Policy,
AGENT_ROLES do aisef_new, papeis avaliadores do check). Agora todos leem daqui:
- aisef_project.AGENT_PROFILES  -> profiles()
- aisef_new.AGENT_ROLES          -> role_ids()
- aisef_route (role_defaults)    -> role_defaults()
- check_project (avaliadores)    -> evaluator_roles()
- tools/gen_agents.py            -> agents_to_generate() + prompt()

Tipos (`kind`):
  orchestrator  sessao principal; nao vira subagente
  executor      implementa (estado final no maximo `executed`)
  fixer         corrige com diff minimo (build, simplificacao, performance); tambem e executor
  evaluator     revisa e relata, nunca corrige o codigo do executor
  validator     validacao independente dos criterios de aceite
  advisor       investiga, planeja ou explica; nao edita codigo de producao

Ativacao (`activation`), usada para decidir quais Agent Contracts viram rascunho num projeto:
  always | manual | stack:<id> | arch:<id> | domain:<id>

Uso:
    python3 -I aisef_catalog.py list [--kind evaluator] [--activation always]
    python3 -I aisef_catalog.py check          (valida o catalogo contra o schema e a consistencia interna)
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG_PATH = os.path.join(HERE, "agents", "catalog.v0.1.json")
SCHEMA_PATH = os.path.join(HERE, "agent-catalog.schema.v0.1.json")
KINDS = ("orchestrator", "executor", "fixer", "evaluator", "validator", "advisor")
ROLE_RE = re.compile(r"^[a-z][a-z0-9-]*[a-z0-9]$")
ACTIVATION_RE = re.compile(r"^(always|manual|(stack|arch|domain):[a-z0-9][a-z0-9_.+-]*)$")

_cache = {}


def load(path=CATALOG_PATH):
    if path not in _cache:
        with open(path, encoding="utf-8") as fh:
            _cache[path] = json.load(fh)
    return _cache[path]


def roles(path=CATALOG_PATH):
    return load(path)["roles"]


def by_id(path=CATALOG_PATH):
    return {r["id"]: r for r in roles(path)}


def get(role_id, path=CATALOG_PATH):
    return by_id(path).get(role_id)


def role_ids(path=CATALOG_PATH):
    return {r["id"] for r in roles(path)}


def profiles(path=CATALOG_PATH):
    """Formato historico de aisef_project.AGENT_PROFILES: id -> (nome, task_types, tools, resources, git_ops, resp)."""
    return {r["id"]: (r["name"], r["task_types"], r["tools"], r["resources"], r["git_operations"], r["responsibilities"])
            for r in roles(path)}


def role_defaults(path=CATALOG_PATH):
    """Nivel padrao na escada da Model Policy por papel roteavel (orquestrador e validador tem regra propria)."""
    return {r["id"]: r["level"] for r in roles(path) if r.get("level") is not None}


def evaluator_roles(path=CATALOG_PATH):
    """Papeis cujo relatorio e de avaliacao (nao de execucao): avaliadores e validador."""
    return {r["id"] for r in roles(path) if r["kind"] in ("evaluator", "validator")}


def validatable_roles(path=CATALOG_PATH):
    """Papeis cuja entrega o validador valida: os que alteram o projeto (executores e corretores)."""
    return [r["id"] for r in roles(path) if r["kind"] in ("executor", "fixer")]


def agents_to_generate(path=CATALOG_PATH):
    return [r for r in roles(path) if r.get("generate_agent", True)]


def prompt(role, path=CATALOG_PATH):
    with open(os.path.join(os.path.dirname(path), role["prompt"]), encoding="utf-8") as fh:
        return fh.read().rstrip("\n")


def applicable(role, stacks=(), styles=(), domains=()):
    """O papel se aplica ao projeto? `manual` nunca se aplica sozinho (so quando o usuario pede)."""
    act = role.get("activation", "always")
    if act == "always":
        return True
    if act == "manual":
        return False
    kind, _, value = act.partition(":")
    return value in {"stack": stacks, "arch": styles, "domain": domains}[kind]


def check(path=CATALOG_PATH):
    """Consistencia do catalogo; devolve lista de problemas (vazia = ok)."""
    p = []
    doc = load(path)
    try:
        import jsonschema
        with open(SCHEMA_PATH, encoding="utf-8") as fh:
            schema = json.load(fh)
        for e in sorted(jsonschema.Draft202012Validator(schema).iter_errors(doc), key=lambda e: list(e.path)):
            p.append("schema: %s: %s" % ("/".join(str(x) for x in e.path) or "(raiz)", e.message))
    except ImportError:
        pass
    seen = set()
    base = os.path.dirname(path)
    for r in doc.get("roles", []):
        rid = r.get("id", "?")
        if rid in seen:
            p.append("papel duplicado: %s" % rid)
        seen.add(rid)
        if not ROLE_RE.match(rid):
            p.append("id invalido: %s" % rid)
        if not ACTIVATION_RE.match(r.get("activation", "")):
            p.append("%s: activation invalida %r" % (rid, r.get("activation")))
        gen = r.get("generate_agent", True)
        if gen and not r.get("prompt"):
            p.append("%s: agente gerado sem prompt" % rid)
        if gen and not r.get("description"):
            p.append("%s: agente gerado sem description" % rid)
        if r.get("prompt") and not os.path.exists(os.path.join(base, r["prompt"])):
            p.append("%s: prompt %s nao existe" % (rid, r["prompt"]))
        kind = r.get("kind")
        if kind in ("orchestrator", "validator") and r.get("level") is not None:
            p.append("%s: %s tem regra propria de modelo, sem level" % (rid, kind))
        if kind not in ("orchestrator", "validator") and r.get("level") is None:
            p.append("%s: papel roteavel sem level" % rid)
        tools = set(r.get("tools", []))
        if kind in ("evaluator", "validator", "advisor") and tools & {"Edit", "Write", "NotebookEdit"}:
            p.append("%s: %s nao edita codigo (tirar Edit/Write)" % (rid, kind))
    return p


def main(argv=None):
    ap = argparse.ArgumentParser(description="AISEF Agent Catalog")
    ap.add_argument("command", choices=["list", "check"])
    ap.add_argument("--kind")
    ap.add_argument("--activation")
    a = ap.parse_args(argv)
    if a.command == "check":
        problems = check()
        for x in problems:
            print("ERRO " + x)
        print("catalogo: %d papeis, %d problema(s)" % (len(roles()), len(problems)))
        return 1 if problems else 0
    for r in roles():
        if a.kind and r["kind"] != a.kind:
            continue
        if a.activation and not r["activation"].startswith(a.activation):
            continue
        print("%-28s %-12s %-10s %s" % (r["id"], r["kind"], r["group"], r["activation"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
