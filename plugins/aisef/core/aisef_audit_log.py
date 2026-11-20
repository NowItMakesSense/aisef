#!/usr/bin/env python3

"""AISEF: log de auditoria: append assinado, ator, rotacao, ancora, rotacao de chave e verify.

H-01 (0.14): parte do antigo aisef_project.py. Importe pela fachada `aisef_project`, que reexporta tudo."""

import base64  # noqa: F401
import datetime  # noqa: F401
import fnmatch  # noqa: F401
import glob  # noqa: F401
import json  # noqa: F401
import os
import re  # noqa: F401
import sys
import time  # noqa: F401

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_base  # noqa: E402
import aisef_catalog  # noqa: E402,F401
import audit_chain  # noqa: E402,F401

from aisef_base import *  # noqa: E402,F401,F403
from aisef_base import _ED25519_PKCS8_PREFIX, _LazySerialization, _load_private_key, _plugin_version  # noqa: E402,F401
try:
    from aisef_base import Ed25519PrivateKey, audit_signing  # noqa: E402,F401
except ImportError:
    pass

def audit_settings(cfg):
    """Limites do log; ajustaveis em config.json -> audit. Valores pequenos so fazem sentido em teste."""
    a = cfg.get("audit", {})
    return {"key_id": a.get("key_id", KEY_ID), "checkpoint_every": a.get("checkpoint_every", 500),
            "rotate_bytes": a.get("rotate_bytes", 5 * 1024 * 1024)}


def last_line(path):
    """Ultima linha nao vazia sem ler o arquivo inteiro (o log so cresce)."""
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        pos, buf = fh.tell(), b""
        while pos > 0:
            step = min(4096, pos)
            pos -= step
            fh.seek(pos)
            buf = fh.read(step) + buf
            lines = [l for l in buf.split(b"\n") if l.strip()]
            if len(lines) > 1 or (lines and pos == 0):
                return json.loads(lines[-1].decode("utf-8"))
    return None


def last_event(audit_dir):
    for seg in reversed(audit_chain.log_segments(audit_dir)):
        if os.path.getsize(seg):
            return last_line(seg)
    return None


def load_signer(project_id, key_id=KEY_ID):
    if not os.path.exists(private_key_path(project_id, key_id)):
        return None
    if not aisef_base.HAS_CRYPTO:
        # um evento sem assinatura num log assinado quebraria a verificacao: melhor recusar alto
        raise RuntimeError("o log deste projeto e assinado, mas este Python nao tem 'cryptography' "
                           "(instale-a ou defina AISEF_PYTHON)")
    with open(private_key_path(project_id, key_id), "rb") as fh:
        key = _load_private_key(fh.read())
    return audit_signing.AuditSigner(key_id, key)


def _write_event(project, cfg, partial):
    """Anexa UM evento ao segmento atual. Chamar com o lock do log ja obtido."""
    audit_dir = os.path.join(aisef_dir(project), "audit")
    log_path = os.path.join(audit_dir, "log.jsonl")
    last = last_event(audit_dir)
    event = {"schema_version": "0.1.0", "log_id": cfg["log_id"], "project_id": cfg["project_id"],
             "timestamp": now_iso()}
    event.update(partial)
    event.setdefault("event_id", "E%d" % (last["sequence"] + 1 if last else 0))
    tail = [last] if last else []  # a cadeia so precisa do ultimo evento (sequencia e hash)
    key_id = audit_settings(cfg)["key_id"]
    signer = load_signer(cfg["project_id"], key_id)
    if signer is None and any(n.endswith(".pem") for n in os.listdir(os.path.join(aisef_dir(project), "keys"))):
        # log assinado sem a chave privada: gravar sem assinatura quebraria a verificacao em silencio
        raise RuntimeError("o log deste projeto e assinado, mas a chave privada %s nao foi encontrada "
                           "(confira AISEF_HOME)" % private_key_path(cfg["project_id"], key_id))
    new = signer.append(tail, event) if signer else audit_chain.append_event(tail, event)
    with open(log_path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(new, ensure_ascii=False) + "\n")
    if signer:
        write_json(external_head_path(cfg["project_id"]), signer.head)
        write_json(os.path.join(audit_dir, "head.json"), signer.head)
    return new


def _rotate_if_large(project, cfg):
    """Arquiva o segmento atual quando passa do limite. A cadeia continua no proximo segmento."""
    audit_dir = os.path.join(aisef_dir(project), "audit")
    log_path = os.path.join(audit_dir, "log.jsonl")
    if not os.path.exists(log_path) or os.path.getsize(log_path) < audit_settings(cfg)["rotate_bytes"]:
        return
    with open(log_path, encoding="utf-8") as fh:
        first = json.loads(fh.readline())
    last = last_line(log_path)
    archive = os.path.join(audit_dir, "archive")
    os.makedirs(archive, exist_ok=True)
    os.replace(log_path, os.path.join(archive, "log-%09d-%09d.jsonl" % (first["sequence"], last["sequence"])))


