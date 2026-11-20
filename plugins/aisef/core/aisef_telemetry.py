#!/usr/bin/env python3
"""AISEF telemetria (0.14, F-05): segunda camada do log, para o volume que nao precisa de assinatura.

O log assinado (.aisef/audit/) fica com o que prova o trabalho: ciclo de vida, decisoes, tudo o que o gateway negou
ou perguntou, e os comandos de shell (Bash/PowerShell, de onde sai o consumo da aprovacao reforcada). Com
config.json -> audit.telemetry = "split" (padrao dos projetos novos), as edicoes de arquivo (Edit, Write, MultiEdit,
NotebookEdit) e as chamadas MCP liberadas vao para .aisef/telemetry/telemetry.jsonl: cadeia de hash propria
(adulteracao e detectavel), sem assinatura, fora do Git e com rotacao. "signed" mantem tudo no log assinado
(projetos antigos, ate o migrate).

    python -I aisef_telemetry.py verify --project .
Somente stdlib.
"""
import datetime
import hashlib
import json
import os
import sys

MODES = ("split", "signed")
ROTATE_BYTES = 5 * 1024 * 1024
FILE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")


def mode(cfg):
    m = ((cfg or {}).get("audit") or {}).get("telemetry")
    return m if m in MODES else "signed"  # sem a chave: comportamento anterior a 0.14


def routes_to_telemetry(cfg, tool):
    """O PostToolUse desta ferramenta vai para a telemetria?"""
    return mode(cfg) == "split" and (tool in FILE_TOOLS or tool.startswith("mcp__"))


def _dir(project):
    d = os.path.join(project, ".aisef", "telemetry")
    os.makedirs(d, exist_ok=True)
    ign = os.path.join(d, ".gitignore")
    if not os.path.exists(ign):
        with open(ign, "w", encoding="utf-8") as fh:
            fh.write("*\n")
    return d


def _hash(rec):
    body = {k: v for k, v in rec.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def _last(path):
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - 8192))
            tail = fh.read().decode("utf-8", errors="replace").strip().splitlines()
        return json.loads(tail[-1]) if tail else None
    except (OSError, ValueError, IndexError):
        return None


def append(project, record):
    """Grava um registro encadeado (seq, prev_hash, hash). Rotaciona quando passa de ROTATE_BYTES: o arquivo vira
    telemetry-<seq>.jsonl e o novo comeca apontando para o ultimo hash do anterior."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from aisef_base import Lock  # a mesma trava do log assinado: hooks em paralelo nao quebram a cadeia
    d = _dir(project)
    path = os.path.join(d, "telemetry.jsonl")
    with Lock(path + ".lock"):
        last = _last(path)
        if last and os.path.getsize(path) > ROTATE_BYTES:
            os.replace(path, os.path.join(d, "telemetry-%08d.jsonl" % last["seq"]))
        rec = {"seq": (last["seq"] + 1) if last else 1, "prev_hash": last["hash"] if last else None,
               "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), **record}
        rec["hash"] = _hash(rec)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def read(project):
    d = os.path.join(project, ".aisef", "telemetry")
    files = sorted(f for f in os.listdir(d) if f.startswith("telemetry-")) + ["telemetry.jsonl"] if os.path.isdir(d) else []
    out = []
    for f in files:
        try:
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                for line in fh:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        out.append({"_broken": line[:80]})
        except OSError:
            continue
    return out


def verify(project):
    """Problemas da cadeia (lista vazia = integra)."""
    out, prev, seq = [], None, 0
    for r in read(project):
        if "_broken" in r:
            out.append("linha ilegivel: %s" % r["_broken"])
            continue
        seq += 1
        if r.get("seq") != seq:
            out.append("sequencia %s, esperada %d (registro removido ou inserido)" % (r.get("seq"), seq))
            seq = r.get("seq") or seq
        if r.get("prev_hash") != prev:
            out.append("seq %s: prev_hash nao confere com o registro anterior" % r.get("seq"))
        if _hash(r) != r.get("hash"):
            out.append("seq %s: conteudo alterado (hash nao confere)" % r.get("seq"))
        prev = r.get("hash")
    return out


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["verify"])
    p.add_argument("--project", default=".")
    a = p.parse_args(argv)
    problems = verify(os.path.abspath(a.project))
    for x in problems:
        print("ERRO " + x)
    print("telemetria: %d registro(s), %d problema(s)" % (len(read(os.path.abspath(a.project))), len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
