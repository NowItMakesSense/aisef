#!/usr/bin/env python3
"""AISEF ui_probe: rotas da sonda (arquivo ou Task Contract), ignore com motivo e conferencia das provas (V-05, V-06)."""
import hashlib
import json
import os
import urllib.parse


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def apply_ignore(findings, ignore):
    kept, ignored = [], []
    for f in findings:
        hit = next((i for i in ignore if i.get("rule") in (f["rule"], "*") and i.get("selector", "") in (f.get("selector") or "")), None)
        if hit:
            ignored.append(dict(f, reason=hit.get("reason") or "sem motivo"))
        else:
            kept.append(f)
    return kept, ignored


def verify_report(path):
    """Confere o hash de cada captura citada no relatorio. Devolve a lista de problemas (vazia = provas intactas)."""
    base = os.path.dirname(os.path.abspath(path))
    with open(path, encoding="utf-8") as fh:
        rep = json.load(fh)
    refs = [s for s in rep.get("shots", [])] + [f["shot"] for f in rep.get("findings", []) if f.get("shot")]
    for it in rep.get("interactions", []):
        refs += [it[k] for k in ("before", "after") if it.get(k)]
    out = []
    for r in refs:
        p = os.path.normpath(os.path.join(base, r["path"]))
        if not p.startswith(base):
            out.append("%s: caminho fora da pasta do relatorio" % r["path"])
        elif not os.path.exists(p):
            out.append("%s: captura ausente" % r["path"])
        elif sha256(p) != r["sha256"]:
            out.append("%s: captura alterada (hash diferente)" % r["path"])
    return out


def routes_from_task(project, task_id, base=None):
    """Rotas e gestos da `ui_behavior` do Task Contract (V-06). Devolve (rotas, ignore, pasta padrao do relatorio)."""
    root = os.path.join(os.path.abspath(project), ".aisef")
    path = os.path.join(root, "contracts", "tasks", task_id + ".json")
    with open(path, encoding="utf-8") as fh:
        task = json.load(fh)
    ub = task.get("ui_behavior")
    if not ub:
        raise SystemExit("%s sem ui_behavior: declare rotas, larguras, overflow, interacoes e estados no contrato" % task_id)
    base = base or ub.get("base_url")
    if not base:
        raise SystemExit("%s: diga onde a UI roda (--base http://127.0.0.1:<porta> ou ui_behavior.base_url)" % task_id)
    routes = []
    for r in ub["routes"]:
        its = [i for i in ub.get("interactions") or [] if i.get("route") in (None, r["name"])]
        routes.append(dict(r, url=urllib.parse.urljoin(base, r["path"]), interactions=its))
    ign_path = os.path.join(root, "ui-probe.ignore.json")
    ignore = []
    if os.path.isfile(ign_path):
        with open(ign_path, encoding="utf-8") as fh:
            ignore = json.load(fh).get("ignore") or []
    return routes, ignore, os.path.join(root, "reports", "ui", task_id, "probe")


def load_routes(a):
    if a.task:
        routes, ignore, out = routes_from_task(a.project, a.task, a.base or a.url)
        a.out = a.out or out
        return routes, ignore
    if a.routes:
        with open(a.routes, encoding="utf-8") as fh:
            spec = json.load(fh)
        base = spec.get("base") or a.url or ""
        routes = [dict(r, url=urllib.parse.urljoin(base, r.get("path", "")) if base else r["url"]) for r in spec["routes"]]
        return routes, spec.get("ignore") or []
    return [{"name": "page", "url": a.url}], []
