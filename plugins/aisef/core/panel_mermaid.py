#!/usr/bin/env python3
"""AISEF painel: diagramas Mermaid (arquitetura, ER, engenharia), saneamento de rotulos e copia local do Mermaid

H-01 (0.14): saiu de build_panel.py sem mudar o codigo; build_panel reexporta tudo."""
import argparse
import datetime
import glob
import json
import os
import re
import shutil
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import audit_chain  # noqa: E402
import aisef_project  # noqa: E402


# ----------------------------------------------------------------------------- saneamento
_UNSAFE_LABEL = re.compile(r"[^A-Za-z0-9 _.,:+/\-\u00C0-\u017F]")


def mermaid_id(prefix, raw):
    return prefix + re.sub(r"[^A-Za-z0-9_]", "_", str(raw))


def mermaid_label(raw, limit=40):
    text = _UNSAFE_LABEL.sub(" ", str(raw))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] or "-"


def redact_tree(obj, counter):
    if isinstance(obj, str):
        out = obj
        for _name, rx in audit_chain.SECRET_PATTERNS:
            out, n = rx.subn("[REDACTED]", out)
            counter[0] += n
        return out
    if isinstance(obj, list):
        return [redact_tree(x, counter) for x in obj]
    if isinstance(obj, dict):
        return {k: redact_tree(v, counter) for k, v in obj.items()}
    return obj


ER_TYPE = re.compile(r"[^A-Za-z0-9_]")


def architecture_mermaid(bp):
    arch = bp["architecture"]
    shape = {"datastore": ('[("', '")]'), "external": ('{{"', '"}}'), "ui": ('(["', '"])')}
    lines = ["flowchart LR"]
    for c in arch["components"]:
        left, right = shape.get(c["kind"], ('["', '"]'))
        lines.append("  %s%s%s: %s%s" % (mermaid_id("c_", c["id"]), left, mermaid_label(c["id"], 20),
                                         mermaid_label(c["name"]), right))
    for i in arch.get("interactions", []):
        lines.append('  %s -->|"%s"| %s' % (mermaid_id("c_", i["from"]), mermaid_label(i.get("protocol", ""), 20),
                                           mermaid_id("c_", i["to"])))
    return "\n".join(lines)


def er_mermaid(bp):
    entities = bp.get("database", {}).get("entities", [])
    if not entities:
        return None
    lines = ["erDiagram"]
    rels = []
    # nome da tabela como identificador do Mermaid; o id do blueprint so se o nome nao servir
    ident = {e["id"]: (ER_TYPE.sub("_", e["name"]) if re.match(r"^[A-Za-z]", e["name"]) else mermaid_id("e_", e["id"]))
             for e in entities}
    for e in entities:
        lines.append("  %s {" % ident[e["id"]])
        for f in e["fields"]:
            keys = ["PK"] if f.get("primary_key") else []
            if f.get("references"):
                keys.append("FK")
                rels.append((f["references"]["entity_id"], e["id"], f["name"]))
            note = "segredo" if f.get("secret") else "pii" if f.get("pii") else ""
            lines.append("    %s %s%s%s" % (ER_TYPE.sub("_", f["type"]) or "t", ER_TYPE.sub("_", f["name"]) or "f",
                                             (" " + ",".join(keys)) if keys else "", (' "%s"' % note) if note else ""))
        lines.append("  }")
    for target, source, field in rels:
        lines.append('  %s ||--o{ %s : "%s"' % (ident.get(target, mermaid_id("e_", target)), ident[source], mermaid_label(field, 30)))
    return "\n".join(lines)


