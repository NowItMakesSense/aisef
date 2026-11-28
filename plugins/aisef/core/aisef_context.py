#!/usr/bin/env python3
"""AISEF context engineering (v0.4.0): pacote de contexto por tarefa e memoria de projeto.

    python -I aisef_context.py pack     --project <repo> --task T-001 [--limit 20] [--json]
    python -I aisef_context.py remember --project <repo> --summary "..." --source-kind file|url|task|decision
                                        --source-ref <ref> [--detail ...] [--tags a,b] [--task T] [--feature F]
                                        [--created-by orchestrator] [--supersedes K-001]
    python -I aisef_context.py graph    --project <repo>          (mostra qual graph MCP esta configurado)

O pacote tem as tres camadas do Task Contract:
  mandatory   caminho do contrato, requisitos ligados (texto), criterios de aceite e decisoes aprovadas que afetam a tarefa;
  referenced  arquivos existentes que casam com scope.paths_allowed (com limite) e docs citados;
  on_demand   entradas de conhecimento relevantes; com o Graphify ligado e o grafo gerado, o que o grafo liga a tarefa
              (decisoes, docs, quem depende do codigo dela), lido direto do graph.json; e, se houver graph MCP no
              .mcp.json, consultas sugeridas. Sem o Graphify, usa o grafo nativo de imports (G-06, quem importa e o que
              e importado pelos arquivos da tarefa). `pack --no-graph` desliga o grafo (para medir o efeito, G-05).
O pack nao altera o projeto: so grava o cache do grafo nativo em .aisef/runtime/graph.json (fora do Git), quando um
arquivo de codigo mudou. `remember` e o unico comando que grava conhecimento (em .aisef/knowledge/).
Somente stdlib; jsonschema so e importado quando `remember` precisa validar.
"""
import argparse
import datetime
import fnmatch
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_graph  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python -I nao poe a pasta do script no path
from aisef_context_aux import *  # noqa: E402,F401,F403  (H-01)
from aisef_context_aux import _load_json, _now, _safe_key, _sensitive_patterns, _write_json  # noqa: E402,F401
DEFAULT_LIMIT = 20
KNOWLEDGE_LIMIT = 10
WALK_CAP = 50000  # teto de arquivos visitados: o pack precisa ser rapido mesmo em monorepo
SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", ".aisef", "__pycache__", ".venv", "venv", "dist", "build",
             ".next", ".tox", ".mypy_cache", ".pytest_cache", "target", ".idea", ".vscode", "graphify-out", ".gradle"}


def _rel(project, path):
    return os.path.relpath(path, project).replace(os.sep, "/")


def _glob_files(project, patterns, forbidden, walk_cap=WALK_CAP):
    """Arquivos existentes que casam com os padroes (fnmatch, como o check_project: '*' cruza '/'). Um padrao sem
    curinga que nomeia uma pasta vale para tudo dentro dela. Devolve (caminhos ordenados, padroes sem nenhum arquivo)."""
    pats = []
    for p in patterns:
        p = p.replace("\\", "/")
        if p.startswith("./"):
            p = p[2:]
        if p.endswith("/"):
            p += "*"
        elif not any(c in p for c in "*?[") and os.path.isdir(os.path.join(project, p)):
            p += "/*"
        pats.append(p)
    forb = [(x[2:] if x.startswith("./") else x).replace("\\", "/") for x in forbidden]
    matched, hit, seen = [], set(), 0
    for root, dirs, files in os.walk(project):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            seen += 1
            if seen > walk_cap:
                break
            rel = _rel(project, os.path.join(root, name))
            for p in pats:
                if fnmatch.fnmatchcase(rel, p):
                    hit.add(p)
                    if not any(fnmatch.fnmatchcase(rel, x) for x in forb):
                        matched.append(rel)
                    break
        if seen > walk_cap:
            break
    return sorted(set(matched)), [p for p in pats if p not in hit]


