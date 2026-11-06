#!/usr/bin/env python3
"""AISEF: gera os dados do painel a partir dos contratos e do log de auditoria (RASCUNHO v0.1).

O painel e uma VISAO DERIVADA. Este script:
  1. le contratos, aprovacoes e relatorios e valida cada um contra o seu schema (invalidos ficam
     de fora e aparecem em source_errors);
  2. verifica a integridade do log de auditoria (cadeia de hash, assinaturas Ed25519, head assinado);
  3. deriva as visoes (features, tarefas, RTM, aprovacoes, decisoes, agentes, riscos, linha do tempo,
     grafo de dependencias em Mermaid, execucoes);
  4. mascara qualquer trecho com aparencia de segredo;
  5. escreve JSON por area em <out>/data/, o pacote <out>/panel-data.json e <out>/data.js
     (data.js existe porque paginas abertas via file:// nao conseguem fazer fetch de JSON).

Estrutura esperada de --project:
    contracts/features/*.json   contracts/tasks/*.json   contracts/agents/*.json
    approvals/*.json            reports/*.json            blueprints/*.json
    audit/log.jsonl             audit/head.json
    keys/<key_id>.pem           (chaves PUBLICAS do Audit Signer)

Uso:
    python3 -I build_panel.py --project DIR --out DIR [--schemas DIR]
"""
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

BUILDER_VERSION = "0.1.0"
SEVERITY = {"low": 0, "medium": 1, "high": 2, "critical": 3}
SCHEMA_FILES = {
    "features": "feature-contract.schema.v0.1.json",
    "tasks": "task-contract.schema.v0.1.json",
    "agents": "agent-contract.schema.v0.1.json",
    "approvals": "approval-request.schema.v0.1.json",
    "reports": "execution-report.schema.v0.1.json",
    "blueprints": "engineering-blueprint.schema.v0.1.json",
}
SOURCE_GLOBS = {
    "features": "contracts/features/*.json",
    "tasks": "contracts/tasks/*.json",
    "agents": "contracts/agents/*.json",
    "approvals": "approvals/*.json",
    "reports": "reports/*.json",
    "blueprints": "blueprints/*.json",
}


# ----------------------------------------------------------------------------- leitura e validacao
def load_sources(project, schemas_dir):
    try:
        import jsonschema
    except ImportError:
        jsonschema = None
    loaded = {k: [] for k in SOURCE_GLOBS}
    errors = []
    validators = {}
    for kind, fname in SCHEMA_FILES.items():
        path = os.path.join(schemas_dir, fname)
        if jsonschema and os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                validators[kind] = jsonschema.Draft202012Validator(json.load(fh))
    if not jsonschema:
        errors.append({"file": "(construtor)", "errors": ["jsonschema ausente: contratos NAO foram validados"]})
    for kind, pattern in SOURCE_GLOBS.items():
        for path in sorted(glob.glob(os.path.join(project, pattern))):
            rel = os.path.relpath(path, project)
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, ValueError) as exc:
                errors.append({"file": rel, "errors": ["JSON ilegivel: %s" % exc]})
                continue
            validator = validators.get(kind)
            if validator:
                problems = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
                if problems:
                    errors.append({"file": rel, "errors": ["%s: %s" % ("/".join(map(str, e.path)) or "(raiz)", e.message[:160]) for e in problems[:3]]})
                    continue
            loaded[kind].append(data)
    return loaded, errors


