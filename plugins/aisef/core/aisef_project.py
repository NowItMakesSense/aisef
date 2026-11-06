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
    python3 -I aisef_project.py agents --project REPO [--activate] [--roles backend,qa]
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


def iso_in(**delta):
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(**delta)).astimezone().isoformat(timespec="seconds")


def home_dir():
    return os.environ.get("AISEF_HOME") or os.path.join(os.path.expanduser("~"), ".aisef")


def aisef_dir(project):
    return os.path.join(project, ".aisef")


def load_config(project):
    with open(os.path.join(aisef_dir(project), "config.json"), encoding="utf-8") as fh:
        return json.load(fh)


def private_key_path(project_id, key_id=KEY_ID):
    return os.path.join(home_dir(), "keys", project_id, key_id + ".pem")


def anchors_path(project_id):
    return os.path.join(home_dir(), "anchors", project_id + ".jsonl")


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


def load_signer(project_id, key_id=KEY_ID):
    if not os.path.exists(private_key_path(project_id, key_id)):
        return None
    if not HAS_CRYPTO:
        # um evento sem assinatura num log assinado quebraria a verificacao: melhor recusar alto
        raise RuntimeError("o log deste projeto e assinado, mas este Python nao tem 'cryptography' "
                           "(instale-a ou defina AISEF_PYTHON)")
    with open(private_key_path(project_id, key_id), "rb") as fh:
        key = serialization.load_pem_private_key(fh.read(), password=None)
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
    signer = load_signer(cfg["project_id"], audit_settings(cfg)["key_id"])
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
    if not HAS_CRYPTO:
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
    write_agent_drafts(project)
    return signed


# Agentes do plugin (plugins/aisef/agents/*.md). O contrato e o TETO; o gateway o aplica aos subagentes.
EDIT_TOOLS = ["Read", "Grep", "Glob", "Edit", "Write", "Bash"]
READ_TOOLS = ["Read", "Grep", "Glob", "Bash"]
AGENT_PROFILES = {
    "orchestrator": ("Orquestrador AISEF", ["implementation", "review", "investigation", "documentation"], EDIT_TOOLS,
                     ["repo_code", "config_ci_iac"], ["status_log_diff", "commit", "push", "merge"],
                     ["Coordenar o trabalho, executar tarefas pequenas e integrar resultados (sessao principal)"]),
    "backend": ("Agente Backend", ["implementation", "refactoring", "testing"], EDIT_TOOLS, ["repo_code", "db_schema"], ["status_log_diff", "commit"],
                ["APIs, servicos, regras de dominio e integracoes, com testes"]),
    "frontend": ("Agente Frontend", ["implementation", "refactoring", "testing"], EDIT_TOOLS, ["repo_code"], ["status_log_diff", "commit"],
                 ["Telas, componentes e fluxos de UX, com testes"]),
    "database": ("Agente de Banco de Dados", ["migration", "implementation", "review"], ["Read", "Grep", "Glob", "Edit", "Write"], ["repo_code", "db_schema"],
                 ["status_log_diff"], ["Entidades e migrations com rollback, sem conectar ao banco"]),
    "qa": ("Agente de QA", ["testing", "review"], READ_TOOLS, ["repo_code"], ["status_log_diff"],
           ["Testes, cobertura dos criterios de aceite e regressoes"]),
    "security": ("Agente de Seguranca", ["security_review", "review"], READ_TOOLS, ["repo_code"], ["status_log_diff"],
                 ["Ameacas, controle de acesso, segredos e exposicao de dados"]),
    "devops": ("Agente DevOps", ["implementation", "documentation"], EDIT_TOOLS, ["repo_code", "config_ci_iac", "deploy_infra"], ["status_log_diff", "commit"],
               ["CI/CD, IaC, estrategia de deploy e rollback, sem executar deploy"]),
    "domain": ("Agente de Dominio", ["investigation", "documentation"], ["Read", "Grep", "Glob", "WebSearch", "WebFetch"], ["repo_code"], ["status_log_diff"],
               ["Regras de negocio, glossario e excecoes, sempre com fonte"]),
    "validator": ("Agente Validador", ["validation"], READ_TOOLS, ["repo_code"], ["status_log_diff"],
                  ["Verificar criterios de aceite com evidencias, sem nunca validar o proprio trabalho"]),
}