def _words(text):
    return {w for w in re.findall(r"[a-z0-9]{4,}", text.lower())}


# ---------------------------------------------------------------------------- conhecimento
def load_knowledge(aisef_dir):
    """Entradas validas em sintaxe de .aisef/knowledge/K-*.json (a validacao completa e do check_knowledge)."""
    kdir = os.path.join(aisef_dir, "knowledge")
    out = []
    if not os.path.isdir(kdir):
        return out
    for name in sorted(os.listdir(kdir)):
        if re.fullmatch(r"K-\d+\.json", name):
            try:
                e = _load_json(os.path.join(kdir, name))
                if isinstance(e, dict) and e.get("id"):
                    out.append(e)
            except Exception:
                pass
    return out


def _relevant_knowledge(entries, task, feature_id, files, tokens, limit=KNOWLEDGE_LIMIT):
    fileset = set(files)
    scored = []
    import aisef_learn
    for e in entries:
        if e.get("status", "active") != "active" or not aisef_learn.injectable(e):
            continue
        score, why = 0, []
        if e.get("task_id") == task["task_id"]:
            score += 4
            why.append("mesma tarefa")
        if feature_id and e.get("feature_id") == feature_id:
            score += 2
            why.append("mesma feature")
        tags = {str(t).lower() for t in e.get("tags", [])}
        common = sorted(tags & tokens)
        if common:
            score += 2 * len(common)
            why.append("tags: " + ",".join(common))
        src = e.get("source", {})
        if src.get("kind") == "file" and src.get("ref", "").replace("\\", "/") in fileset:
            score += 3
            why.append("fonte e arquivo da tarefa")
        if src.get("kind") == "task" and src.get("ref") == task["task_id"]:
            score += 3
            why.append("fonte e a propria tarefa")
        overlap = sorted(_words(e.get("summary", "")) & tokens)
        if overlap:
            score += min(len(overlap), 3)
            why.append("termos: " + ",".join(overlap[:3]))
        if score:
            item = {"id": e["id"], "summary": e.get("summary", ""), "source": src,
                    "tags": e.get("tags", []), "score": score, "why": why}
            if e.get("lesson"):
                item.update(lesson=True, confidence=e["lesson"]["confidence"], action=e["lesson"]["action"])
            scored.append((-score, e["id"], item))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [s[2] for s in scored[:limit]], max(0, len(scored) - limit)


# ---------------------------------------------------------------------------- pacote
def _pick_blueprint(adir, feature_id):
    best = None
    bdir = os.path.join(adir, "blueprints")
    for name in sorted(os.listdir(bdir)) if os.path.isdir(bdir) else []:
        if not name.endswith(".json"):
            continue
        try:
            b = _load_json(os.path.join(bdir, name))
        except Exception:
            continue
        if b.get("feature_id") != feature_id or b.get("state", {}).get("status") == "superseded":
            continue
        if best is None or b.get("contract_version", 0) >= best[1].get("contract_version", 0):
            best = (os.path.join(bdir, name), b)
    return best


def _blueprint_elements(bp, req_ids):
    """Elementos do desenho que citam algum dos requisitos da tarefa."""
    out = []
    groups = [("component", bp.get("architecture", {}).get("components", []), "name"),
              ("endpoint", bp.get("backend", {}).get("endpoints", []), "path"),
              ("screen", bp.get("frontend", {}).get("screens", []), "name"),
              ("entity", bp.get("database", {}).get("entities", []), "name")]
    for kind, items, label in groups:
        for it in items:
            if set(it.get("requirement_ids", [])) & req_ids:
                out.append({"kind": kind, "id": it.get("id"), "name": it.get(label, ""),
                            "requirement_ids": sorted(set(it.get("requirement_ids", [])) & req_ids)})
    return out


