#!/usr/bin/env python3
"""AISEF sysgraph (0.14, G-07): o grafo do proprio sistema, consultavel, sem modelo.

Os contratos ja formam um grafo: requisito -> tarefa -> criterio -> teste -> arquivo -> evidencia, mais blueprint,
decisoes e ADRs. Este modulo responde as perguntas que a reabertura, o rebase-req e a revisao fazem a mao:

    python -I aisef_sysgraph.py impact --project . --req REQ-001     tarefas, criterios, testes, arquivos e evidencias
    python -I aisef_sysgraph.py impact --project . --file src/a.py   requisitos e tarefas que tocam o arquivo
    python -I aisef_sysgraph.py why    --project . --task T-001      requisitos, decisoes, ADRs e blueprint da tarefa
    (todas aceitam --json)

Arquivos de uma tarefa: scope.paths_allowed (globs) e os arquivos que os Execution Reports dela criaram ou mudaram.
Somente leitura e somente stdlib.
"""
import argparse
import fnmatch
import glob
import json
import os
import re
import sys

ADR_RE = re.compile(r"(?:docs/)?adr/[\w./-]+\.md|\bADR[- ]?\d{3,4}\b", re.I)


def _load(project, sub):
    out = []
    for path in sorted(glob.glob(os.path.join(project, ".aisef", sub, "*.json"))):
        try:
            with open(path, encoding="utf-8") as fh:
                out.append(json.load(fh))
        except (OSError, ValueError):
            continue
    return out


def load(project):
    """Indices do projeto: features, tarefas, relatorios e blueprints."""
    feats = {f["feature_id"]: f for f in _load(project, "contracts/features") if f.get("feature_id")}
    tasks = {t["task_id"]: t for t in _load(project, "contracts/tasks") if t.get("task_id")}
    reports = [r for r in _load(project, "reports") if r.get("task_id")]
    bps = [b for b in _load(project, "blueprints") if b.get("blueprint_id")]
    return feats, tasks, reports, bps


def _req_ids(task):
    return [x.get("id") for x in ((task.get("requirements") or {}).get("requirement_ids") or []) if isinstance(x, dict)]


def task_files(task, reports):
    """(globs do escopo, arquivos reais dos relatorios)."""
    globs = list(((task.get("scope") or {}).get("paths_allowed") or []))
    real = set()
    for r in reports:
        if r.get("task_id") != task["task_id"]:
            continue
        files = r.get("files") or {}
        for kind in ("created", "modified", "deleted"):
            for fe in files.get(kind) or []:
                p = fe.get("path") if isinstance(fe, dict) else fe
                if p:
                    real.add(p.replace("\\", "/"))
    return globs, sorted(real)


def impact_req(project, req_id):
    feats, tasks, reports, bps = load(project)
    feat = next((f for f in feats.values() if any(r["id"] == req_id for r in f.get("requirements", []))), None)
    if feat is None:
        raise SystemExit("requisito %s nao existe em nenhum Feature Contract" % req_id)
    req = next(r for r in feat["requirements"] if r["id"] == req_id)
    out = {"requirement": {"id": req_id, "version": req.get("version"), "statement": req.get("statement"),
                           "feature_id": feat["feature_id"]}, "tasks": [], "criteria": [], "tests": [], "files": [],
           "evidence": [], "blueprint_elements": []}
    files, real = set(), set()
    for t in sorted(tasks.values(), key=lambda x: x["task_id"]):
        if req_id not in _req_ids(t):
            continue
        out["tasks"].append({"task_id": t["task_id"], "title": t.get("title"), "status": (t.get("state") or {}).get("status"),
                             "agent": (t.get("assigned_agent") or {}).get("agent_id")})
        for c in t.get("acceptance_criteria") or []:
            if req_id in (c.get("requirement_ids") or []) or not c.get("requirement_ids"):
                out["criteria"].append({"id": c["id"], "task_id": t["task_id"], "description": c.get("description")})
                cmd = (c.get("verification") or {}).get("command")
                if cmd:
                    out["tests"].append({"task_id": t["task_id"], "command": cmd})
        tests = t.get("tests") or {}
        for cmd in tests.get("commands") or []:
            out["tests"].append({"task_id": t["task_id"], "command": cmd})
        for seam in tests.get("seams") or []:
            out["tests"].append({"task_id": t["task_id"], "seam": seam})
        g, r = task_files(t, reports)
        files.update(g)
        real.update(r)
        for rep in reports:
            if rep.get("task_id") == t["task_id"]:
                for ev in rep.get("evidence") or []:
                    out["evidence"].append({"report_id": rep.get("report_id"), "id": ev.get("id"), "type": ev.get("type"),
                                            "ref": ev.get("ref")})
    for b in bps:
        if b.get("feature_id") != feat["feature_id"] or (b.get("state") or {}).get("status") == "superseded":
            continue
        for section, items in (b.get("architecture") or {}).items():
            for it in items if isinstance(items, list) else []:
                if isinstance(it, dict) and req_id in (it.get("requirement_ids") or []):
                    out["blueprint_elements"].append({"blueprint_id": b["blueprint_id"], "section": section,
                                                      "id": it.get("id"), "name": it.get("name")})
    out["tests"] = [dict(t) for t in {json.dumps(x, sort_keys=True): x for x in out["tests"]}.values()]
    out["files"] = sorted(files | real)
    return out


