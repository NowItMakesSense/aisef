#!/usr/bin/env python3
"""AISEF: estado do projeto alvo em <repo>/.aisef (v0.1).

O plugin guarda codigo, schemas e politica; o projeto guarda so dados. Este modulo cria a estrutura,
anexa eventos ao log de auditoria e verifica a integridade.

Chaves e head ficam FORA do projeto (decisao do chat: o head nao pode ficar no mesmo armazenamento
do log, e agentes nunca tocam a chave privada):
    ~/.aisef/keys/<project_id>/audit-key-1.pem   chave PRIVADA do Audit Signer
    ~/.aisef/heads/<project_id>.json             head assinado de referencia
No projeto ficam a chave PUBLICA (.aisef/keys/) e uma copia do head (.aisef/audit/head.json) para o painel.
Sem a biblioteca cryptography, o log continua com cadeia de hash, mas sem assinatura (aviso no verify).

Uso:
    python3 -I aisef_project.py init   --project REPO --project-id ID [--name N] [--environment dev|staging|prod]
    python3 -I aisef_project.py append --project REPO --type EVENT_TYPE --summary TEXTO
                                       [--actor TIPO] [--actor-id ID] [--feature F] [--task T] [--data JSON]
    python3 -I aisef_project.py decide --project REPO --request APR-NNN --choice approve|reject|request_changes|select_option
                                       [--option OPT-X] [--note TEXTO] [--ack impact_read,rollback_read,diff_reviewed]
                                       [--authorization rascunho.json]
    python3 -I aisef_project.py verify --project REPO
    python3 -I aisef_project.py status --project REPO
"""
import argparse
import datetime
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import audit_chain  # noqa: E402

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    import audit_signing
    HAS_CRYPTO = True
except ImportError:  # assinatura opcional
    HAS_CRYPTO = False

KEY_ID = "audit-key-1"
SUBDIRS = ["contracts/features", "contracts/tasks", "contracts/agents", "blueprints", "approvals",
           "authorizations", "reports", "audit", "keys", "panel"]


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


def home_dir():
    return os.environ.get("AISEF_HOME") or os.path.join(os.path.expanduser("~"), ".aisef")


def aisef_dir(project):
    return os.path.join(project, ".aisef")


def load_config(project):
    with open(os.path.join(aisef_dir(project), "config.json"), encoding="utf-8") as fh:
        return json.load(fh)


def private_key_path(project_id):
    return os.path.join(home_dir(), "keys", project_id, KEY_ID + ".pem")


def external_head_path(project_id):
    return os.path.join(home_dir(), "heads", project_id + ".json")


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


class Lock:
    """Lock por arquivo exclusivo: varias sessoes/hooks podem anexar ao mesmo log."""

    def __init__(self, path, timeout=10.0):
        self.path, self.timeout = path, timeout

    def __enter__(self):
        deadline = time.time() + self.timeout
        while True:
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except FileExistsError:
                if time.time() > deadline:
                    raise TimeoutError("log de auditoria travado: " + self.path)
                time.sleep(0.05)

    def __exit__(self, *exc):
        os.close(self.fd)
        os.remove(self.path)


def load_signer(project_id):
    if not os.path.exists(private_key_path(project_id)):
        return None
    if not HAS_CRYPTO:
        # um evento sem assinatura num log assinado quebraria a verificacao: melhor recusar alto
        raise RuntimeError("o log deste projeto e assinado, mas este Python nao tem 'cryptography' "
                           "(instale-a ou defina AISEF_PYTHON)")
    with open(private_key_path(project_id), "rb") as fh:
        key = serialization.load_pem_private_key(fh.read(), password=None)
    return audit_signing.AuditSigner(KEY_ID, key)


def append(project, partial):
    """Anexa um evento (sequence, prev_hash e hash sao preenchidos aqui) e assina se houver chave."""
    cfg = load_config(project)
    log_path = os.path.join(aisef_dir(project), "audit", "log.jsonl")
    event = {"schema_version": "0.1.0", "log_id": cfg["log_id"], "project_id": cfg["project_id"],
             "timestamp": now_iso()}
    event.update(partial)
    with Lock(log_path + ".lock"):
        log = audit_chain.read_log(log_path) if os.path.exists(log_path) else []
        event.setdefault("event_id", "E%d" % len(log))
        signer = load_signer(cfg["project_id"])
        if signer:
            new = signer.append(log, event)
        else:
            new = audit_chain.append_event(log, event)
        with open(log_path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(new, ensure_ascii=False) + "\n")
        if signer:
            write_json(external_head_path(cfg["project_id"]), signer.head)
            write_json(os.path.join(aisef_dir(project), "audit", "head.json"), signer.head)
    return new