def _decisions(adir, feature_id, task, bp, bp_elements, req_ids):
    """ADRs aprovados que afetam a tarefa: approvals architecture_decision aprovadas da feature (ligadas pelo contrato
    da tarefa, pelo blueprint que cita os requisitos, ou sem requisito declarado) e decisoes do blueprint com aprovacao."""
    by_id = {}
    adir_ap = os.path.join(adir, "approvals")
    for name in sorted(os.listdir(adir_ap)) if os.path.isdir(adir_ap) else []:
        if not name.endswith(".json"):
            continue
        try:
            a = _load_json(os.path.join(adir_ap, name))
        except Exception:
            continue
        ref = a.get("resulting_ref") or {}
        if a.get("request_type") != "architecture_decision" or a.get("status") != "approved" or a.get("feature_id") != feature_id:
            continue
        if ref.get("kind") != "architectural_decision" or not ref.get("id"):
            continue
        prev = by_id.get(ref["id"])
        if prev is None or ref.get("version", 0) >= prev["version"]:
            opt = next((o for o in a.get("options", []) if o.get("option_id") == (a.get("decision") or {}).get("selected_option_id")), None)
            by_id[ref["id"]] = {"id": ref["id"], "version": ref.get("version", 1), "title": a.get("title", ""),
                                "summary": a.get("summary", ""), "chosen": (opt or {}).get("label"),
                                "approval": a.get("request_id"), "cited_requirements": sorted(a.get("presented", {}).get("requirement_ids", []))}
    task_ids = {(d if isinstance(d, str) else d.get("id")) for d in task.get("requirements", {}).get("architectural_decision_ids", [])}
    bp_ids = {d.get("id") for d in (bp or {}).get("architecture", {}).get("decisions", [])}
    out, unapproved = [], []
    for did, d in sorted(by_id.items()):
        why = []
        if did in task_ids:
            why.append("citada no Task Contract")
        if did in bp_ids and bp_elements:
            why.append("adotada pelo blueprint, que cita os requisitos da tarefa")
        if d["cited_requirements"] and set(d["cited_requirements"]) & req_ids:
            why.append("a aprovacao cita requisitos da tarefa")
        if not d["cited_requirements"] and not why:
            why.append("decisao aprovada da feature (sem requisitos declarados)")
        if why:
            d = dict(d, why=why)
            d.pop("cited_requirements")
            out.append(d)
    for did in sorted((task_ids | bp_ids) - set(by_id)):
        if did and ((did in task_ids) or bp_elements):
            unapproved.append(did)
    return out, unapproved


def _doc_refs(project, task, bp):
    """Docs citados: contexto do Task Contract (origin doc/adr/file) e caminhos de .md/.rst/.txt/.adoc no texto do blueprint."""
    docs, seen = [], set()

    def add(path, origin):
        p = path.replace("\\", "/")
        if p not in seen and os.path.isfile(os.path.join(project, p)):
            seen.add(p)
            docs.append({"path": p, "origin": origin})

    for layer in ("mandatory", "referenced"):
        for c in task.get("context", {}).get(layer, []):
            if c.get("origin") in ("doc", "adr", "file"):
                add(c.get("ref", ""), "task:" + layer)
    if bp:
        text = json.dumps(bp, ensure_ascii=False)
        for m in sorted(set(re.findall(r"[\w./-]+\.(?:md|rst|txt|adoc)\b", text))):
            add(m, "blueprint")
    return docs


def _graphify_related(project, files, ids):
    """Bloco do Graphify para o pacote, ou None quando desligado ou sem grafo. Nunca levanta excecao."""
    try:
        import aisef_project
        cfg = aisef_project.load_config(project)
        st = aisef_project.graphify_status(project, cfg)
    except Exception:
        return None
    if not (st["enabled"] and st["exists"]):
        return _native_related(project, files, ids)
    g = aisef_graph.load(os.path.join(project, st["graph"]))
    if g is None:
        return {"graph": st["graph"], "error": "graph.json ilegivel ou grande demais", "items": [], "seeds": 0, "truncated": 0}
    out = aisef_graph.related(g, files, ids)
    out.update(aisef_graph.graph_info(project, st["graph"]) or {"path": st["graph"]})
    out["stale"] = st["stale"]
    out["newer_source"] = st["newer_source"]
    return out