# ----------------------------------------------------------------------------- integridade do log
def check_integrity(project):
    errors, warnings = [], []
    log_path = os.path.join(project, "audit", "log.jsonl")
    head_path = os.path.join(project, "audit", "head.json")
    log, head = [], None
    signatures_verified = head_verified = False
    if not os.path.exists(log_path):
        warnings.append("sem log de auditoria em audit/log.jsonl")
        status = "warning"
        return log, {"status": status, "signatures_verified": False, "head_verified": False,
                     "errors": errors, "warnings": warnings}
    try:
        log = audit_chain.read_log(log_path)
    except (OSError, ValueError) as exc:
        errors.append("log ilegivel: %s" % exc)
        return [], {"status": "broken", "signatures_verified": False, "head_verified": False,
                    "errors": errors, "warnings": warnings}
    if os.path.exists(head_path):
        try:
            with open(head_path, encoding="utf-8") as fh:
                head = json.load(fh)
        except (OSError, ValueError) as exc:
            errors.append("head ilegivel: %s" % exc)

    keys = {}
    try:
        from cryptography.hazmat.primitives import serialization
        for pem in glob.glob(os.path.join(project, "keys", "*.pem")):
            with open(pem, "rb") as fh:
                keys[os.path.splitext(os.path.basename(pem))[0]] = serialization.load_pem_public_key(fh.read())
    except ImportError:
        warnings.append("biblioteca cryptography ausente: assinaturas nao verificadas")

    if keys:
        import audit_signing
        verifier = audit_signing.AuditVerifier(keys)
        errs, warns = verifier.verify(log, head)
        errors.extend(errs)
        warnings.extend(warns)
        signatures_verified = not any("assinatura" in e or "sem assinatura" in e or "key_id" in e or "chave" in e for e in errs)
        head_verified = head is not None and not any(e.startswith("head") or "truncado" in e or "head assinado" in e for e in errs)
    else:
        errors.extend(audit_chain.verify_chain(log))
        warnings.append("sem chaves publicas em keys/: assinaturas e head nao verificados")
    status = "broken" if errors else ("warning" if warnings else "ok")
    return log, {"status": status, "signatures_verified": bool(keys) and signatures_verified and not errors,
                 "head_verified": bool(keys) and head_verified and not errors,
                 "errors": errors, "warnings": warnings}


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


