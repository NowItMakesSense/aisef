#!/usr/bin/env python3
"""Atestado in-toto por tarefa (0.17, E-05, ADR 0032): Statement v1 num envelope DSSE assinado com a chave do projeto.

    python -I aisef_evidence.py build --project . --feature FEAT-001 --out <pasta> --in-toto

Cada tarefa da feature vira `attestations/<TASK>.intoto.json`:
- subject: os arquivos que o relatorio diz ter criado ou alterado, com o sha256 de hoje, e o commit (`gitCommit`);
- predicate (`https://aisef.dev/attestation/task/v0.1`): o contrato (sha256), o agente, o modelo e o effort, as
  ferramentas usadas (eventos `tool_used` da tarefa), os testes e a validacao (quem validou e o hash do evento).

DSSE (https://github.com/secure-systems-lab/dsse): assinatura Ed25519 sobre
PAE = "DSSEv1" SP len(tipo) SP tipo SP len(corpo) SP corpo. O `keyid` e o id da chave publica em `keys/<keyid>.pem`
no pacote, que confere o envelope sem o projeto.
"""
import base64
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PAYLOAD_TYPE = "application/vnd.in-toto+json"
STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
PREDICATE_TYPE = "https://aisef.dev/attestation/task/v0.1"


def pae(payload_type, body):
    t = payload_type.encode("utf-8")
    return b"DSSEv1 %d %s %d %s" % (len(t), t, len(body), body)


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _file_sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit(project):
    try:
        r = subprocess.run(["git", "-C", project, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = r.stdout.strip()
    return out if r.returncode == 0 and len(out) in (40, 64) else None


def statement(project, task, reports, events, commit=None):
    tid = task["task_id"]
    mine = [r for r in reports if r.get("task_id") == tid]
    exe = next((r for r in reversed(mine) if (r.get("agent") or {}).get("role") != "validator"), mine[-1] if mine else {})
    subjects, missing = [], []
    for kind in ("created", "modified"):
        for f in ((exe.get("files") or {}).get(kind) or []):
            path = os.path.join(project, f["path"])
            if os.path.isfile(path):
                subjects.append({"name": f["path"].replace("\\", "/"), "digest": {"sha256": _file_sha(path)}})
            else:
                missing.append(f["path"])
    if commit:
        subjects.append({"name": "git:HEAD", "digest": {"gitCommit": commit}})
    tev = [e for e in events if e.get("task_id") == tid]
    val = next((e for e in reversed(tev) if e.get("event_type") == "task_validated"), None)
    tests = exe.get("tests") or {}
    predicate = {
        "task": {"task_id": tid, "title": task.get("title"), "contract_version": task.get("contract_version"),
                 "contract_sha256": hashlib.sha256(_canon(task)).hexdigest()},
        "feature_id": task.get("feature_id"),
        "agent": exe.get("agent"),
        "model": exe.get("execution_profile"),
        "tools": sorted({(e.get("data") or {}).get("tool") for e in tev if e.get("event_type") == "tool_used"} - {None}),
        "tests": {k: tests.get(k) for k in ("executed", "passed", "failed", "skipped", "commands") if k in tests},
        "tdd": bool(exe.get("tdd_evidence")),
        "validation": {"validated": bool(val), "validator": (val or {}).get("actor", {}).get("id"),
                       "event_hash": (val or {}).get("hash")},
        "log": {"events": len(tev), "last_event_hash": tev[-1]["hash"] if tev else None},
        "files_missing": missing,
    }
    return {"_type": STATEMENT_TYPE, "subject": subjects, "predicateType": PREDICATE_TYPE, "predicate": predicate}


def sign(stmt, private_key, key_id):
    body = _canon(stmt)
    sig = private_key.sign(pae(PAYLOAD_TYPE, body))
    return {"payloadType": PAYLOAD_TYPE, "payload": base64.b64encode(body).decode(),
            "signatures": [{"keyid": key_id, "sig": base64.b64encode(sig).decode()}]}


def signer_for(project):
    """(chave privada, key_id) do projeto, do arquivo ou do cofre (E-02)."""
    import aisef_project as ap
    cfg = ap.load_config(project)
    key_id = ap.audit_settings(cfg)["key_id"]
    s = ap.load_signer(cfg["project_id"], key_id)
    if s is None:
        raise SystemExit("--in-toto precisa da chave privada %s deste projeto nesta maquina" % key_id)
    return s._private, key_id


def build(project, out, tasks, reports, events):
    """Grava attestations/<TASK>.intoto.json; devolve os caminhos relativos."""
    priv, key_id = signer_for(project)
    commit = git_commit(project)
    os.makedirs(os.path.join(out, "attestations"), exist_ok=True)
    written = []
    for t in tasks:
        env = sign(statement(project, t, reports, events, commit), priv, key_id)
        rel = "attestations/%s.intoto.json" % t["task_id"]
        with open(os.path.join(out, rel), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(env, fh, indent=2)
            fh.write("\n")
        written.append(rel)
    return written


def verify_envelope(env, pubs):
    """(statement, problema). `pubs`: {key_id: chave publica}."""
    if env.get("payloadType") != PAYLOAD_TYPE:
        return None, "payloadType inesperado: %s" % env.get("payloadType")
    try:
        body = base64.b64decode(env["payload"], validate=True)
        stmt = json.loads(body)
    except (KeyError, ValueError, TypeError):
        return None, "payload ilegivel"
    sigs = env.get("signatures") or []
    if not sigs:
        return stmt, "sem assinatura"
    from cryptography.exceptions import InvalidSignature
    for s in sigs:
        pub = pubs.get(s.get("keyid"))
        if pub is None:
            continue
        try:
            pub.verify(base64.b64decode(s.get("sig", "")), pae(PAYLOAD_TYPE, body))
        except (InvalidSignature, ValueError):
            return stmt, "assinatura DSSE nao confere com a chave %s" % s.get("keyid")
        if stmt.get("_type") != STATEMENT_TYPE or stmt.get("predicateType") != PREDICATE_TYPE:
            return stmt, "nao e um Statement v1 do AISEF"
        return stmt, None
    return stmt, "nenhuma chave publica do pacote para %s" % ", ".join(str(s.get("keyid")) for s in sigs)


def verify_pack(pack, pubs, load):
    """Problemas dos atestados de um pacote de evidencia (lista vazia se nao ha ou se conferem)."""
    d = os.path.join(pack, "attestations")
    out = []
    for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        where = "attestations/" + name
        try:
            env = load(os.path.join(d, name))
        except (OSError, ValueError):
            out.append(where + ": ilegivel")
            continue
        stmt, problem = verify_envelope(env, pubs)
        if problem:
            out.append(where + ": " + problem)
            continue
        task = stmt["predicate"].get("task") or {}
        tpath = os.path.join(pack, "tasks", "%s.json" % task.get("task_id"))
        if not os.path.exists(tpath):
            out.append(where + ": a tarefa %s nao esta no pacote" % task.get("task_id"))
        elif hashlib.sha256(_canon(load(tpath))).hexdigest() != task.get("contract_sha256"):
            out.append(where + ": o contrato da tarefa no pacote nao e o atestado")
    return out