def _native_related(project, files, ids):
    """Grafo nativo de imports (G-06), quando nao ha Graphify: so raio de impacto e dependencias do codigo."""
    rel = aisef_graph.ensure_native(project)
    g = aisef_graph.load(os.path.join(project, rel)) if rel else None
    if g is None:
        return None
    out = aisef_graph.related(g, files, ids)
    out.update(aisef_graph.graph_info(project, rel) or {"path": rel})
    out.update({"source": "native", "stale": False, "newer_source": None})
    return out


def build_pack(project, task_id, limit=DEFAULT_LIMIT, graph=True):
    """Pacote de contexto da tarefa. Levanta SystemExit se a tarefa nao existe. graph=False desliga o grafo."""
    project = os.path.abspath(project)
    adir = os.path.join(project, ".aisef")
    tpath = os.path.join(adir, "contracts", "tasks", task_id + ".json")
    if not os.path.isfile(tpath):
        raise SystemExit("tarefa %s nao encontrada em %s" % (task_id, tpath))
    task = _load_json(tpath)
    fid = task["feature_id"]
    warnings = []
    feature = {}
    fpath = os.path.join(adir, "contracts", "features", fid + ".json")
    if os.path.isfile(fpath):
        feature = _load_json(fpath)
    else:
        warnings.append("Feature Contract %s nao encontrado" % fid)

    # requisitos e regras de negocio ligados (texto vem do Feature Contract)
    reqs_by_id = {r["id"]: r for r in feature.get("requirements", [])}
    rules_by_id = {r["id"]: r for r in feature.get("business_rules", [])}
    reqs = []
    for ref in task.get("requirements", {}).get("requirement_ids", []):
        rid, ver = (ref, None) if isinstance(ref, str) else (ref.get("id"), ref.get("version"))
        r = reqs_by_id.get(rid)
        if r is None:
            warnings.append("requisito %s do contrato nao existe no Feature Contract" % rid)
            reqs.append({"id": rid, "version": ver, "statement": None})
            continue
        item = {"id": rid, "version": r["version"], "kind": r.get("kind"), "statement": r["statement"]}
        if ver is not None and ver != r["version"]:
            item["version_in_task"] = ver
            warnings.append("requisito %s: a tarefa cita v%s e o Feature Contract esta em v%s" % (rid, ver, r["version"]))
        reqs.append(item)
    rules = []
    for ref in task.get("requirements", {}).get("business_rule_ids", []):
        rid = ref if isinstance(ref, str) else ref.get("id")
        r = rules_by_id.get(rid)
        rules.append({"id": rid, "statement": r["statement"] if r else None, "exceptions": (r or {}).get("exceptions", [])})
    criteria = [{"id": c["id"], "description": c["description"], "required": c["required"],
                 "method": c["verification"]["method"], "evidence_expected": c["verification"]["evidence_expected"],
                 "requirement_ids": c.get("requirement_ids", [])} for c in task.get("acceptance_criteria", [])]
    req_ids = {r["id"] for r in reqs}

    bp_hit = _pick_blueprint(adir, fid)
    bp_path, bp = bp_hit if bp_hit else (None, None)
    if bp is None:
        warnings.append("a feature %s nao tem blueprint (nao superseded): sem decisoes nem elementos de desenho" % fid)
    elements = _blueprint_elements(bp, req_ids) if bp else []
    decisions, unapproved = _decisions(adir, fid, task, bp, elements, req_ids)
    for d in unapproved:
        warnings.append("decisao %s citada pela tarefa ou pelo blueprint sem aprovacao registrada (nao entra no pacote)" % d)

    # referenciado
    scope = task.get("scope", {})
    patterns = list(scope.get("paths_allowed", [])) + list(scope.get("exclusive_files", []))
    files, unmatched = _glob_files(project, patterns, scope.get("paths_forbidden", []))
    shown = files[:max(0, limit)]
    docs = _doc_refs(project, task, bp)

    # sob demanda
    tokens = _words(task.get("title", "") + " " + task.get("objective", ""))
    for p in patterns:
        tokens |= {w for w in re.findall(r"[a-z0-9]{3,}", p.lower()) if w not in ("src", "tests", "test", "lib", "app")}
    tokens.add(fid.lower())
    tokens.add(task.get("assigned_agent", {}).get("role", "-"))
    know, know_cut = _relevant_knowledge(load_knowledge(adir), task, fid, files, tokens)
    servers = detect_graph_servers(project) if graph else []
    queries, gnotes = graph_queries(project, servers, shown, task)
    graph_ids = set(req_ids) | {r["id"] for r in rules} | {d.get("id") for d in decisions if isinstance(d, dict)} | {task_id, fid}
    related = _graphify_related(project, files, graph_ids) if graph else None
    if related and related.get("stale"):
        warnings.append("grafo do Graphify velho (%s mudou depois dele): regenere com `graphify update .`"
                        % related.get("newer_source"))
    if related and related.get("items") is not None and not related.get("error"):
        context_mode = "native" if related.get("source") == "native" else "graphify"
    else:
        context_mode = "mcp" if servers else "none"

    architecture = _architecture_for(project, patterns + [f for f in files[:200]])
    design = _design_for(project, task)
    if design and design["status"] != "approved":
        warnings.append("autoridade de design em %s ainda nao aprovada: siga-a como proposta e avise o orquestrador"
                        % design["path"])
    return {
        "task_id": task_id, "feature_id": fid, "title": task.get("title"), "objective": task.get("objective"),
        "mandatory": {
            "task_contract": _rel(project, tpath),
            "feature_contract": _rel(project, fpath) if feature else None,
            "blueprint": ({"path": _rel(project, bp_path), "id": bp.get("blueprint_id"), "version": bp.get("contract_version"),
                           "elements": elements} if bp else None),
            "requirements": reqs, "business_rules": rules, "acceptance_criteria": criteria, "decisions": decisions,
            "design": design, "ui": _ui_for(task, warnings), "architecture": architecture},
        "referenced": {"limit": limit, "files": shown, "matched_total": len(files), "truncated": max(0, len(files) - len(shown)),
                       "patterns_without_match": unmatched, "docs": docs},
        "on_demand": {"knowledge": know, "knowledge_truncated": know_cut,
                      "context_refs": task.get("context", {}).get("on_demand", []),
                      "graph": {"configured": [{"server": s["server"], "profile": s["profile"], "label": s["label"]} for s in servers],
                                "queries": queries, "notes": gnotes, "related": related}},
        "context_mode": context_mode,
        "warnings": warnings}


