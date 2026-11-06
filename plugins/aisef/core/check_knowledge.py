#!/usr/bin/env python3
"""Valida a memoria do projeto (.aisef/knowledge/K-NNN.json).

    python -I check_knowledge.py --project <repo> [--strict]        (--strict: aviso tambem falha)

validate(aisef_dir) -> lista de (codigo, onde, mensagem). Os codigos em WARNINGS sao avisos; os demais, erros.
O check_project liga isto as suas regras. Somente stdlib + jsonschema (como o resto do AISEF).
"""
import argparse
import datetime
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import userlibs  # noqa: E402,F401  (jsonschema pode estar na pasta de usuario do pip)
import aisef_context as ctx  # noqa: E402

SCHEMA = os.path.join(HERE, "knowledge-entry.schema.v0.1.json")
WARNINGS = frozenset({"KNW-SOURCE-FILE-MISSING", "KNW-SOURCE-DECISION-UNKNOWN", "KNW-SOURCE-TASK-MISSING"})


def _json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _known_decisions(aisef_dir):
    ids = set()
    for p in glob.glob(os.path.join(aisef_dir, "approvals", "*.json")):
        try:
            ref = _json(p).get("resulting_ref") or {}
            if ref.get("kind") == "architectural_decision":
                ids.add(ref.get("id"))
        except Exception:
            pass
    for pat in ("blueprints", os.path.join("contracts", "features")):
        for p in glob.glob(os.path.join(aisef_dir, pat, "*.json")):
            try:
                d = _json(p)
                for x in d.get("architecture", {}).get("decisions", []) + d.get("architectural_decisions", []):
                    ids.add(x.get("id"))
            except Exception:
                pass
    return ids


def validate(aisef_dir):
    """Erros e avisos da memoria do projeto. Pasta .aisef/knowledge ausente: nada a validar."""
    import jsonschema
    kdir = os.path.join(aisef_dir, "knowledge")
    out = []
    if not os.path.isdir(kdir):
        return out
    project = os.path.dirname(os.path.abspath(aisef_dir))
    validator = jsonschema.Draft202012Validator(_json(SCHEMA))
    tasks = {os.path.basename(p)[:-5] for p in glob.glob(os.path.join(aisef_dir, "contracts", "tasks", "*.json"))}
    features = {os.path.basename(p)[:-5] for p in glob.glob(os.path.join(aisef_dir, "contracts", "features", "*.json"))}
    decisions = None
    seen, entries = {}, {}
    for name in sorted(os.listdir(kdir)):
        where = "knowledge/" + name
        if name.endswith((".tmp", ".lock")):
            continue
        if not re.fullmatch(r"K-\d{3,}\.json", name):
            out.append(("KNW-FILENAME", where, "nome fora do padrao K-NNN.json"))
            continue
        try:
            e = _json(os.path.join(kdir, name))
        except Exception as exc:
            out.append(("KNW-JSON", where, "JSON invalido: %s" % exc))
            continue
        errs = sorted(validator.iter_errors(e), key=lambda x: list(x.path))
        for er in errs:
            out.append(("KNW-SCHEMA", where, "%s: %s" % ("/".join(map(str, er.path)) or "(raiz)", er.message)))
        if errs or not isinstance(e, dict):
            continue
        try:
            datetime.datetime.fromisoformat(e["created_at"])
        except ValueError:
            out.append(("KNW-SCHEMA", where, "created_at: nao e data-hora ISO 8601"))
        if e["id"] + ".json" != name:
            out.append(("KNW-ID-NAME", where, "id %s diverge do nome do arquivo" % e["id"]))
        if e["id"] in seen:
            out.append(("KNW-ID-DUP", where, "id %s duplicado (tambem em %s)" % (e["id"], seen[e["id"]])))
        seen[e["id"]] = where
        entries[e["id"]] = (where, e)
        for label, text in (("summary", e["summary"]), ("detail", e["detail"]), ("source.ref", e["source"]["ref"])):
            hits = ctx.find_secrets(text, e["source"]["kind"] if label == "source.ref" else None)
            if hits:
                out.append(("KNW-SECRET", where, "%s parece conter segredo (%s): apague o valor da entrada" % (label, ", ".join(sorted(set(hits))))))
        if e.get("task_id") and e["task_id"] not in tasks:
            out.append(("KNW-TASK-MISSING", where, "task_id %s nao existe em contracts/tasks" % e["task_id"]))
        if e.get("feature_id") and e["feature_id"] not in features:
            out.append(("KNW-FEATURE-MISSING", where, "feature_id %s nao existe em contracts/features" % e["feature_id"]))
        kind, ref = e["source"]["kind"], e["source"]["ref"]
        if kind == "file" and not os.path.exists(os.path.join(project, ref)):
            out.append(("KNW-SOURCE-FILE-MISSING", where, "arquivo-fonte %s nao existe (movido ou apagado?)" % ref))
        elif kind == "task" and ref not in tasks:
            out.append(("KNW-SOURCE-TASK-MISSING", where, "tarefa-fonte %s nao existe" % ref))
        elif kind == "decision":
            decisions = _known_decisions(aisef_dir) if decisions is None else decisions
            if ref not in decisions:
                out.append(("KNW-SOURCE-DECISION-UNKNOWN", where, "decisao-fonte %s nao aparece em aprovacoes, blueprints nem features" % ref))
    for kid, (where, e) in sorted(entries.items()):
        for field in ("supersedes", "superseded_by"):
            if e.get(field) and e[field] not in entries:
                out.append(("KNW-LINK", where, "%s aponta para %s, que nao existe" % (field, e[field])))
        if e["status"] == "superseded" and e.get("superseded_by") in entries and entries[e["superseded_by"]][1].get("supersedes") not in (None, kid):
            out.append(("KNW-LINK", where, "%s diz ser substituida por %s, que substitui outra entrada" % (kid, e["superseded_by"])))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="valida .aisef/knowledge")
    ap.add_argument("--project", default=".")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args(argv)
    found = validate(os.path.join(os.path.abspath(a.project), ".aisef"))
    errs = [f for f in found if f[0] not in WARNINGS]
    for code, where, msg in found:
        print("%-7s %-30s %s: %s" % ("AVISO" if code in WARNINGS else "ERRO", code, where, msg))
    print("%d erro(s), %d aviso(s)" % (len(errs), len(found) - len(errs)))
    return 1 if errs or (a.strict and found) else 0


if __name__ == "__main__":
    sys.exit(main())
