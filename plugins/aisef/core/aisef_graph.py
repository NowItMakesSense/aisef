#!/usr/bin/env python3
"""AISEF graph (0.11.0): le o grafo do Graphify (graphify-out/graph.json) direto, so com stdlib.

O pacote do Graphify fica no Python do usuario e o AISEF roda com `python -I`, que nao o enxerga. Por isso o
`pack` le o graph.json (formato node-link do networkx: nodes[id, label, source_file, source_location, file_type],
links[source, target, relation]) em vez de chamar a CLI ou o servidor MCP.

`related()` devolve o que a tarefa precisa saber e nao esta nos arquivos dela:
- decisoes e documentos que referenciam ou justificam os arquivos e ids da tarefa (references, rationale_for);
- codigo de fora da tarefa que chama ou importa o codigo da tarefa (raio de impacto: onde pode quebrar);
- o que o codigo da tarefa chama ou importa de fora (dependencias).
Com teto de itens e de caracteres: o grafo nunca estoura o pacote.

Grafo nativo (0.13, G-06): sem o Graphify, `build_native` monta um grafo de imports do proprio repositorio (um no por
arquivo de codigo, arestas `imports`), no mesmo formato node-link, em .aisef/runtime/graph.json (fora do Git).
`ensure_native` o reconstroi so quando um arquivo de codigo mudou, entrou ou saiu. O `related()` funciona igual sobre ele.

    python -I aisef_graph.py build-native --project <repo>   (forca a reconstrucao e mostra o tamanho)
"""
import argparse
import datetime
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_imports  # noqa: E402

MAX_GRAPH_BYTES = 40 * 1024 * 1024
MAX_ITEMS = 15
MAX_CHARS = 2500
DOC_RELATIONS = ("rationale_for", "references")
IMPACT_RELATIONS = ("calls", "imports", "imports_from", "inherits", "indirect_call", "method")
NATIVE_GRAPH = os.path.join(".aisef", "runtime", "graph.json")
MAX_NATIVE_FILES = 20000
MAX_NATIVE_BYTES = 300_000
ID_RE = re.compile(r"\b(?:REQ|BR|D|ADR|DEC|FEAT|T)-[A-Za-z0-9._-]+\b")


def load(path):
    """(nodes por id, arestas) ou None se o arquivo nao existe, e grande demais ou nao e um grafo."""
    try:
        if os.path.getsize(path) > MAX_GRAPH_BYTES:
            return None
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("nodes"), list):
        return None
    nodes = {n["id"]: n for n in data["nodes"] if isinstance(n, dict) and "id" in n}
    links = [l for l in (data.get("links") or data.get("edges") or [])
             if isinstance(l, dict) and l.get("source") in nodes and l.get("target") in nodes]
    return nodes, links


def _file(n):
    return (n.get("source_file") or "").replace("\\", "/")


def _text(n):
    fm = n.get("frontmatter") if isinstance(n.get("frontmatter"), dict) else {}
    return " ".join(str(x) for x in (n.get("label"), n.get("norm_label"), fm.get("name"), fm.get("title")) if x)


def related(graph, task_files, ids, max_items=MAX_ITEMS, max_chars=MAX_CHARS):
    """Itens do grafo ligados a tarefa e fora dela. `task_files`: caminhos relativos dos arquivos da tarefa;
    `ids`: requisitos, regras, decisoes, tarefa e feature (casam no label dos nos)."""
    nodes, links = graph
    files = {f.replace("\\", "/") for f in task_files}
    ids = {i for i in ids if i}
    seeds, mentions = set(), {}  # seeds: nos nos arquivos da tarefa; mentions: nos de fora que citam um id dela
    for nid, n in nodes.items():
        if _file(n) in files:
            seeds.add(nid)
        elif ids:
            hit = ids & set(ID_RE.findall(_text(n)))
            if hit:
                mentions[nid] = sorted(hit)[0]
    if not seeds and not mentions:
        return {"seeds": 0, "items": [], "truncated": 0}

    def outside(nid):
        return nid not in seeds and _file(nodes[nid]) not in files

    found = {}  # (arquivo, label) -> item; um por no de fora, com a relacao mais informativa

    def add(nid, kind, relation, via, rank):
        n = nodes[nid]
        key = (_file(n), n.get("label"))
        if key in found and found[key]["_rank"] <= rank:
            return
        found[key] = {"kind": kind, "relation": relation, "label": n.get("label"), "file": _file(n) or None,
                      "location": n.get("source_location"), "via": via if via not in nodes else nodes[via].get("label"),
                      "_rank": rank}

    for nid, cited in mentions.items():
        add(nid, "decision" if nodes[nid].get("file_type") == "rationale" else "doc", "mentions", cited, 0)
    for l in links:
        s, t, rel = l["source"], l["target"], l.get("relation")
        if rel in DOC_RELATIONS:
            # documento/decisao (de fora) que fala de algo da tarefa, ou que algo da tarefa cita
            if t in seeds and outside(s):
                add(s, "decision" if rel == "rationale_for" else "doc", rel, t, 0 if rel == "rationale_for" else 1)
            elif s in seeds and outside(t):
                add(t, "doc", rel, s, 1)
        elif rel in IMPACT_RELATIONS:
            if t in seeds and outside(s):
                add(s, "impact", rel, t, 2)       # quem de fora depende do codigo da tarefa
            elif s in seeds and outside(t) and not nodes[t].get("external"):
                add(t, "dependency", rel, s, 3)   # do que o codigo da tarefa depende
    items = sorted(found.values(), key=lambda x: (x["_rank"], x["file"] or "", str(x["label"])))
    out, used = [], 0
    for it in items:
        it = {k: v for k, v in it.items() if k != "_rank"}
        size = len(json.dumps(it, ensure_ascii=False))
        if len(out) >= max_items or used + size > max_chars:
            break
        out.append(it)
        used += size
    return {"seeds": len(seeds), "mentions": len(mentions), "items": out, "truncated": len(items) - len(out)}