def _architecture_for(project, paths):
    """Estilo de arquitetura (adotado, ou detectado e ainda nao adotado) e as boas praticas que valem para os arquivos da
    tarefa (instaladas em .claude/rules/aisef/ quando existem; senao, o caminho no plugin). So caminhos, sem o texto."""
    apath = os.path.join(project, ".aisef", "architecture.json")
    arch = _load_json(apath) if os.path.isfile(apath) else None
    try:
        import aisef_practices
        rels = aisef_practices.for_paths(project, [p.replace(os.sep, "/") for p in paths])
    except (OSError, ValueError, ImportError):
        rels = []
    if not isinstance(arch, dict) and not rels:
        return None
    practices = []
    for rel in rels:
        installed = os.path.join(project, ".claude", "rules", "aisef", rel)
        practices.append(_rel(project, installed) if os.path.isfile(installed) else "<CORE>/practices/" + rel)
    out = {"practices": practices}
    if isinstance(arch, dict):
        approved = (arch.get("approved") or {}).get("styles")
        out.update({"styles": approved or [s["id"] for s in arch.get("styles", []) if s.get("confidence", 0) >= 0.5],
                    "adopted": bool(approved), "path": _rel(project, apath),
                    "dependency_check": "python -I <CORE>/aisef_detect.py deps --project ."})
    return out