def derive_engineering(blueprints):
    """Paginas de engenharia: o blueprint vigente de cada feature (o de maior versao que nao foi substituido)."""
    current = {}
    for bp in blueprints:
        if bp["state"]["status"] == "superseded":
            continue
        cur = current.get(bp["feature_id"])
        if cur is None or bp["contract_version"] > cur["contract_version"]:
            current[bp["feature_id"]] = bp
    rows = []
    for fid in sorted(current):
        bp = current[fid]
        db = bp.get("database", {})
        rows.append({
            "blueprint_id": bp["blueprint_id"], "feature_id": fid, "version": bp["contract_version"],
            "title": bp["title"], "summary": bp["summary"], "state": bp["state"]["status"],
            "approval": bp["approval"]["status"],
            "components": [{k: c.get(k) for k in ("id", "name", "kind", "responsibility", "owner_role", "requirement_ids")}
                           for c in bp["architecture"]["components"]],
            "decisions": [d["id"] for d in bp["architecture"].get("decisions", [])],
            "endpoints": [{"id": e["id"], "method": e["method"], "path": e["path"], "auth": e["auth"],
                           "roles": e.get("roles", []), "errors": ["%s %s" % (x["status"], x.get("code", "")) for x in e.get("errors", [])],
                           "requirement_ids": e["requirement_ids"]} for e in bp.get("backend", {}).get("endpoints", [])],
            "screens": [{"id": s["id"], "name": s["name"], "route": s["route"], "endpoints": s["calls_endpoint_ids"],
                         "states": s.get("states", []), "requirement_ids": s["requirement_ids"]}
                        for s in bp.get("frontend", {}).get("screens", [])],
            "entities": [{"id": e["id"], "name": e["name"], "data_class": e.get("data_class"),
                          "fields": [{"name": f["name"], "type": f["type"], "primary_key": bool(f.get("primary_key")),
                                      "references": f.get("references"), "pii": bool(f.get("pii")), "secret": bool(f.get("secret"))}
                                     for f in e["fields"]]} for e in db.get("entities", [])],
            "migrations": [{k: m.get(k) for k in ("id", "description", "entity_ids", "destructive", "reversible", "rollback")}
                           for m in db.get("migrations", [])],
            "threats": [{k: t.get(k) for k in ("id", "description", "severity", "mitigation", "component_ids")}
                        for t in bp.get("security", {}).get("threats", [])],
            "secrets_handling": bp.get("security", {}).get("secrets_handling"),
            "devops": {k: bp.get("devops", {}).get(k) for k in ("environments", "deploy_strategy", "pipeline_steps", "rollback", "observability")},
            "tests": [{"level": l["level"], "covers": l["covers"], "notes": l.get("notes")} for l in bp["test_strategy"]["levels"]],
            "graphs": {"architecture": architecture_mermaid(bp), "er": er_mermaid(bp)},
        })
    return rows


# O Mermaid (2,5 MB) nao fica no repositorio: e baixado uma vez, com versao e hash fixos, para um cache
# fora do projeto. Depois disso o painel funciona offline. Sem rede e sem cache, a pagina tenta a CDN.
MERMAID_VERSION = "11.4.1"
MERMAID_URL = "https://cdn.jsdelivr.net/npm/mermaid@%s/dist/mermaid.min.js" % MERMAID_VERSION
MERMAID_SHA256 = "a43bc1afd446f9c4cc66ac5dd45d02e8d65e26fc5344ec0ef787f88d6ddb6f9e"


def mermaid_cache_path():
    home = os.environ.get("AISEF_HOME") or os.path.join(os.path.expanduser("~"), ".aisef")
    return os.path.join(home, "vendor", "mermaid-%s.min.js" % MERMAID_VERSION)


def ensure_mermaid():
    """Caminho da copia local verificada do Mermaid, baixando-a se faltar. None se nao der (sem rede)."""
    import hashlib
    path = mermaid_cache_path()
    if os.path.exists(path):
        with open(path, "rb") as fh:
            if hashlib.sha256(fh.read()).hexdigest() == MERMAID_SHA256:
                return path
    try:
        import urllib.request
        with urllib.request.urlopen(MERMAID_URL, timeout=30) as resp:
            data = resp.read()
    except OSError:
        return None
    if hashlib.sha256(data).hexdigest() != MERMAID_SHA256:
        sys.stderr.write("aviso: Mermaid baixado nao confere com o hash esperado; ignorado\n")
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "wb") as fh:
        fh.write(data)
    os.replace(path + ".tmp", path)
    return path


def install_page(out):
    """Copia a pagina e o Mermaid local (o painel abre via file:// e funciona sem internet)."""
    shutil.copy(os.path.join(HERE, "index.html"), os.path.join(out, "index.html"))
    vendor = ensure_mermaid()
    if vendor:
        os.makedirs(os.path.join(out, "vendor"), exist_ok=True)
        shutil.copy(vendor, os.path.join(out, "vendor", "mermaid.min.js"))
    else:
        sys.stderr.write("aviso: sem copia local do Mermaid (sem rede?); o painel tentara a CDN\n")
