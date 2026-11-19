#!/usr/bin/env python3
"""AISEF: boas praticas do plugin (core/practices/) aplicadas ao projeto em .claude/rules/aisef/.

Quais entram vem de `.aisef/architecture.json` -> practices (aisef_detect): sempre `common`, mais as pastas das
linguagens detectadas e as dos estilos de arquitetura (o adotado pelo usuario, ou os detectados com confianca >= 0.5).
As regras de linguagem tem `paths:` no frontmatter: o Claude Code so as carrega ao mexer nesses arquivos.

Instalar e decisao do usuario (escreve em .claude/, o gateway pede aprovacao). Arquivo que o usuario mudou no projeto
nao e sobrescrito sem --force.

Uso:
    python3 -I aisef_practices.py list  --project REPO          (o que entraria e o estado de cada arquivo)
    python3 -I aisef_practices.py apply --project REPO [--force]
    python3 -I aisef_practices.py for-paths --project REPO src/a.py src/b.ts   (praticas que valem para esses arquivos)
"""
import argparse
import fnmatch
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "practices")
TARGET = os.path.join(".claude", "rules", "aisef")


def wanted(project):
    """Entradas de practices do architecture.json (ou so `common` sem deteccao), com o estilo adotado prevalecendo."""
    path = os.path.join(project, ".aisef", "architecture.json")
    if not os.path.exists(path):
        return ["common"]
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    items = list(doc.get("practices") or ["common"])
    approved = (doc.get("approved") or {}).get("styles")
    if approved:
        import aisef_detect
        items = [p for p in items if not p.startswith("architecture/")]
        items += [aisef_detect.STYLE_PRACTICE[s] for s in approved if s in aisef_detect.STYLE_PRACTICE]
    if "common" not in items:
        items.insert(0, "common")
    return list(dict.fromkeys(items))


def files_for(entries):
    """Arquivos (relativos a core/practices) de cada entrada: pasta inteira (`common`) ou um arquivo (`lang/python`)."""
    out = []
    for e in entries:
        d = os.path.join(SRC, e)
        if os.path.isdir(d):
            out += [e + "/" + f for f in sorted(os.listdir(d)) if f.endswith(".md")]
        elif os.path.exists(d + ".md"):
            out.append(e + ".md")
    return list(dict.fromkeys(out))


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def plan(project):
    rows = []
    for rel in files_for(wanted(project)):
        src, dst = os.path.join(SRC, rel), os.path.join(project, TARGET, rel)
        if not os.path.exists(dst):
            state = "novo"
        elif read(dst) == read(src):
            state = "igual"
        else:
            state = "modificado no projeto"
        rows.append({"practice": rel, "target": os.path.join(TARGET, rel).replace(os.sep, "/"), "state": state})
    return rows


def apply(project, force=False):
    done, kept = [], []
    for r in plan(project):
        if r["state"] == "igual":
            continue
        if r["state"] == "modificado no projeto" and not force:
            kept.append(r["target"])
            continue
        dst = os.path.join(project, r["target"])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(read(os.path.join(SRC, r["practice"])))
        done.append(r["target"])
    return done, kept


def paths_of(text):
    """Globs do frontmatter `paths:` (sem yaml: a lista e simples, uma linha por item)."""
    if not text.startswith("---"):
        return []
    head = text.split("---", 2)[1]
    out, inside = [], False
    for line in head.splitlines():
        if line.startswith("paths:"):
            inside = True
            continue
        if inside and line.strip().startswith("- "):
            out.append(line.strip()[2:].strip().strip("\"'"))
        elif inside and line and not line.startswith(" "):
            break
    return out


def for_paths(project, rels):
    """Praticas aplicaveis aos arquivos de uma tarefa: as sem `paths:` sempre, as com `paths:` se algum arquivo casa."""
    out = []
    for rel in files_for(wanted(project)):
        globs = paths_of(read(os.path.join(SRC, rel)))
        if not globs or any(fnmatch.fnmatch(p, g) or fnmatch.fnmatch(p, g.replace("**/", "")) for p in rels for g in globs):
            out.append(rel)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="AISEF: boas praticas no projeto")
    ap.add_argument("command", choices=["list", "apply", "for-paths"])
    ap.add_argument("--project", default=".")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("paths", nargs="*")
    a = ap.parse_args(argv)
    project = os.path.abspath(a.project)
    if a.command == "list":
        for r in plan(project):
            print("%-28s %-50s %s" % (r["state"], r["target"], r["practice"]))
        return 0
    if a.command == "for-paths":
        print("\n".join(for_paths(project, a.paths)))
        return 0
    done, kept = apply(project, a.force)
    print("gravados: %s" % (", ".join(done) or "nada mudou"))
    if kept:
        print("mantidos (modificados no projeto; --force sobrescreve): %s" % ", ".join(kept))
    return 0


if __name__ == "__main__":
    sys.exit(main())
