#!/usr/bin/env python3
"""AISEF streams (0.15, T-04/T-05, ADR 0026): um log de auditoria por pessoa, para times.

Com um log so, duas pessoas anexando em branches diferentes geram conflito no merge do log.jsonl e a cadeia se parte.
Com `config.json` -> `"audit": {"streams": true, "owner": "<id>"}`:
- o log que ja existe (.aisef/audit/) vira o stream do dono, sem reescrever nada;
- cada outra pessoa ganha .aisef/audit/streams/<id>/ com cadeia propria, log_id `<projeto>.<id>`, chave Ed25519
  propria (`<id>.audit-key-1`, a privada em ~/.aisef/keys/, a publica em .aisef/keys/) e ids de evento `<id>.E<n>`;
- cada pessoa so anexa aos proprios arquivos: o merge do Git nao conflita no log;
- a decisao do usuario (aprovacao, aceite) sai assinada pela chave de quem decidiu;
- quem le o log recebe os streams juntos, em ordem de tempo (audit_chain.read_log_dir); a verificacao e stream a stream.

Identidade: AISEF_USER, senao o e-mail do Git (git config user.email), reduzido a [a-z0-9._-].

    python -I aisef_streams.py enable --project . [--owner <id>]   (decisao do usuario: o gateway pergunta)
    python -I aisef_streams.py whoami --project .
    python -I aisef_streams.py verify --project .
"""
import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def slug(raw):
    s = re.sub(r"[^a-z0-9._-]+", "-", (raw or "").strip().lower()).strip("-.")
    return s[:40] or None


def identity(project=None):
    """Quem esta gravando: AISEF_USER, senao git config user.email (local do repositorio ou global)."""
    env = slug(os.environ.get("AISEF_USER"))
    if env:
        return env
    try:
        r = subprocess.run(["git", "-C", project or ".", "config", "user.email"], capture_output=True, text=True, timeout=5)
        return slug(r.stdout.split("@")[0]) if r.returncode == 0 and r.stdout.strip() else None
    except (OSError, subprocess.SubprocessError):
        return None


def enabled(cfg):
    a = (cfg or {}).get("audit") or {}
    return a.get("streams") is True and bool(a.get("owner"))


def context(project, cfg):
    """Onde o proximo evento vai: {dir, log_id, key_id, prefix, owner}. Sem streams, ou quando quem grava e o dono,
    o stream do dono (o comportamento de sempre)."""
    import aisef_project as ap
    base = {"dir": os.path.join(ap.aisef_dir(project), "audit"), "log_id": cfg["log_id"],
            "key_id": ap.audit_settings(cfg)["key_id"], "prefix": "", "owner": True}
    if not enabled(cfg):
        return base
    who = identity(project)
    owner = slug(cfg["audit"]["owner"])
    if not who or who == owner:
        return base
    return {"dir": os.path.join(ap.aisef_dir(project), "audit", "streams", who), "log_id": "%s.%s" % (cfg["log_id"], who),
            "key_id": "%s.audit-key-1" % who, "prefix": "%s." % who, "owner": False, "user": who}


def ensure_stream(project, cfg, ctx):
    """Primeiro evento de uma pessoa: cria a chave dela (privada fora do repositorio) e o genesis do stream."""
    import aisef_audit_log as al
    import aisef_base
    os.makedirs(ctx["dir"], exist_ok=True)
    if al.last_event(ctx["dir"]) is not None:
        return
    pub = os.path.join(aisef_base.aisef_dir(project), "keys", ctx["key_id"] + ".pem")
    if aisef_base.HAS_CRYPTO:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        import aisef_keystore  # E-02: a chave da pessoa vai para onde audit.key_store manda
        if aisef_keystore.locate(cfg["project_id"], ctx["key_id"]) is None:
            key = Ed25519PrivateKey.generate()
            aisef_keystore.write(cfg["project_id"], ctx["key_id"], key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()),
                aisef_keystore.store_of(cfg))
        signer = al.load_signer(cfg["project_id"], ctx["key_id"])
        with open(pub, "wb") as fh:
            fh.write(signer.public_key_pem())
    al._write_event(project, cfg, {"event_id": ctx["prefix"] + "E0", "event_type": "genesis",
                                   "actor": {"type": "system", "id": "aisef"},
                                   "summary": "Stream de %s criado" % ctx.get("user")}, ctx)


def verify_all(project, head_source="external"):
    """(erros, avisos) de todos os streams, cada um com a propria cadeia, assinaturas e head.
    head_source: 'external' (~/.aisef/heads, a maquina de quem grava) ou 'project' (head.json versionado, para o CI)."""
    import aisef_project as ap
    import audit_chain
    root = ap.aisef_dir(project)
    errors, warnings = [], []
    try:
        import audit_signing
        from cryptography.hazmat.primitives import serialization
        pubs = {}
        kdir = os.path.join(root, "keys")
        for name in sorted(os.listdir(kdir)) if os.path.isdir(kdir) else []:
            if name.endswith(".pem"):
                with open(os.path.join(kdir, name), "rb") as fh:
                    pubs[name[:-4]] = serialization.load_pem_public_key(fh.read())
    except ImportError:
        pubs = {}
    for d in audit_chain.stream_dirs(os.path.join(root, "audit")):
        log = audit_chain.read_stream(d)
        label = os.path.relpath(d, root).replace("\\", "/")
        if not log:
            if d.endswith("audit"):
                errors.append("sem log em .aisef/audit/")
            continue
        head = None
        if head_source == "project":
            hp = os.path.join(d, "head.json")
        else:
            hp = ap.external_head_path(log[0]["log_id"])
        if os.path.exists(hp):
            with open(hp, encoding="utf-8") as fh:
                head = json.load(fh)
        if pubs:
            e, w = audit_signing.AuditVerifier(pubs).verify(log, head)
        else:
            e, w = audit_chain.verify_chain(log), ["sem assinatura Ed25519: so a cadeia de hash foi verificada"]
        errors += ["%s: %s" % (label, x) for x in e]
        warnings += ["%s: %s" % (label, x) for x in w]
    return errors, warnings


def enable(project, owner=None):
    import aisef_project as ap
    cfg = ap.load_config(project)
    owner = slug(owner) or identity(project)
    if not owner:
        raise SystemExit("nao sei quem e o dono do log: defina AISEF_USER ou o e-mail do Git, ou passe --owner")
    a = cfg.setdefault("audit", {})
    a.update({"streams": True, "owner": owner})
    ap.write_json(os.path.join(ap.aisef_dir(project), "config.json"), cfg)
    ap.append(project, {"event_type": "decision_recorded", "actor": {"type": "user", "id": "user"},
                        "summary": "log por pessoa ligado; o log atual e o stream de %s" % owner,
                        "data": {"audit_streams": True, "owner": owner}})
    return owner


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["enable", "whoami", "verify"])
    p.add_argument("--project", default=".")
    p.add_argument("--owner")
    a = p.parse_args(argv)
    project = os.path.abspath(a.project)
    if a.command == "enable":
        print("log por pessoa ligado; dono: %s" % enable(project, a.owner))
    elif a.command == "whoami":
        import aisef_project as ap
        ctx = context(project, ap.load_config(project))
        print("%s -> %s" % (identity(project) or "(desconhecido)", os.path.relpath(ctx["dir"], project)))
    else:
        e, w = verify_all(project)
        for x in e:
            print("ERRO " + x)
        for x in w:
            print("AVISO " + x)
        print("streams: %d erro(s)" % len(e))
        return 1 if e else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