def graph_info(project, graph_rel):
    path = os.path.join(project, graph_rel)
    try:
        built = datetime.datetime.fromtimestamp(os.path.getmtime(path), datetime.timezone.utc)
    except OSError:
        return None
    return {"path": graph_rel.replace("\\", "/"), "built_at": built.isoformat(timespec="seconds")}


# ------------------------------------------------------------------ grafo nativo (G-06)
def _source_files(project):
    import aisef_detect
    files, _dirs, _trunc = aisef_detect.scan(project)
    src = [f for f in files if os.path.splitext(f)[1] in aisef_imports.IMPORT_RES]
    return src[:MAX_NATIVE_FILES]


def build_native(project, files=None):
    """Grafo de imports do repositorio no formato node-link. `files`: arquivos de codigo (padrao: varredura)."""
    files = _source_files(project) if files is None else files
    res = aisef_imports.Resolver(files)
    nodes = [{"id": f, "label": os.path.basename(f), "source_file": f, "file_type": "code"} for f in files]
    links, seen = [], set()
    for rel in files:
        try:
            with open(os.path.join(project, rel), encoding="utf-8", errors="replace") as fh:
                text = fh.read(MAX_NATIVE_BYTES)
        except OSError:
            continue
        for imp, line in aisef_imports.imports_in(text, os.path.splitext(rel)[1]):
            for target in res.resolve(rel, imp):
                if target != rel and (rel, target) not in seen:
                    seen.add((rel, target))
                    links.append({"source": rel, "target": target, "relation": "imports",
                                  "source_location": "L%d" % line})
    return {"directed": True, "nodes": nodes, "links": links,
            "aisef": {"kind": "native", "files": len(files),
                      "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}}


def _native_stale(project, path, files):
    try:
        built = os.path.getmtime(path)
        with open(path, encoding="utf-8") as fh:
            meta = (json.load(fh) or {}).get("aisef") or {}
    except (OSError, ValueError):
        return True
    if meta.get("files") != len(files):
        return True
    for f in files:
        try:
            if os.path.getmtime(os.path.join(project, f)) > built:
                return True
        except OSError:
            return True
    return False


def ensure_native(project, force=False):
    """Caminho relativo do grafo nativo, reconstruido se faltar ou estiver velho. None se nao ha codigo ou deu erro."""
    if not os.path.isfile(os.path.join(project, ".aisef", "config.json")):
        return None  # so grava em projeto AISEF
    path = os.path.join(project, NATIVE_GRAPH)
    try:
        files = _source_files(project)
        if not files:
            return None
        if force or _native_stale(project, path, files):
            graph = build_native(project, files)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(graph, fh, ensure_ascii=False)
            os.replace(tmp, path)
        return NATIVE_GRAPH.replace(os.sep, "/")
    except Exception:
        return None


def main(argv=None):
    p = argparse.ArgumentParser(description="Grafo nativo de imports do AISEF")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build-native", help="reconstroi .aisef/runtime/graph.json")
    b.add_argument("--project", default=".")
    a = p.parse_args(argv)
    project = os.path.abspath(a.project)
    t0 = time.time()
    rel = ensure_native(project, force=True)
    if not rel:
        print("nada gravado: projeto sem .aisef/config.json, sem arquivo de codigo ou erro ao gravar")
        return 1
    g = load(os.path.join(project, rel))
    print("%s: %d arquivo(s), %d import(s) resolvido(s), %.2f s" % (rel, len(g[0]), len(g[1]), time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