# ----------------------------------------------------------------------------- derivacao
def derive(loaded, log, integrity):
    features = loaded["features"]
    tasks = loaded["tasks"]
    agents = loaded["agents"]
    approvals = loaded["approvals"]
    reports = loaded["reports"]

    task_by_id = {t["task_id"]: t for t in tasks}
    status_of = {t["task_id"]: t["state"]["status"] for t in tasks}

    task_rows = []
    for t in tasks:
        deps = t.get("dependencies", {}).get("depends_on", [])
        task_rows.append({
            "task_id": t["task_id"], "feature_id": t["feature_id"], "title": t["title"],
            "role": t["assigned_agent"].get("role"), "agent_id": t["assigned_agent"]["agent_id"],
            "status": t["state"]["status"], "contract_version": t["contract_version"],
            "depends_on": list(deps),
            "blocked_by": [d for d in deps if status_of.get(d) != "completed"],
            "parallelizable": bool(t.get("dependencies", {}).get("parallelizable", False)),
            "risk_level": t["risk"]["level"], "environment": t["permissions"]["environment"],
            "criteria_total": len(t["acceptance_criteria"]),
            "rejection_count": t["state"].get("rejection_count", 0),
        })

    rtm_rows = []
    for f in features:
        active = {r["id"]: r for r in f["requirements"] if r["status"] == "active"}
        for entry in f["rtm"]:
            req = active.get(entry["requirement_id"])
            if req is None:
                continue
            missing = [tid for tid in entry["task_ids"] if tid not in task_by_id]
            states = [status_of[tid] for tid in entry["task_ids"] if tid in task_by_id]
            if missing:
                state = "broken_link"
            elif states and all(s == "completed" for s in states):
                state = "covered"
            elif any(s in ("in_progress", "executed", "validated", "completed", "blocked", "rejected") for s in states):
                state = "in_progress"
            else:
                state = "not_started"
            rtm_rows.append({
                "feature_id": f["feature_id"], "requirement_id": req["id"], "version": req["version"],
                "kind": req["kind"], "statement": req["statement"], "status": state,
                "task_ids": list(entry["task_ids"]), "criterion_ids": list(entry["criterion_ids"]),
                "missing_task_ids": missing,
            })

    feature_rows = []
    for f in features:
        fid = f["feature_id"]
        ft = [r for r in task_rows if r["feature_id"] == fid]
        done = sum(1 for r in ft if r["status"] == "completed")
        fr = [r for r in rtm_rows if r["feature_id"] == fid]
        feature_rows.append({
            "feature_id": fid, "title": f["title"], "cycle": f["cycle"]["number"],
            "business_priority": f["business_priority"]["level"], "status": f["state"]["status"],
            "plan_approval": f["approval"]["plan"]["status"],
            "acceptance": f["approval"].get("acceptance", {}).get("status", "pending"),
            "tasks_total": len(ft), "tasks_completed": done,
            "tasks_blocked": sum(1 for r in ft if r["status"] == "blocked"),
            "progress_pct": int(round(100 * done / len(ft))) if ft else 0,
            "requirements_total": len(fr),
            "requirements_covered": sum(1 for r in fr if r["status"] == "covered"),
            "risks_open": len(f.get("risks", [])),
        })

    def approval_item(a):
        dec = a.get("decision")
        decided = None
        if dec:
            decided = {"choice": dec["choice"], "decided_by": dec["decided_by"], "decided_at": dec["decided_at"]}
            if dec.get("selected_option_id"):
                decided["selected_option_id"] = dec["selected_option_id"]
        op = a.get("operation")
        return {
            "request_id": a["request_id"], "request_type": a["request_type"], "status": a["status"],
            "title": a["title"], "summary": a["summary"], "feature_id": a["feature_id"],
            "task_id": a.get("task_id"), "risk_level": a["risk"]["level"],
            "created_at": a["created_at"], "expires_at": a["expires_at"],
            "blocked_task_ids": list(a["blocks"]["blocked_task_ids"]),
            "independent_work_continues": a["blocks"]["independent_work_continues"],
            "operation": ({"environment": op["environment"], "resource_class": op["resource_class"],
                           "operation": op["operation"], "destructive": op["destructive"]} if op else None),
            "required_acknowledgements": list(a.get("required_acknowledgements", [])),
            "decided": decided,
        }

    pending = [approval_item(a) for a in approvals if a["status"] == "pending"]
    pending.sort(key=lambda p: (-len(p["blocked_task_ids"]), -SEVERITY[p["risk_level"]], p["expires_at"]))
    decided_items = [approval_item(a) for a in approvals if a["status"] != "pending"]
    decided_items.sort(key=lambda p: (p["decided"] or {}).get("decided_at", p["created_at"]), reverse=True)

    decisions = []
    for a in approvals:
        if a["request_type"] not in ("architecture_decision", "scope_change_decision"):
            continue
        dec = a.get("decision") or {}
        chosen_id = dec.get("selected_option_id")
        opts = [{"option_id": o["option_id"], "label": o["label"], "description": o["description"],
                 "risks": list(o["risks"])} for o in a["options"]]
        selected = next((o for o in opts if o["option_id"] == chosen_id), None)
        discarded = [o for o in opts if chosen_id and o["option_id"] != chosen_id]
        rec = a.get("recommendation")
        decisions.append({
            "request_id": a["request_id"], "feature_id": a["feature_id"], "title": a["title"],
            "request_type": a["request_type"], "status": a["status"], "selected_option": selected,
            "discarded_alternatives": discarded,
            "recommendation": {"option_id": rec["option_id"], "rationale": rec["rationale"]} if rec else None,
            "followed_recommendation": (rec["option_id"] == chosen_id) if (rec and chosen_id) else None,
            "decided_at": dec.get("decided_at"),
        })

    agent_rows = []
    for ag in agents:
        mine = [r for r in task_rows if r["agent_id"] == ag["agent_id"]]
        agent_rows.append({
            "agent_id": ag["agent_id"], "name": ag["name"], "role": ag["role"], "status": ag["status"],
            "contract_version": ag["contract_version"],
            "tasks_in_progress": [r["task_id"] for r in mine if r["status"] == "in_progress"],
            "tasks_assigned_total": len(mine),
        })

    risk_rows = []
    for f in features:
        for r in f.get("risks", []):
            risk_rows.append({"source": "feature", "source_id": r["id"], "feature_id": f["feature_id"],
                              "description": r["description"], "severity": r["severity"],
                              "mitigation": r.get("mitigation")})
    for a in approvals:
        if a["status"] != "pending":
            continue
        for r in a["risk"]["items"]:
            risk_rows.append({"source": "approval", "source_id": a["request_id"], "feature_id": a["feature_id"],
                              "description": r["description"], "severity": r["severity"],
                              "mitigation": r.get("mitigation")})
    risk_rows.sort(key=lambda r: -SEVERITY[r["severity"]])

    visible = [e for e in log if e.get("panel_visible", True) is not False]
    timeline = [{
        "sequence": e["sequence"], "event_id": e["event_id"], "timestamp": e["timestamp"],
        "event_type": e["event_type"], "actor_type": e["actor"]["type"], "actor_id": e["actor"]["id"],
        "summary": e["summary"], "feature_id": e.get("feature_id"), "task_id": e.get("task_id"),
    } for e in reversed(visible)][:200]

    nodes = [{"id": r["task_id"], "feature_id": r["feature_id"], "title": r["title"], "status": r["status"]} for r in task_rows]
    edges, missing_nodes = [], []
    for r in task_rows:
        for d in r["depends_on"]:
            edges.append({"from": d, "to": r["task_id"]})
            if d not in task_by_id and d not in missing_nodes:
                missing_nodes.append(d)

    lines = ["flowchart TD",
             "  classDef completed fill:#d4edda,stroke:#2e7d32,color:#111",
             "  classDef in_progress fill:#fff3cd,stroke:#b8860b,color:#111",
             "  classDef blocked fill:#f8d7da,stroke:#c62828,color:#111",
             "  classDef other fill:#e9ecef,stroke:#6c757d,color:#111"]
    by_feature = {}
    for n in nodes:
        by_feature.setdefault(n["feature_id"], []).append(n)
    for fid, group in by_feature.items():
        lines.append('  subgraph %s["%s"]' % (mermaid_id("f_", fid), mermaid_label(fid)))
        for n in group:
            lines.append('    %s["%s: %s"]' % (mermaid_id("n_", n["id"]), mermaid_label(n["id"], 20), mermaid_label(n["title"])))
        lines.append("  end")
    for m in missing_nodes:
        lines.append('  %s["%s ausente"]' % (mermaid_id("n_", m), mermaid_label(m, 20)))
    for e in edges:
        lines.append("  %s --> %s" % (mermaid_id("n_", e["from"]), mermaid_id("n_", e["to"])))
    for n in nodes:
        cls = n["status"] if n["status"] in ("completed", "in_progress", "blocked") else "other"
        lines.append("  class %s %s" % (mermaid_id("n_", n["id"]), cls))
    for m in missing_nodes:
        lines.append("  class %s blocked" % mermaid_id("n_", m))

    exec_rows = []
    for rp in reports:
        cr = rp["criteria_results"]
        exec_rows.append({
            "report_id": rp["report_id"], "task_id": rp["task_id"], "status": rp["status"],
            "finished_at": rp["timing"]["finished_at"],
            "tests": {k: rp["tests"][k] for k in ("executed", "passed", "failed", "skipped")},
            "criteria": {"met": sum(1 for c in cr if c["result"] == "met"),
                         "not_met": sum(1 for c in cr if c["result"] == "not_met"),
                         "not_verifiable": sum(1 for c in cr if c["result"] == "not_verifiable")},
            "evidence_count": len(rp["evidence"]), "intervention_needed": rp["intervention"]["needed"],
        })

    def count(rows, key):
        out = {}
        for r in rows:
            out[r[key]] = out.get(r[key], 0) + 1
        return out

    overview = {
        "features_by_status": count(feature_rows, "status"),
        "tasks_by_status": count(task_rows, "status"),
        "pending_approvals": len(pending),
        "pending_high_risk": sum(1 for p in pending if p["risk_level"] in ("high", "critical")),
        "blocked_tasks": sum(1 for r in task_rows if r["status"] == "blocked" or (r["blocked_by"] and r["status"] in ("ready", "in_progress"))),
        "last_event_at": log[-1]["timestamp"] if log else None,
    }

    return {
        "overview": overview, "features": feature_rows, "tasks": task_rows, "rtm": rtm_rows,
        "approvals": {"pending": pending, "recent": decided_items[:10]},
        "decisions": decisions, "agents": agent_rows, "risks": risk_rows, "timeline": timeline,
        "graphs": {"dependencies": {"nodes": nodes, "edges": edges, "missing_nodes": missing_nodes,
                                    "mermaid": "\n".join(lines)}},
        "executions": exec_rows,
    }


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


