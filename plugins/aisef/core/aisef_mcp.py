#!/usr/bin/env python3
"""AISEF MCP (0.13, F-01, ADR 0024): confianca do usuario em ferramentas MCP, com prazo.

Antes, ferramenta MCP fora do `mcp_allow` do config.json pedia aprovacao a cada chamada, e o `mcp_allow` nao tinha
prazo. Agora o usuario confia numa ferramenta (ou num glob) por ate 7 dias (validity_max_days da politica), e renova
quando quiser. Ferramenta que executa codigo ou comandos (execute_*, *_eval, javascript_tool, run_*, sql...) so entra
com --allow-code-execution: um glob comum nunca a cobre, nem no mcp_allow.

    python -I aisef_mcp.py trust  --project . --tool mcp__github__get_*[,mcp__docs__*] [--days 7] [--allow-code-execution]
                                  [--reason "..."]
    python -I aisef_mcp.py revoke --project . --id MCP-001
    python -I aisef_mcp.py list   --project .

trust e revoke sao decisao do usuario: o gateway abre o prompt nativo. O documento fica em .aisef/authorizations/
(kind mcp_tool) e cada decisao vai para o log assinado.
"""
import argparse
import datetime
import fnmatch
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_project as ap  # noqa: E402

TOOL_RE = re.compile(r"^mcp__[A-Za-z0-9_.*?-]+(__[A-Za-z0-9_.*?-]+)?$")
PATTERNS = os.path.join(os.path.dirname(HERE), "hooks", "sensitive_patterns.json")


def max_days():
    with open(os.path.join(HERE, "permission-policy.v0.1.json"), encoding="utf-8") as fh:
        return json.load(fh).get("scope_authorization_schema_ref", {}).get("validity_max_days") or 7


def code_re():
    with open(PATTERNS, encoding="utf-8") as fh:
        return re.compile((json.load(fh).get("mcp_code_execution") or {}).get("regex") or r"(?!)", re.I)


def runs_code(tool):
    return bool(code_re().search(tool.rsplit("__", 1)[-1]))


def _all(project):
    out = []
    for path in sorted(glob.glob(os.path.join(ap.aisef_dir(project), "authorizations", "*.json"))):
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except (OSError, ValueError):
            continue
        if doc.get("kind") == "mcp_tool":
            out.append((path, doc))
    return out


def trust(project, tools, days=None, allow_code=False, reason=None, now=None):
    limit = max_days()
    days = limit if days is None else days
    if not tools or any(not TOOL_RE.match(t) for t in tools):
        raise SystemExit("--tool: nomes ou globs de ferramenta MCP (mcp__servidor__ferramenta), separados por virgula")
    if not 0 < days <= limit:
        raise SystemExit("--days entre 1 e %d (validity_max_days da politica)" % limit)
    code = [t for t in tools if "*" not in t and "?" not in t and runs_code(t)]
    if code and not allow_code:
        raise SystemExit("%s executa codigo ou comandos: confie com --allow-code-execution, se for isso mesmo" % ", ".join(code))
    now = now or datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    cfg = ap.load_config(project)
    n = len(_all(project)) + 1
    while os.path.exists(os.path.join(ap.aisef_dir(project), "authorizations", "MCP-%03d.json" % n)):
        n += 1
    aid = "MCP-%03d" % n
    doc = {"schema_version": "0.1.0", "kind": "mcp_tool", "authorization_id": aid, "project_id": cfg["project_id"],
           "tools": tools, "allow_code_execution": bool(allow_code),
           "validity": {"valid_from": now.isoformat(), "valid_until": (now + datetime.timedelta(days=days)).isoformat()},
           "status": "active", "granted_by": "user", "granted_at": now.isoformat(),
           **({"reason": reason} if reason else {}),
           "history": [{"event": "granted", "at": now.isoformat()}]}
    problems = ap.validate(doc, "authorization.schema.v0.1.json")
    if problems:
        raise SystemExit("nada foi gravado:\n - " + "\n - ".join(problems))
    ap.write_json(os.path.join(ap.aisef_dir(project), "authorizations", aid + ".json"), doc)
    ap.append(project, {"event_type": "authorization_granted", "actor": {"type": "user", "id": "user"},
                        "summary": "%s: confianca em %s por %d dia(s)%s" % (aid, ", ".join(tools), days,
                                                                          ", com execucao de codigo" if allow_code else ""),
                        "data": {"authorization_id": aid, "tools": tools, "allow_code_execution": bool(allow_code)}})
    return doc


def revoke(project, aid, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    for path, doc in _all(project):
        if doc["authorization_id"] == aid:
            if doc["status"] != "active":
                raise SystemExit("%s ja esta %s" % (aid, doc["status"]))
            doc["status"] = "revoked"
            doc["history"].append({"event": "revoked", "at": now.isoformat()})
            ap.write_json(path, doc)
            ap.append(project, {"event_type": "authorization_revoked", "actor": {"type": "user", "id": "user"},
                                "summary": "%s revogada (%s)" % (aid, ", ".join(doc["tools"])),
                                "data": {"authorization_id": aid}})
            return doc
    raise SystemExit("confianca MCP %s nao existe" % aid)


def covers(project, tool, now=None):
    """Mesma regra do gateway (para testes e para o painel): id da confianca ativa que cobre a ferramenta, ou None."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    code = runs_code(tool)
    for _p, a in _all(project):
        if a["status"] != "active" or (code and not a.get("allow_code_execution")):
            continue
        start = datetime.datetime.fromisoformat(a["validity"]["valid_from"])
        end = datetime.datetime.fromisoformat(a["validity"]["valid_until"])
        if start <= now <= end and any(fnmatch.fnmatchcase(tool, g) for g in a["tools"]):
            return a["authorization_id"]
    return None


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["trust", "revoke", "list"])
    p.add_argument("--project", default=".")
    p.add_argument("--tool", default="")
    p.add_argument("--days", type=int)
    p.add_argument("--allow-code-execution", action="store_true")
    p.add_argument("--reason")
    p.add_argument("--id")
    a = p.parse_args(argv)
    project = os.path.abspath(a.project)
    if a.command == "trust":
        doc = trust(project, [t.strip() for t in a.tool.split(",") if t.strip()], a.days, a.allow_code_execution, a.reason)
        print("%s: %s ate %s" % (doc["authorization_id"], ", ".join(doc["tools"]), doc["validity"]["valid_until"]))
    elif a.command == "revoke":
        if not a.id:
            raise SystemExit("--id obrigatorio")
        revoke(project, a.id)
        print("%s revogada" % a.id)
    else:
        now = datetime.datetime.now(datetime.timezone.utc)
        for _p, d in _all(project):
            end = datetime.datetime.fromisoformat(d["validity"]["valid_until"])
            state = d["status"] if d["status"] != "active" or end >= now else "vencida"
            print("%s %-8s ate %s  %s%s" % (d["authorization_id"], state, d["validity"]["valid_until"][:16],
                                           ", ".join(d["tools"]), "  (executa codigo)" if d["allow_code_execution"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