def init(project, project_id, name=None, environment="dev"):
    root = aisef_dir(project)
    if os.path.exists(os.path.join(root, "config.json")):
        raise SystemExit("ja existe %s; nada foi alterado" % os.path.join(root, "config.json"))
    for sub in SUBDIRS:
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    write_json(os.path.join(root, "config.json"), {
        "schema_version": "0.1.0", "project_id": project_id, "log_id": project_id,
        "name": name or project_id, "environment": environment, "created_at": now_iso(),
        "policy": "permission-policy.v0.1.json", "defaults": "orchestration-defaults.v0.1.json"})
    with open(os.path.join(root, ".gitignore"), "w", encoding="utf-8") as fh:
        fh.write("# gerado pelo AISEF\n*.lock\n*.tmp\npanel/\n")
    signed = False
    if HAS_CRYPTO:
        priv_path = private_key_path(project_id)
        if not os.path.exists(priv_path):
            os.makedirs(os.path.dirname(priv_path), exist_ok=True)
            key = Ed25519PrivateKey.generate()
            with open(priv_path, "wb") as fh:
                fh.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
            try:
                os.chmod(priv_path, 0o600)
            except OSError:
                pass
        signer = load_signer(project_id)
        with open(os.path.join(root, "keys", KEY_ID + ".pem"), "wb") as fh:
            fh.write(signer.public_key_pem())
        signed = True
    append(project, {"event_id": "E0", "event_type": "genesis", "actor": {"type": "system", "id": "aisef"},
                     "summary": "Log criado"})
    return signed


CHOICE_STATUS = {"approve": "approved", "select_option": "approved", "reject": "rejected",
                 "request_changes": "changes_requested"}


def validate(doc, schema_file):
    """Valida contra o schema quando jsonschema existe; sem ela, o aisef-check pega depois."""
    try:
        import jsonschema
    except ImportError:
        return []
    with open(os.path.join(HERE, schema_file), encoding="utf-8") as fh:
        schema = json.load(fh)
    v = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    return ["%s: %s" % ("/".join(map(str, e.absolute_path)) or "(raiz)", e.message) for e in v.iter_errors(doc)]


def decide(project, request_id, choice, option=None, note=None, ack=(), authorization_draft=None):
    """Registra a decisao do USUARIO sobre um pedido pendente do Approval Center.

    Uma unica chamada grava a decisao, a autorizacao gerada (escopo ou reforcada) e o evento de
    auditoria. O gateway exige o prompt nativo de permissao para este comando: e ali que o usuario decide.
    """
    root = aisef_dir(project)
    req_path = os.path.join(root, "approvals", request_id + ".json")
    with open(req_path, encoding="utf-8") as fh:
        req = json.load(fh)
    if req.get("status") != "pending":
        raise SystemExit("%s nao esta pendente (status %s): decisao nao muda, crie um novo pedido" % (request_id, req.get("status")))
    when = now_iso()
    req["status"] = CHOICE_STATUS[choice]
    req["decision"] = {"choice": choice, "decided_by": "user", "decided_at": when}
    if option:
        req["decision"]["selected_option_id"] = option
    if note:
        req["decision"]["note"] = note
    if ack:
        req["decision"]["acknowledged"] = list(ack)

    auth, auth_path = None, None
    if authorization_draft and req["status"] == "approved":
        with open(authorization_draft, encoding="utf-8") as fh:
            auth = json.load(fh)
        if auth.get("kind") == "scope":
            auth.update({"status": "active", "granted_by": "user", "granted_at": when})
            auth.setdefault("history", []).append({"event": "granted", "at": when, "by": "user"})
            auth_id, kind = auth["authorization_id"], "scope_authorization"
        elif auth.get("kind") == "reinforced":
            auth.update({"status": "approved", "decided_by": "user", "decided_at": when})
            auth_id, kind = auth["approval_id"], "reinforced_approval"
        else:
            raise SystemExit("autorizacao com kind desconhecido: %r" % auth.get("kind"))
        req["resulting_ref"] = {"kind": kind, "id": auth_id}
        auth_path = os.path.join(root, "authorizations", auth_id + ".json")
        if os.path.exists(auth_path):
            raise SystemExit("%s ja existe; autorizacoes nao sao sobrescritas" % auth_path)

    req.setdefault("audit", {})["decided_event_ref"] = "events/pending"
    problems = validate(req, "approval-request.schema.v0.1.json")
    if auth:
        problems += ["autorizacao: " + p for p in validate(auth, "authorization.schema.v0.1.json")]
    if problems:
        raise SystemExit("nada foi gravado; documento invalido:\n - " + "\n - ".join(problems))

    etype = "approval_granted" if req["status"] == "approved" else "approval_rejected"
    partial = {"event_type": etype, "actor": {"type": "user", "id": "user"},
               "summary": "%s: %s" % (request_id, req["status"]),
               "data": {"request_id": request_id, "request_type": req.get("request_type"), "choice": choice}}
    if req.get("feature_id"):
        partial["feature_id"] = req["feature_id"]
    ev = append(project, partial)
    if auth:
        append(project, {"event_type": "authorization_granted", "actor": {"type": "user", "id": "user"},
                         "summary": "%s concedida" % req["resulting_ref"]["id"], "caused_by": ev["event_id"],
                         "subject": {"kind": req["resulting_ref"]["kind"], "id": req["resulting_ref"]["id"]}})
        write_json(auth_path, auth)
    req["audit"]["decided_event_ref"] = "events/%d" % ev["sequence"]
    write_json(req_path, req)
    return req


