#!/usr/bin/env python3
"""AISEF context: memoria de projeto (remember, segredos), render do pacote e consultas sugeridas ao graph MCP

H-01 (0.14): saiu de aisef_context.py sem mudar o codigo; aisef_context reexporta tudo."""
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


PLUGIN = os.path.dirname(HERE)
PATTERNS_PATH = os.path.join(PLUGIN, "hooks", "sensitive_patterns.json")
KNOWLEDGE_SCHEMA = os.path.join(HERE, "knowledge-entry.schema.v0.1.json")

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
    if m.get("design"):
        d = m["design"]
        L.append("- Autoridade de design (%s, %s): %s%s" % (d["status"], d["kind"], d["path"], "; " + d["doc"] if d["doc"] else ""))
        L.append("    - fontes: " + ", ".join("%s=%s" % kv for kv in sorted(d["families"].items())))
        L.append("    - escala: %s | cores: %s | espacos: %s" % (", ".join(d["scale"]), ", ".join(d["colors"]), ", ".join(d["spacing"])))
        L.append("    - movimento: %s%s" % (d["motion"].get("level"), " (sem scroll-linked)" if not d["motion"].get("scroll_linked") else ""))
        if d["components"]:
            L.append("    - componentes existentes (reuse antes de criar): " + ", ".join(d["components"]))
        L += ["    - regra: " + x for x in d["rules"]]
        L.append("    - use so estes valores; confira com: " + d["check"])
    if m.get("architecture"):
        a = m["architecture"]
        if a.get("styles") is not None:
            L.append("- Arquitetura (%s): %s; %s" % ("adotada" if a["adopted"] else "detectada, ainda nao adotada",
                                                 ", ".join(a["styles"]) or "nenhum estilo", a["path"]))
            L.append("    - regra de dependencia: dominio nao importa aplicacao, infraestrutura nem framework; confira com: "
                     + a["dependency_check"])
        if a["practices"]:
            L.append("- Boas praticas que valem para estes arquivos (leia antes de editar):")
            L += ["    - " + x for x in a["practices"]]
    L += ["", "## 2. Referenciado (limite %d)" % r["limit"]]
    L += ["- " + f for f in r["files"]] or ["- (nenhum arquivo existente casa com os caminhos da tarefa)"]
    if r["truncated"]:
        L.append("- ... mais %d arquivo(s) cortado(s) pelo limite (%d no total)" % (r["truncated"], r["matched_total"]))
    if r["patterns_without_match"]:
        L.append("- caminhos sem arquivo existente (a criar?): " + ", ".join(r["patterns_without_match"]))
    L += ["- doc: %s (%s)" % (d["path"], d["origin"]) for d in r["docs"]]
    L += ["", "## 3. Sob demanda"]
    for k in o["knowledge"]:
        if k.get("lesson"):
            L.append("- %s (licao aprovada, confianca %.2f; referencia, nao ordem): %s -> %s" % (k["id"], k["confidence"], k["summary"], k["action"]))
            continue
        L.append("- %s: %s [%s %s] (%s)" % (k["id"], k["summary"], k["source"].get("kind"), k["source"].get("ref"), "; ".join(k["why"])))
    if o["knowledge_truncated"]:
        L.append("- ... mais %d entrada(s) de conhecimento cortada(s)" % o["knowledge_truncated"])
    if not o["knowledge"]:
        L.append("- conhecimento: nenhuma entrada relevante")
    for c in o["context_refs"]:
        L.append("- contexto do contrato: %s (%s)" % (c.get("ref"), c.get("origin")))
    g = o["graph"]
    rel = g.get("related")
    if rel:
        L.append("- %s (%s, gerado em %s%s): %d no(s) da tarefa" % (
            "grafo nativo de imports" if rel.get("source") == "native" else "grafo do Graphify", rel.get("path"), (rel.get("built_at") or "?")[:16], ", VELHO" if rel.get("stale") else "", rel.get("seeds", 0)))
        names = {"decision": "decisao", "doc": "doc", "impact": "depende da tarefa", "dependency": "a tarefa depende"}
        for it in rel.get("items", []):
            L.append("    - [%s] %s (%s%s) via %s" % (names.get(it["kind"], it["kind"]), it["label"], it.get("file") or "?",
                                                    ":" + it["location"] if it.get("location") else "", it.get("via")))
        if rel.get("truncated"):
            L.append("    - ... mais %d ligacao(oes) cortada(s) pelo limite" % rel["truncated"])
        if not rel.get("items"):
            L.append("    - nada do grafo liga a tarefa a arquivos de fora dela")
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