def agent_contract(role, created_at):
    name, task_types, tools, resources, git_ops, resp = AGENT_PROFILES[role]
    doc = {
        "schema_version": "0.1.0", "agent_id": role, "contract_version": 1, "role": role, "name": name,
        "description": "Agente %s do plugin AISEF (perfil em plugins/aisef/agents/%s.md)" % (role, role),
        "responsibilities": resp, "task_types": task_types,
        "tools": {"allowed": tools, "via_execution_gateway": True},
        "permission_ceiling": {"resources": resources, "max_environment": "dev", "git_operations": git_ops},
        "context_access": {"layers": ["mandatory", "referenced", "on_demand"]},
        "communication": {"route": "orchestrator", "can_delegate_directly": False,
                          "can_message_other_agents_directly": False, "reports_discoveries_to_orchestrator": True},
        "authority": {"can_change_scope": False, "can_modify_approved_decisions": False,
                      "can_modify_other_agents_contracts": False, "can_modify_own_contract": False,
                      "can_contest_with_evidence": True, "must_stop_on_scope_change": True},
        "output": {"execution_report_schema": "execution-report/0.1.0", "formats": ["json", "technical_report"],
                   "secrets_in_output": False},
        "validation_role": {"can_self_attest_delivery": False, "can_validate_own_work": False},
        "memory": {"permanent_knowledge_source": False, "writes_discoveries_to": "project_knowledge_base"},
        "handoff": {"replaceable": True, "preserved_on_replacement": [
            "contract", "history", "evidence", "changes", "tests", "identified_problems", "original_permissions"]},
        "limits": {"max_fix_attempts": None},
        "status": "draft",
        "audit": {"created_by": "aisef-init", "created_at": created_at},
    }
    if role == "validator":
        doc["validation_role"]["validates"] = ["backend", "frontend", "database", "devops"]
    return doc


def write_agent_drafts(project):
    """Cria os Agent Contracts dos agentes do plugin como 'draft' (nao sobrescreve existentes)."""
    created = []
    for role in AGENT_PROFILES:
        path = os.path.join(aisef_dir(project), "contracts", "agents", role + ".json")
        if not os.path.exists(path):
            write_json(path, agent_contract(role, now_iso()))
            created.append(role)
    return created


def activate_agents(project, roles=None):
    """Decisao do USUARIO: ativa Agent Contracts em draft (o gateway exige o prompt nativo para isto)."""
    when, done = now_iso(), []
    for role in roles or list(AGENT_PROFILES):
        path = os.path.join(aisef_dir(project), "contracts", "agents", role + ".json")
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        if doc.get("status") != "draft":
            continue
        doc["status"] = "active"
        doc["audit"].update({"approved_by": "user", "approved_at": when})
        problems = validate(doc, "agent-contract.schema.v0.1.json")
        if problems:
            raise SystemExit("%s invalido, nada ativado:\n - %s" % (role, "\n - ".join(problems)))
        write_json(path, doc)
        append(project, {"event_type": "contract_changed", "actor": {"type": "user", "id": "user"},
                         "summary": "Agent Contract %s aprovado e ativo" % role,
                         "subject": {"kind": "agent_contract", "id": role, "version": doc["contract_version"]}})
        done.append(role)
    return done


# Segunda camada: regras 'ask' nativas do Claude Code. Valem mesmo se o hook falhar ou for desligado.
# Sao 'ask' (nao 'deny') para nao impedir o que a politica permite com aprovacao.
NATIVE_ASK_RULES = [
    "Bash(git commit:*)", "Bash(git push:*)", "Bash(git merge:*)", "Bash(git rebase:*)", "Bash(git reset --hard:*)",
    "Bash(git branch -D:*)", "Bash(git branch -d:*)", "Bash(git tag:*)", "Bash(git clean:*)", "Bash(git filter-branch:*)",
    "Bash(gh release:*)", "Bash(gh pr merge:*)", "Bash(npm publish:*)", "Bash(twine upload:*)", "Bash(cargo publish:*)",
    "Bash(psql:*)", "Bash(mysql:*)", "Bash(mongosh:*)", "Bash(redis-cli:*)", "Bash(sqlite3:*)", "Bash(sqlcmd:*)",
    "Bash(docker exec:*)", "Bash(docker compose exec:*)", "Bash(kubectl exec:*)", "Bash(kubectl delete:*)",
    "Bash(terraform apply:*)", "Bash(terraform destroy:*)", "Bash(helm install:*)", "Bash(helm upgrade:*)",
    "Bash(printenv:*)", "Bash(cat .env*)",
    "Read(./.env)", "Read(./.env.*)", "Read(./**/.env)", "Read(./**/*.pem)", "Read(./**/*.key)", "Read(./secrets/**)",
    "Edit(./.env)", "Edit(./.env.*)", "Write(./.env)", "Write(./.env.*)",
    "Edit(./.aisef/approvals/**)", "Write(./.aisef/approvals/**)", "Edit(./.aisef/authorizations/**)",
    "Write(./.aisef/authorizations/**)", "Edit(./.aisef/contracts/agents/**)", "Edit(./.aisef/config.json)",
]
NATIVE_DENY_RULES = ["Edit(./.aisef/audit/**)", "Write(./.aisef/audit/**)", "Edit(./.aisef/keys/**)", "Write(./.aisef/keys/**)"]