def verify(project):
    """Retorna (erros, avisos). Usa o head EXTERNO como referencia, nao a copia do projeto."""
    cfg = load_config(project)
    log_path = os.path.join(aisef_dir(project), "audit", "log.jsonl")
    if not os.path.exists(log_path):
        return ["sem log em .aisef/audit/log.jsonl"], []
    log = audit_chain.read_log(log_path)
    pub_path = os.path.join(aisef_dir(project), "keys", KEY_ID + ".pem")
    if not (HAS_CRYPTO and os.path.exists(pub_path)):
        return audit_chain.verify_chain(log), ["sem assinatura Ed25519: so a cadeia de hash foi verificada"]
    with open(pub_path, "rb") as fh:
        pub = serialization.load_pem_public_key(fh.read())
    head = None
    if os.path.exists(external_head_path(cfg["project_id"])):
        with open(external_head_path(cfg["project_id"]), encoding="utf-8") as fh:
            head = json.load(fh)
    return audit_signing.AuditVerifier({KEY_ID: pub}).verify(log, head)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["init", "append", "decide", "verify", "status"])
    ap.add_argument("--project", default=os.getcwd())
    ap.add_argument("--project-id")
    ap.add_argument("--name")
    ap.add_argument("--environment", default="dev", choices=["dev", "staging", "prod"])
    ap.add_argument("--type")
    ap.add_argument("--summary")
    ap.add_argument("--actor", default="orchestrator", choices=["user", "orchestrator", "agent", "validator", "system"])
    ap.add_argument("--actor-id", default="aisef")
    ap.add_argument("--feature")
    ap.add_argument("--task")
    ap.add_argument("--data")
    ap.add_argument("--request")
    ap.add_argument("--choice", choices=sorted(CHOICE_STATUS))
    ap.add_argument("--option")
    ap.add_argument("--note")
    ap.add_argument("--ack", default="", help="impact_read,rollback_read,diff_reviewed")
    ap.add_argument("--authorization", help="rascunho JSON da autorizacao gerada (escopo ou reforcada)")
    a = ap.parse_args(argv)
    project = os.path.abspath(a.project)

    if a.command == "init":
        if not a.project_id:
            ap.error("--project-id e obrigatorio")
        signed = init(project, a.project_id, a.name, a.environment)
        print("AISEF iniciado em %s (log %s)" % (aisef_dir(project), "assinado com Ed25519" if signed else "SEM assinatura: instale cryptography"))
        return 0
    if a.command == "append":
        if not (a.type and a.summary):
            ap.error("--type e --summary sao obrigatorios")
        partial = {"event_type": a.type, "actor": {"type": a.actor, "id": a.actor_id}, "summary": a.summary}
        if a.feature:
            partial["feature_id"] = a.feature
        if a.task:
            partial["task_id"] = a.task
        if a.data:
            partial["data"] = json.loads(a.data)
        ev = append(project, partial)
        print("evento %s (sequencia %d) registrado" % (ev["event_id"], ev["sequence"]))
        return 0
    if a.command == "decide":
        if not (a.request and a.choice):
            ap.error("--request e --choice sao obrigatorios")
        req = decide(project, a.request, a.choice, a.option, a.note,
                     [x for x in a.ack.split(",") if x], a.authorization)
        print("%s -> %s%s" % (a.request, req["status"],
                              " (gerou %s)" % req["resulting_ref"]["id"] if req.get("resulting_ref") else ""))
        return 0
    errors, warnings = verify(project)
    for w in warnings:
        print("aviso:", w)
    for e in errors:
        print("ERRO:", e)
    if a.command == "status":
        cfg = load_config(project)
        print(json.dumps({"project_id": cfg["project_id"], "environment": cfg["environment"],
                          "audit_ok": not errors}, ensure_ascii=False))
    else:
        print("integridade ok" if not errors else "%d erro(s) de integridade" % len(errors))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
