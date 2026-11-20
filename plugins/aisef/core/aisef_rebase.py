#!/usr/bin/env python3
"""AISEF rebase-req (F-07): leva tarefas e blueprint a versao atual da feature e dos requisitos

H-01 (0.14): saiu de aisef_new.py sem mudar o codigo; aisef_new reexporta tudo."""
import argparse
import glob
import json
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_catalog  # noqa: E402
import aisef_project as ap  # noqa: E402


REBASE_OK = ("draft", "ready", "rejected", "blocked")  # tarefa que ainda nao comecou (ou voltou ao executor)


def rebase_plan(project, feature_id):
    """F-07: o que o rebase-req faria. Devolve {feature_version, changed, tasks: [...], blueprints: [...], blocked: [...]}.
    Tarefa com requisito desatualizado e nao iniciada: nova versao. Demais tarefas: so acertar feature_contract_version.
    Tarefa iniciada ou concluida com requisito desatualizado: bloqueada (reabrir). Blueprint que cita requisito que mudou:
    bloqueado (nova versao do blueprint); o resto: acertar a base."""
    root = ap.aisef_dir(project)
    fpath = os.path.join(root, "contracts", "features", feature_id + ".json")
    if not os.path.exists(fpath):
        raise SystemExit("feature %s nao existe" % feature_id)
    with open(fpath, encoding="utf-8") as fh:
        feat = json.load(fh)
    fv = feat["contract_version"]
    current = {r["id"]: r["version"] for r in feat["requirements"]}
    out = {"feature": feat, "feature_path": fpath, "feature_version": fv, "changed": set(), "tasks": [], "blueprints": [],
           "blocked": []}
    for item in feat["task_plan"]:
        tpath = os.path.join(root, "contracts", "tasks", item["task_id"] + ".json")
        if not os.path.exists(tpath):
            continue
        with open(tpath, encoding="utf-8") as fh:
            t = json.load(fh)
        stale = [x["id"] for x in t["requirements"]["requirement_ids"] if x["id"] in current and x["version"] != current[x["id"]]]
        out["changed"].update(stale)
        status = (t.get("state") or {}).get("status")
        if stale and status not in REBASE_OK:
            out["blocked"].append("%s (%s) usa %s em versao antiga: reabra a feature para mudar uma tarefa ja iniciada "
                                  "(aisef-feature, Reabertura)" % (t["task_id"], status, ", ".join(stale)))
        elif stale or t["feature_contract_version"] != fv or item["contract_version"] != t["contract_version"]:
            out["tasks"].append({"path": tpath, "task": t, "stale": stale})
    for bpath in sorted(glob.glob(os.path.join(root, "blueprints", "*.json"))):
        with open(bpath, encoding="utf-8") as fh:
            b = json.load(fh)
        if b.get("feature_id") != feature_id or b.get("feature_contract_version") == fv or \
                (b.get("state") or {}).get("status") == "superseded":
            continue
        cited = sorted(r for r in out["changed"] if r in json.dumps(b))
        if cited:
            out["blocked"].append("%s cita %s, que mudou: crie a nova versao do blueprint (aisef_new.py blueprint)"
                                  % (b["blueprint_id"], ", ".join(cited)))
        else:
            out["blueprints"].append({"path": bpath, "blueprint": b})
    return out


def cmd_rebase(project, feature_id, dry_run=False):
    """Leva tarefas e blueprint a versao atual do Feature Contract e dos requisitos, com um contract_changed."""
    pl = rebase_plan(project, feature_id)
    fv, feat, now = pl["feature_version"], pl["feature"], ap.now_iso()
    current = {r["id"]: r["version"] for r in feat["requirements"]}
    lines = []
    for x in pl["tasks"]:
        t = x["task"]
        if x["stale"]:
            for ref in t["requirements"]["requirement_ids"]:
                if ref["id"] in current:
                    ref["version"] = current[ref["id"]]
            t["contract_version"] += 1
            lines.append("%s v%d: %s na versao atual" % (t["task_id"], t["contract_version"], ", ".join(x["stale"])))
        else:
            lines.append("%s: base na v%d da feature" % (t["task_id"], fv))
        t["feature_contract_version"] = fv
        for item in feat["task_plan"]:
            if item["task_id"] == t["task_id"]:
                item["contract_version"] = t["contract_version"]
    for x in pl["blueprints"]:
        x["blueprint"]["feature_contract_version"] = fv
        lines.append("%s: base na v%d da feature (nao cita requisito que mudou)" % (x["blueprint"]["blueprint_id"], fv))
    if not dry_run and (pl["tasks"] or pl["blueprints"]):
        problems = []
        for x in pl["tasks"]:
            problems += ["%s: %s" % (x["task"]["task_id"], p) for p in ap.validate(x["task"], "task-contract.schema.v0.1.json")]
        problems += ap.validate(feat, "feature-contract.schema.v0.1.json")
        if problems:
            raise SystemExit("nada foi gravado:\n - " + "\n - ".join(problems[:20]))
        for x in pl["tasks"]:
            ap.write_json(x["path"], x["task"])
        for x in pl["blueprints"]:
            ap.write_json(x["path"], x["blueprint"])
        ap.write_json(pl["feature_path"], feat)
        ap.append(project, {"event_type": "contract_changed", "actor": {"type": "orchestrator", "id": "orchestrator"},
                            "feature_id": feature_id,
                            "summary": "rebase para a v%d de %s: %s" % (fv, feature_id, "; ".join(lines))[:900],
                            "subject": {"kind": "feature_contract", "id": feature_id, "version": fv}})
    return lines, pl["blocked"]