def check_append_actor(project, event_type, actor_type, actor_id, task_id, corrects):
    """Recusa, antes de gravar, eventos que o check_project acusaria para sempre (o log e imutavel).
    Devolve a mensagem do problema ou None."""
    if (event_type == "correction") != bool(corrects):
        return "--corrects e obrigatorio em 'correction' e so vale nele"
    if actor_type in ("agent", "validator") and actor_id in (None, "", "aisef"):
        return "ator %s exige --actor-id com o Agent Contract (ex.: backend, validator)" % actor_type
    if event_type in ("task_started", "task_executed") and task_id:
        path = os.path.join(aisef_dir(project), "contracts", "tasks", task_id + ".json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                assigned = json.load(fh)["assigned_agent"]["agent_id"]
            if actor_type != "agent" or actor_id != assigned:
                return ("%s de %s e registrado pelo agente da tarefa: --actor agent --actor-id %s "
                        "(o orquestrador registra 'delegation')" % (event_type, task_id, assigned))
    return None


def append(project, partial):
    """Anexa um evento (sequence, prev_hash e hash sao preenchidos aqui) e assina se houver chave.
    A cada `checkpoint_every` eventos grava um checkpoint assinado e uma ancora externa; segmentos
    grandes sao arquivados."""
    cfg = load_config(project)
    log_path = os.path.join(aisef_dir(project), "audit", "log.jsonl")
    with Lock(log_path + ".lock"):
        new = _write_event(project, cfg, partial)
        every = audit_settings(cfg)["checkpoint_every"]
        if every and new["sequence"] and (new["sequence"] + 1) % every == 0 and new["event_type"] != "checkpoint":
            cp = _write_event(project, cfg, {"event_type": "checkpoint", "actor": {"type": "system", "id": "aisef"},
                                             "summary": "Checkpoint ate a sequencia %d" % new["sequence"],
                                             "data": {"through_sequence": new["sequence"], "through_hash": new["hash"]}})
            _anchor(cfg, cp)
        _rotate_if_large(project, cfg)
    return new


def _anchor(cfg, event):
    rec = {"at": now_iso(), "sequence": event["sequence"], "hash": event["hash"]}
    path = anchors_path(cfg["project_id"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


def anchor(project):
    """Ancora manual: grava o ultimo evento em ~/.aisef/anchors/ (fora do repositorio e do log)."""
    cfg = load_config(project)
    last = last_event(os.path.join(aisef_dir(project), "audit"))
    return _anchor(cfg, last)


def rotate_key(project):
    """Troca a chave do Audit Signer. O evento de rotacao e assinado pela chave ANTIGA, que depois e apagada:
    dali em diante, um evento assinado por ela e erro na verificacao."""
    if not aisef_base.HAS_CRYPTO:
        raise SystemExit("rotacao exige a biblioteca cryptography")
    cfg = load_config(project)
    old = audit_settings(cfg)["key_id"]
    n = int(old.rsplit("-", 1)[-1]) + 1 if old.rsplit("-", 1)[-1].isdigit() else 2
    new_id = "audit-key-%d" % n
    key = Ed25519PrivateKey.generate()
    priv = private_key_path(cfg["project_id"], new_id)
    os.makedirs(os.path.dirname(priv), exist_ok=True)
    with open(priv, "wb") as fh:
        fh.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    with open(os.path.join(aisef_dir(project), "keys", new_id + ".pem"), "wb") as fh:
        fh.write(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    ev = append(project, {"event_type": "checkpoint", "actor": {"type": "system", "id": "aisef"},
                          "summary": "Rotacao da chave de auditoria: %s -> %s" % (old, new_id),
                          "data": {"key_rotation": {"from": old, "to": new_id}}})
    cfg.setdefault("audit", {})["key_id"] = new_id
    write_json(os.path.join(aisef_dir(project), "config.json"), cfg)
    _anchor(cfg, ev)
    try:
        os.remove(private_key_path(cfg["project_id"], old))
    except OSError:
        pass
    return new_id


def verify(project):
    """Retorna (erros, avisos). Usa o head EXTERNO como referencia, nao a copia do projeto."""
    cfg = load_config(project)
    audit_dir = os.path.join(aisef_dir(project), "audit")
    log = audit_chain.read_log_dir(audit_dir)
    if not log:
        return ["sem log em .aisef/audit/"], []
    pubs = {}
    if aisef_base.HAS_CRYPTO:
        for name in sorted(os.listdir(os.path.join(aisef_dir(project), "keys"))):
            if name.endswith(".pem"):
                with open(os.path.join(aisef_dir(project), "keys", name), "rb") as fh:
                    pubs[name[:-4]] = serialization.load_pem_public_key(fh.read())
    if not pubs:
        errors, warnings = audit_chain.verify_chain(log), ["sem assinatura Ed25519: so a cadeia de hash foi verificada"]
    else:
        head = None
        if os.path.exists(external_head_path(cfg["project_id"])):
            with open(external_head_path(cfg["project_id"]), encoding="utf-8") as fh:
                head = json.load(fh)
        errors, warnings = audit_signing.AuditVerifier(pubs).verify(log, head)
        errors += rotation_errors(log)
    errors += anchor_errors(cfg, log)
    return errors, warnings


def rotation_errors(log):
    """Depois de uma rotacao, a chave antiga nao assina mais nada."""
    errors, retired = [], {}
    for ev in log:
        sig_key = (ev.get("signature") or {}).get("key_id")
        if sig_key in retired:
            errors.append("evento %d assinado pela chave %s, aposentada na sequencia %d" % (ev["sequence"], sig_key, retired[sig_key]))
        rot = (ev.get("data") or {}).get("key_rotation")
        if ev.get("event_type") == "checkpoint" and rot:
            retired[rot["from"]] = ev["sequence"]
    return errors


def anchor_errors(cfg, log):
    """Ancoras externas: cada uma precisa bater com o evento da mesma sequencia (detecta reescrita e truncamento)."""
    path = anchors_path(cfg["project_id"])
    if not os.path.exists(path):
        return []
    by_seq = {ev["sequence"]: ev["hash"] for ev in log}
    errors = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            a = json.loads(line)
            if a["sequence"] not in by_seq:
                errors.append("ancora da sequencia %d nao existe mais no log (truncado?)" % a["sequence"])
            elif by_seq[a["sequence"]] != a["hash"]:
                errors.append("ancora da sequencia %d nao confere com o log (reescrito?)" % a["sequence"])
    return errors