def _matches(path, task, reports):
    globs, real = task_files(task, reports)
    p = path.replace("\\", "/").lstrip("./")
    if p in real:
        return "relatorio"
    for g in globs:
        g2 = g.replace("\\", "/").lstrip("./")
        if fnmatch.fnmatch(p, g2) or (g2.endswith("/*") and p.startswith(g2[:-1])) or p == g2.rstrip("/"):
            return "escopo (%s)" % g
    return None


def impact_file(project, path):
    feats, tasks, reports, _bps = load(project)
    out = {"file": path, "tasks": [], "requirements": []}
    reqs = {}
    for t in sorted(tasks.values(), key=lambda x: x["task_id"]):
        how = _matches(path, t, reports)
        if not how:
            continue
        out["tasks"].append({"task_id": t["task_id"], "title": t.get("title"), "via": how,
                             "status": (t.get("state") or {}).get("status"), "feature_id": t.get("feature_id")})
        for rid in _req_ids(t):
            f = feats.get(t.get("feature_id")) or {}
            r = next((x for x in f.get("requirements", []) if x["id"] == rid), None)
            reqs[rid] = {"id": rid, "feature_id": t.get("feature_id"), "statement": (r or {}).get("statement"),
                         "version": (r or {}).get("version")}
    out["requirements"] = [reqs[k] for k in sorted(reqs)]
    return out


def why_task(project, task_id):
    feats, tasks, _reports, bps = load(project)
    t = tasks.get(task_id)
    if t is None:
        raise SystemExit("tarefa %s nao existe" % task_id)
    f = feats.get(t.get("feature_id")) or {}
    ids = set(_req_ids(t))
    out = {"task": {"task_id": task_id, "title": t.get("title"), "feature_id": t.get("feature_id")},
           "requirements": [{"id": r["id"], "version": r.get("version"), "origin": r.get("origin"),
                             "statement": r.get("statement")} for r in f.get("requirements", []) if r["id"] in ids],
           "decisions": [], "adrs": [], "blueprint": None, "triage": f.get("triage")}
    for d in f.get("architectural_decisions") or []:
        out["decisions"].append({k: d.get(k) for k in ("id", "title", "version", "status") if d.get(k) is not None})
    refs = json.dumps(t.get("context") or {}) + json.dumps(f.get("architectural_decisions") or [])
    for b in bps:
        if b.get("feature_id") == t.get("feature_id") and (b.get("state") or {}).get("status") != "superseded":
            out["blueprint"] = {"blueprint_id": b["blueprint_id"], "status": (b.get("state") or {}).get("status")}
            refs += json.dumps(b.get("decisions") or b.get("adrs") or [])
    out["adrs"] = sorted(set(m.group(0) for m in ADR_RE.finditer(refs)))
    return out


def render(kind, res):
    L = []
    if kind == "req":
        r = res["requirement"]
        L.append("%s v%s (%s): %s" % (r["id"], r["version"], r["feature_id"], r["statement"]))
        L.append("Tarefas: " + (", ".join("%s [%s]" % (t["task_id"], t["status"]) for t in res["tasks"]) or "-"))
        L.append("Criterios: " + (", ".join(c["id"] for c in res["criteria"]) or "-"))
        L.append("Testes: " + ("; ".join(t.get("command") or "seam " + t.get("seam", "") for t in res["tests"]) or "-"))
        L.append("Arquivos: " + (", ".join(res["files"]) or "-"))
        L.append("Evidencias: " + (", ".join("%s/%s" % (e["report_id"], e["id"]) for e in res["evidence"]) or "-"))
        L.append("Blueprint: " + (", ".join("%s %s" % (b["blueprint_id"], b["id"]) for b in res["blueprint_elements"]) or "-"))
    elif kind == "file":
        L.append("%s" % res["file"])
        L.append("Tarefas: " + (", ".join("%s (%s)" % (t["task_id"], t["via"]) for t in res["tasks"]) or "nenhuma"))
        L.append("Requisitos: " + (", ".join(r["id"] for r in res["requirements"]) or "nenhum"))
    else:
        t = res["task"]
        L.append("%s (%s): %s" % (t["task_id"], t["feature_id"], t["title"]))
        L.append("Requisitos: " + (", ".join("%s v%s (%s)" % (r["id"], r["version"], r["origin"]) for r in res["requirements"]) or "-"))
        L.append("Decisoes: " + (", ".join(d.get("id", "?") for d in res["decisions"]) or "-"))
        L.append("ADRs: " + (", ".join(res["adrs"]) or "-"))
        L.append("Blueprint: " + (res["blueprint"]["blueprint_id"] if res["blueprint"] else "-"))
        if res.get("triage"):
            L.append("Caminho: %s" % res["triage"]["path"])
    return "\n".join(L)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["impact", "why"])
    p.add_argument("--project", default=".")
    p.add_argument("--req")
    p.add_argument("--file")
    p.add_argument("--task")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    project = os.path.abspath(a.project)
    if a.command == "impact" and a.req:
        kind, res = "req", impact_req(project, a.req)
    elif a.command == "impact" and a.file:
        kind, res = "file", impact_file(project, a.file)
    elif a.command == "why" and a.task:
        kind, res = "task", why_task(project, a.task)
    else:
        p.error("impact pede --req ou --file; why pede --task")
    print(json.dumps(res, ensure_ascii=False, indent=2) if a.json else render(kind, res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