def native_settings(project, apply=False):
    """Mescla (uniao) as regras nativas em <repo>/.claude/settings.json. Nunca remove nada que ja exista."""
    path = os.path.join(project, ".claude", "settings.json")
    current = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            current = json.load(fh)
    perms = current.setdefault("permissions", {})
    added = {}
    for key, rules in (("ask", NATIVE_ASK_RULES), ("deny", NATIVE_DENY_RULES)):
        have = perms.setdefault(key, [])
        new = [r for r in rules if r not in have]
        have.extend(new)
        added[key] = new
    if apply and (added["ask"] or added["deny"]):
        write_json(path, current)
    return path, added


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
            with open(os.path.join(HERE, "permission-policy.v0.1.json"), encoding="utf-8") as fh:
                max_days = json.load(fh).get("scope_authorization_schema_ref", {}).get("validity_max_days")
            v = auth.get("validity", {})
            span = (datetime.datetime.fromisoformat(v["valid_until"]) - datetime.datetime.fromisoformat(v["valid_from"])).total_seconds()
            if max_days is not None and span > max_days * 86400:
                raise SystemExit("nada foi gravado; escopo de %.1f dias excede o maximo da politica (%d dias)" % (span / 86400, max_days))
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
    if req.get("request_type") == "plan_approval" and req["status"] == "approved" and req.get("feature_id"):
        reflect_plan_approval(project, req["feature_id"], when)
    return req


def reflect_plan_approval(project, feature_id, when):
    """Plano aprovado pelo usuario: o Feature Contract passa a 'approved_for_execution' e as tarefas em draft a 'ready'."""
    root = aisef_dir(project)
    fpath = os.path.join(root, "contracts", "features", feature_id + ".json")
    if not os.path.exists(fpath):
        return
    with open(fpath, encoding="utf-8") as fh:
        feature = json.load(fh)
    feature["approval"]["plan"] = {"status": "approved", "granularity": "feature", "approved_by": "user", "approved_at": when}
    if feature["state"]["status"] in ("discovery", "planning", "awaiting_plan_approval"):
        feature["state"]["status"] = "approved_for_execution"
    write_json(fpath, feature)
    for t in feature.get("task_plan", []):
        tpath = os.path.join(root, "contracts", "tasks", t["task_id"] + ".json")
        if os.path.exists(tpath):
            with open(tpath, encoding="utf-8") as fh:
                task = json.load(fh)
            if task["state"]["status"] == "draft":
                task["state"]["status"] = "ready"
                write_json(tpath, task)


def verify(project):
    """Retorna (erros, avisos). Usa o head EXTERNO como referencia, nao a copia do projeto."""
    cfg = load_config(project)
    audit_dir = os.path.join(aisef_dir(project), "audit")
    log = audit_chain.read_log_dir(audit_dir)
    if not log:
        return ["sem log em .aisef/audit/"], []
    pubs = {}
    if HAS_CRYPTO:
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


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["init", "append", "decide", "agents", "settings", "rotate-key", "anchor",
                                        "verify", "status"])
    ap.add_argument("--apply", action="store_true", help="settings: grava as regras em .claude/settings.json")
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
    ap.add_argument("--activate", action="store_true", help="agents: ativa os Agent Contracts em draft (decisao do usuario)")
    ap.add_argument("--roles", default="", help="agents: lista separada por virgula (padrao: todos)")
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
    if a.command == "settings":
        path, added = native_settings(project, a.apply)
        total = len(added["ask"]) + len(added["deny"])
        if not total:
            print("%s ja tem todas as regras do AISEF" % path)
        else:
            print("%s %d regra(s) em %s:" % ("gravadas" if a.apply else "faltam (use --apply para gravar)", total, path))
            for k in ("ask", "deny"):
                for r in added[k]:
                    print("  %s %s" % (k, r))
        return 0
    if a.command == "rotate-key":
        print("nova chave: %s" % rotate_key(project))
        return 0
    if a.command == "anchor":
        a_ = anchor(project)
        print("ancora gravada: sequencia %d em %s" % (a_["sequence"], anchors_path(load_config(project)["project_id"])))
        return 0
    if a.command == "agents":
        roles = [x for x in a.roles.split(",") if x] or None
        if a.activate:
            done = activate_agents(project, roles)
            print("ativados: %s" % (", ".join(done) or "nenhum (ja ativos ou inexistentes)"))
        else:
            created = write_agent_drafts(project)
            print("drafts criados: %s" % (", ".join(created) or "nenhum (ja existiam)"))
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
