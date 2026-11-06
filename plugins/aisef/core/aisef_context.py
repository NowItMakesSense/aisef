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
  on_demand   entradas de conhecimento relevantes e, se houver graph MCP no .mcp.json, consultas sugeridas ao grafo.
Somente leitura: o pack nao altera nada. `remember` e o unico comando que grava (em .aisef/knowledge/).
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
PLUGIN = os.path.dirname(HERE)
PATTERNS_PATH = os.path.join(PLUGIN, "hooks", "sensitive_patterns.json")
KNOWLEDGE_SCHEMA = os.path.join(HERE, "knowledge-entry.schema.v0.1.json")
DEFAULT_LIMIT = 20
KNOWLEDGE_LIMIT = 10
WALK_CAP = 50000  # teto de arquivos visitados: o pack precisa ser rapido mesmo em monorepo
SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", ".aisef", "__pycache__", ".venv", "venv", "dist", "build",
             ".next", ".tox", ".mypy_cache", ".pytest_cache", "target", ".idea", ".vscode", "graphify-out", ".gradle"}

# ---------------------------------------------------------------------------- graph MCP (camada de codigo e de docs)
# Nomes das ferramentas conferidos nas fontes oficiais (README e codigo-fonte dos projetos, 2026-11-06).
# Somente as de LEITURA entram aqui; index_repository, delete_project, manage_adr e ingest_traces (codebase-memory)
# e list_prs/get_pr_impact/triage_prs (graphify, falam com o GitHub) ficam de fora de proposito.
GRAPH_PROFILES = [
    {"id": "codebase-memory", "label": "codebase-memory-mcp (grafo de codigo)", "match": ["codebase-memory"],
     "read_tools": ["search_graph", "trace_path", "detect_changes", "query_graph", "get_graph_schema", "get_code_snippet",
                    "get_file_outline", "get_architecture", "search_code", "list_projects", "index_status",
                    "check_index_coverage", "compare_graphs"]},
    {"id": "graphify", "label": "Graphify (grafo de docs e decisoes)", "match": ["graphify"],
     "read_tools": ["query_graph", "get_node", "get_neighbors", "get_community", "god_nodes", "graph_stats", "shortest_path"]},
]