# ----------------------------------------------------------------------------- escrita
def build(project, out, schemas_dir, now=None):
    loaded, source_errors = load_sources(project, schemas_dir)
    log, integrity = check_integrity(project)
    views = derive(loaded, log, integrity)
    views["engineering"] = derive_engineering(loaded["blueprints"])

    project_id = log[0].get("project_id") if log else None
    manifest = {
        "derived": True,
        "generated_at": (now or datetime.datetime.now(datetime.timezone.utc)).isoformat(timespec="seconds"),
        "project_id": project_id, "builder_version": BUILDER_VERSION,
        "source": {"log_id": log[0].get("log_id") if log else None, "event_count": len(log),
                   "head_sequence": log[-1]["sequence"] if log else None,
                   "head_hash": log[-1]["hash"] if log else None},
        "integrity": integrity, "redactions": 0,
        "contains_secrets": False, "contains_model_reasoning": False,
    }
    bundle = {"schema_version": "0.1.0", "manifest": manifest, **views, "source_errors": source_errors}
    counter = [0]
    bundle = redact_tree(bundle, counter)
    bundle["manifest"]["redactions"] = counter[0]
    if counter[0]:
        bundle["manifest"]["integrity"]["warnings"].append(
            "%d trecho(s) com aparencia de segredo foram mascarados nas fontes" % counter[0])
        if bundle["manifest"]["integrity"]["status"] == "ok":
            bundle["manifest"]["integrity"]["status"] = "warning"

    os.makedirs(os.path.join(out, "data"), exist_ok=True)

    def dump(path, obj):
        text = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        return text

    for key, value in bundle.items():
        if key != "schema_version":
            dump(os.path.join(out, "data", key + ".json"), value)
    dump(os.path.join(out, "panel-data.json"), bundle)
    compact = json.dumps(bundle, ensure_ascii=False, sort_keys=True).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    with open(os.path.join(out, "data.js"), "w", encoding="utf-8") as fh:
        fh.write("window.AISEF_DATA = " + compact + ";\n")
    return bundle


def install_page(out):
    """Copia a pagina e o Mermaid local (o painel abre via file:// e funciona sem internet)."""
    shutil.copy(os.path.join(HERE, "index.html"), os.path.join(out, "index.html"))
    vendor = os.path.join(HERE, "vendor", "mermaid.min.js")
    if os.path.exists(vendor):
        os.makedirs(os.path.join(out, "vendor"), exist_ok=True)
        shutil.copy(vendor, os.path.join(out, "vendor", "mermaid.min.js"))


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--schemas", default=HERE)
    ap.add_argument("--with-page", action="store_true", help="copia index.html e o Mermaid local para <out>")
    args = ap.parse_args(argv[1:])
    bundle = build(args.project, args.out, args.schemas)
    if args.with_page:
        install_page(args.out)
    m = bundle["manifest"]
    print("painel gerado em %s | integridade: %s | eventos: %d | redacoes: %d | fontes invalidas: %d" % (
        args.out, m["integrity"]["status"], m["source"]["event_count"], m["redactions"], len(bundle["source_errors"])))
    for e in m["integrity"]["errors"]:
        print("  ERRO:", e)
    for w in m["integrity"]["warnings"]:
        print("  aviso:", w)
    return 0 if m["integrity"]["status"] != "broken" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