def _ui_for(task, warnings):
    """V-06: como a UI se comporta (declarado no contrato) e como provar; tarefa de UI sem declaracao ganha aviso."""
    import aisef_ui
    if not aisef_ui.is_ui(task):
        return None
    tid = task.get("task_id")
    if not task.get("ui_behavior"):
        warnings.append("tarefa de UI sem ui_behavior: antes de codar, devolva ao orquestrador as rotas, o que muda em cada "
                        "largura, o que fazer quando o conteudo nao cabe, os gestos e os estados")
    return {"behavior": task.get("ui_behavior"),
            "probe": "python -I <CORE>/ui_probe.py run --project . --task %s --base <url da UI rodando>" % tid,
            "evidence": ".aisef/reports/ui/%s/probe/report.json (evidencia do tipo ui_probe no Execution Report)" % tid}


def _design_for(project, task):
    """Autoridade de design (.aisef/design/tokens.json) para tarefas que tocam UI: o agente trabalha dentro dela."""
    if "ui" not in (task.get("touches") or []) and task.get("assigned_agent", {}).get("role") != "frontend":
        return None
    path = os.path.join(project, ".aisef", "design", "tokens.json")
    tok = _load_json(path) if os.path.isfile(path) else None
    if not isinstance(tok, dict):
        return None
    md = os.path.join(project, ".aisef", "design", "DESIGN.md")
    typo = tok.get("typography", {})
    return {"path": _rel(project, path), "doc": _rel(project, md) if os.path.isfile(md) else None,
            "status": tok.get("status"), "kind": tok.get("kind"), "families": typo.get("families", {}),
            "scale": sorted(typo.get("scale", {})), "colors": sorted(tok.get("colors", {})),
            "spacing": sorted(tok.get("spacing", {})), "motion": tok.get("motion", {}),
            "components": tok.get("components", []), "rules": tok.get("rules", []),
            "check": "python -I <CORE>/design_check.py scan --project . --task %s" % task.get("task_id")}


# ---------------------------------------------------------------------------- CLI
def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pack", help="gera o pacote de contexto de uma tarefa")
    p.add_argument("--project", default=".")
    p.add_argument("--task", required=True)
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="maximo de arquivos listados em 'referenciado'")
    p.add_argument("--json", action="store_true")
    p.add_argument("--no-graph", action="store_true", help="sem grafo (Graphify e graph MCP), para comparar o efeito")
    r = sub.add_parser("remember", help="grava uma entrada de conhecimento do projeto")
    r.add_argument("--project", default=".")
    r.add_argument("--summary", required=True)
    r.add_argument("--detail")
    r.add_argument("--source-kind", required=True, choices=["file", "url", "task", "decision"])
    r.add_argument("--source-ref", required=True)
    r.add_argument("--tags", default="")
    r.add_argument("--task")
    r.add_argument("--feature")
    r.add_argument("--created-by", default="orchestrator")
    r.add_argument("--supersedes")
    g = sub.add_parser("graph", help="mostra o graph MCP configurado no .mcp.json")
    g.add_argument("--project", default=".")
    a = ap.parse_args(argv)
    if a.cmd == "pack":
        pack = build_pack(a.project, a.task, a.limit, graph=not a.no_graph)
        print(json.dumps(pack, ensure_ascii=False, indent=2) if a.json else render_pack(pack))
    elif a.cmd == "remember":
        path = remember(a.project, a.summary, a.source_kind, a.source_ref, a.detail, a.tags.split(","), a.task, a.feature,
                        a.created_by, a.supersedes)
        print("registrado " + path)
    else:
        print(json.dumps(detect_graph_servers(os.path.abspath(a.project)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