def _safe_key(key):
    """Claude Code monta o nome da ferramenta como mcp__<servidor>__<ferramenta>."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", key)


def detect_graph_servers(project):
    """Le .mcp.json e devolve [{profile, label, server, tools:{nome: nome_mcp_completo}}] para cada graph MCP.
    Nunca levanta excecao: .mcp.json ausente ou quebrado significa 'nenhum'."""
    try:
        with open(os.path.join(project, ".mcp.json"), encoding="utf-8") as fh:
            servers = json.load(fh).get("mcpServers", {})
        if not isinstance(servers, dict):
            return []
    except Exception:
        return []
    found = []
    for key, spec in servers.items():
        try:
            blob = (key + " " + str(spec.get("command", "")) + " " + " ".join(map(str, spec.get("args", [])))).lower()
        except Exception:
            blob = str(key).lower()
        for prof in GRAPH_PROFILES:
            if any(m in blob for m in prof["match"]):
                found.append({"profile": prof["id"], "label": prof["label"], "server": key,
                              "tools": {t: "mcp__%s__%s" % (_safe_key(key), t) for t in prof["read_tools"]}})
                break
    return found


def graph_queries(project, servers, files, task):
    """Consultas sugeridas ao grafo para a tarefa, com os nomes reais das ferramentas. So sugere; nao executa."""
    qs, notes = [], []
    tokens = " ".join([task.get("title", "")] + task["scope"].get("included", [])[:3])
    for s in servers:
        t = s["tools"]
        if s["profile"] == "codebase-memory":
            qs.append({"tool": t["index_status"], "why": "conferir se o projeto esta indexado e fresco antes de consultar", "hint": "sem argumentos de consulta; se nao estiver indexado, pedir ao usuario para liberar index_repository"})
            sample = ", ".join(files[:5]) if files else "(a tarefa ainda nao tem arquivos existentes)"
            qs.append({"tool": t["get_file_outline"], "why": "estrutura de cada arquivo da tarefa sem le-lo inteiro", "hint": "arquivos: " + sample})
            qs.append({"tool": t["search_graph"], "why": "achar os simbolos da tarefa pelo nome (name_pattern)", "hint": "termos: " + tokens})
            qs.append({"tool": t["trace_path"], "why": "impacto: quem chama e quem e chamado pelos simbolos da tarefa (mode=calls)", "hint": "partir dos simbolos achados em search_graph"})
            qs.append({"tool": t["detect_changes"], "why": "raio de impacto do diff atual", "hint": "use depois de editar, antes de entregar"})
        elif s["profile"] == "graphify":
            qs.append({"tool": t["query_graph"], "why": "perguntar ao grafo de docs e decisoes (ADRs, specs, .aisef)", "hint": "pergunta: " + (task.get("title") or "")})
            qs.append({"tool": t["get_neighbors"], "why": "vizinhos de um conceito (requisito, decisao, modulo)", "hint": "label do no, ex.: o id do requisito"})
            qs.append({"tool": t["shortest_path"], "why": "como dois conceitos se ligam (ex.: requisito -> modulo)", "hint": "source e target"})
            if not os.path.exists(os.path.join(project, "graphify-out", "graph.json")):
                notes.append("graphify-out/graph.json nao existe: o grafo ainda nao foi gerado (peca ao usuario para rodar /graphify .)")
    return qs, notes


# ---------------------------------------------------------------------------- utilitarios
def _load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


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
    for e in entries:
        if e.get("status", "active") != "active":
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
            scored.append((-score, e["id"], {"id": e["id"], "summary": e.get("summary", ""), "source": src,
                                             "tags": e.get("tags", []), "score": score, "why": why}))
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


def build_pack(project, task_id, limit=DEFAULT_LIMIT):
    """Pacote de contexto da tarefa. Levanta SystemExit se a tarefa nao existe."""
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
    servers = detect_graph_servers(project)
    queries, gnotes = graph_queries(project, servers, shown, task)

    return {
        "task_id": task_id, "feature_id": fid, "title": task.get("title"), "objective": task.get("objective"),
        "mandatory": {
            "task_contract": _rel(project, tpath),
            "feature_contract": _rel(project, fpath) if feature else None,
            "blueprint": ({"path": _rel(project, bp_path), "id": bp.get("blueprint_id"), "version": bp.get("contract_version"),
                           "elements": elements} if bp else None),
            "requirements": reqs, "business_rules": rules, "acceptance_criteria": criteria, "decisions": decisions},
        "referenced": {"limit": limit, "files": shown, "matched_total": len(files), "truncated": max(0, len(files) - len(shown)),
                       "patterns_without_match": unmatched, "docs": docs},
        "on_demand": {"knowledge": know, "knowledge_truncated": know_cut,
                      "context_refs": task.get("context", {}).get("on_demand", []),
                      "graph": {"configured": [{"server": s["server"], "profile": s["profile"], "label": s["label"]} for s in servers],
                                "queries": queries, "notes": gnotes}},
        "warnings": warnings}


def render_pack(p):
    m, r, o = p["mandatory"], p["referenced"], p["on_demand"]
    L = ["# Pacote de contexto %s (feature %s)" % (p["task_id"], p["feature_id"]), "", "%s" % p["title"], "",
         "## 1. Obrigatorio", "- Task Contract: %s" % m["task_contract"]]
    if m["feature_contract"]:
        L.append("- Feature Contract: %s" % m["feature_contract"])
    if m["blueprint"]:
        L.append("- Blueprint: %s (v%s)" % (m["blueprint"]["path"], m["blueprint"]["version"]))
        for e in m["blueprint"]["elements"]:
            L.append("    - %s %s %s (%s)" % (e["kind"], e["id"], e["name"], ", ".join(e["requirement_ids"])))
    L.append("- Requisitos:")
    L += ["    - %s v%s: %s" % (x["id"], x["version"], x["statement"]) for x in m["requirements"]] or ["    (nenhum)"]
    if m["business_rules"]:
        L.append("- Regras de negocio:")
        L += ["    - %s: %s" % (x["id"], x["statement"]) for x in m["business_rules"]]
    L.append("- Criterios de aceite:")
    for c in m["acceptance_criteria"]:
        L.append("    - %s%s: %s [%s; evidencia: %s]" % (c["id"], "" if c["required"] else " (opcional)", c["description"], c["method"], c["evidence_expected"]))
    L.append("- Decisoes aprovadas:")
    L += ["    - %s v%s%s: %s (%s; %s)" % (d["id"], d["version"], " -> " + d["chosen"] if d.get("chosen") else "", d["title"], d["approval"], "; ".join(d["why"]))
          for d in m["decisions"]] or ["    (nenhuma)"]
    L += ["", "## 2. Referenciado (limite %d)" % r["limit"]]
    L += ["- " + f for f in r["files"]] or ["- (nenhum arquivo existente casa com os caminhos da tarefa)"]
    if r["truncated"]:
        L.append("- ... mais %d arquivo(s) cortado(s) pelo limite (%d no total)" % (r["truncated"], r["matched_total"]))
    if r["patterns_without_match"]:
        L.append("- caminhos sem arquivo existente (a criar?): " + ", ".join(r["patterns_without_match"]))
    L += ["- doc: %s (%s)" % (d["path"], d["origin"]) for d in r["docs"]]
    L += ["", "## 3. Sob demanda"]
    for k in o["knowledge"]:
        L.append("- %s: %s [%s %s] (%s)" % (k["id"], k["summary"], k["source"].get("kind"), k["source"].get("ref"), "; ".join(k["why"])))
    if o["knowledge_truncated"]:
        L.append("- ... mais %d entrada(s) de conhecimento cortada(s)" % o["knowledge_truncated"])
    if not o["knowledge"]:
        L.append("- conhecimento: nenhuma entrada relevante")
    for c in o["context_refs"]:
        L.append("- contexto do contrato: %s (%s)" % (c.get("ref"), c.get("origin")))
    g = o["graph"]
    if g["configured"]:
        L.append("- grafo configurado: " + ", ".join("%s (%s)" % (s["label"], s["server"]) for s in g["configured"]))
        for q in g["queries"]:
            L.append("    - %s: %s (%s)" % (q["tool"], q["why"], q["hint"]))
        L += ["    - nota: " + n for n in g["notes"]]
    else:
        L.append("- grafo: nenhum graph MCP no .mcp.json (veja a secao Grafo de codigo da skill aisef-tooling)")
    if p["warnings"]:
        L += ["", "## Avisos"] + ["- " + w for w in p["warnings"]]
    return "\n".join(L)


# ---------------------------------------------------------------------------- segredos
# Valores com formato de segredo. Cobrem o que nao e comando nem caminho (o que o sensitive_patterns.json nao pega).
SECRET_VALUE_RES = [
    ("chave privada", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("chave de acesso AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("token do GitHub", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("token do GitHub (fine-grained)", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}")),
    ("chave de API (sk-)", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("token do Slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}")),
    ("credencial em URL", re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]{3,}@")),
    ("atribuicao de segredo", re.compile(
        r"(?i)\b(?:password|passwd|senha|secret|client_secret|api[_-]?key|access[_-]?key|auth[_-]?token|token)\b\s*[:=]\s*[\"']?[^\s\"']{6,}")),
]


def _sensitive_patterns():
    try:
        return _load_json(PATTERNS_PATH)
    except Exception:
        return {}


def find_secrets(text, kind=None):
    """Descricoes (sem o valor) do que em `text` parece segredo. kind='file' tambem confere o caminho sensivel
    (.env, chaves, credenciais) e URLs de conexao com banco do sensitive_patterns.json do gateway."""
    hits = [label for label, rx in SECRET_VALUE_RES if rx.search(text)]
    pats = _sensitive_patterns()
    try:
        for c in pats.get("commands", []):
            if c.get("id") == "db-url" and re.search(c["regex"], text, re.I):
                hits.append(c.get("label", "URL de conexao com banco"))
        p = pats.get("paths")
        if kind == "file" and p and re.search(p["regex"], text, re.I) and not re.search(p.get("allow", "(?!)"), text, re.I):
            hits.append(p.get("label", "arquivo sensivel"))
    except re.error:
        pass
    return hits


# ---------------------------------------------------------------------------- remember
def _now():
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


def next_knowledge_id(aisef_dir):
    nums = [int(m.group(1)) for n in (os.listdir(os.path.join(aisef_dir, "knowledge")) if os.path.isdir(os.path.join(aisef_dir, "knowledge")) else [])
            for m in [re.fullmatch(r"K-(\d+)\.json", n)] if m]
    return "K-%03d" % (max(nums, default=0) + 1)


def remember(project, summary, source_kind, source_ref, detail=None, tags=(), task_id=None, feature_id=None,
             created_by="orchestrator", supersedes=None):
    """Grava .aisef/knowledge/K-NNN.json. Recusa segredo e entrada que nao passa no schema. Devolve o caminho."""
    adir = os.path.join(os.path.abspath(project), ".aisef")
    if not os.path.isfile(os.path.join(adir, "config.json")):
        raise SystemExit("%s nao e um projeto AISEF (falta .aisef/config.json)" % project)
    entry = {"schema_version": "0.1.0", "id": next_knowledge_id(adir), "summary": summary.strip(),
             "detail": (detail or summary).strip(), "source": {"kind": source_kind, "ref": source_ref.strip()}}
    if feature_id:
        entry["feature_id"] = feature_id
    if task_id:
        entry["task_id"] = task_id
    entry.update(tags=sorted({t.strip() for t in tags if t.strip()}), created_by=created_by, created_at=_now(), status="active")
    for field, text in (("summary", entry["summary"]), ("detail", entry["detail"]), ("source.ref", entry["source"]["ref"]),
                        ("tags", " ".join(entry["tags"]))):
        hits = find_secrets(text, source_kind if field == "source.ref" else None)
        if hits:
            raise SystemExit("recusado: %s parece conter segredo (%s). Registre onde o valor mora (ex.: o nome da variavel "
                             "e o cofre), nunca o valor." % (field, ", ".join(sorted(set(hits)))))
    old_path = None
    if supersedes:
        old_path = os.path.join(adir, "knowledge", supersedes + ".json")
        if not os.path.isfile(old_path):
            raise SystemExit("--supersedes %s: entrada inexistente" % supersedes)
        entry["supersedes"] = supersedes
    try:
        import userlibs  # noqa: F401  (jsonschema pode estar na pasta de usuario do pip)
        import jsonschema
    except ImportError:
        raise SystemExit("falta a biblioteca jsonschema neste Python (o check_project tambem precisa dela)")
    errors = sorted(jsonschema.Draft202012Validator(_load_json(KNOWLEDGE_SCHEMA)).iter_errors(entry), key=lambda e: list(e.path))
    if errors:
        raise SystemExit("recusado pelo schema: " + "; ".join("%s: %s" % ("/".join(map(str, e.path)) or "(raiz)", e.message) for e in errors))
    kdir = os.path.join(adir, "knowledge")
    os.makedirs(kdir, exist_ok=True)
    path = os.path.join(kdir, entry["id"] + ".json")
    if old_path:
        old = _load_json(old_path)
        old.update(status="superseded", superseded_by=entry["id"])
        _write_json(old_path, old)
    _write_json(path, entry)
    return path


def _write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


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
        pack = build_pack(a.project, a.task, a.limit)
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
