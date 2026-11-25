#!/usr/bin/env python3

"""AISEF: init do projeto, Agent Contracts (drafts, ativacao, validador) e regras nativas de segunda camada.

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
from aisef_audit_log import *  # noqa: E402,F401,F403
from aisef_audit_log import _anchor, _rotate_if_large, _write_event  # noqa: E402,F401
try:
    from aisef_base import Ed25519PrivateKey, audit_signing  # noqa: E402,F401
except ImportError:
    pass

def init(project, project_id, name=None, environment="dev", profile="solo"):
    root = aisef_dir(project)
    if os.path.exists(os.path.join(root, "config.json")):
        raise SystemExit("ja existe %s; nada foi alterado" % os.path.join(root, "config.json"))
    if not aisef_base.HAS_CRYPTO:  # D5 (0.13): o AISEF nao comeca sem log assinado
        import aisef_env
        raise SystemExit("AISEF nao iniciado (nada foi criado): o log precisa ser assinado com Ed25519. "
                         + aisef_env.advice(aisef_env.missing_libs() or ["cryptography"], found=aisef_env.find_python()))
    for sub in SUBDIRS:
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    write_json(os.path.join(root, "config.json"), {
        "schema_version": "0.1.0", "project_id": project_id, "log_id": project_id,
        "name": name or project_id, "environment": environment, "created_at": now_iso(),
        "policy": "permission-policy.v0.1.json", "defaults": "orchestration-defaults.v0.1.json",
        "graphify": {"enabled": True, "backend": "none", "paths": ["docs", ".aisef"]},
        "profile": profile, "plugin_version": _plugin_version(), "audit": {"telemetry": "split"}})
    with open(os.path.join(root, ".gitignore"), "w", encoding="utf-8") as fh:
        fh.write("# gerado pelo AISEF\n*.lock\n*.tmp\npanel/\nruntime/\nworktrees/\n")
    signed = False
    if aisef_base.HAS_CRYPTO:
        import aisef_keystore  # E-02: projeto novo comeca no arquivo; o migrate leva ao cofre
        if aisef_keystore.locate(project_id, KEY_ID) is None:
            key = Ed25519PrivateKey.generate()
            aisef_keystore.write(project_id, KEY_ID, key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
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
AGENT_PROFILES = aisef_catalog.profiles()  # fonte unica: core/agents/catalog.v0.1.json


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
        doc["validation_role"]["validates"] = aisef_catalog.validatable_roles()
    return doc


def project_traits(project):
    """Stacks, estilos de arquitetura e dominios do projeto, lidos de .aisef/architecture.json (aisef_detect).
    Sem o arquivo, so os papeis `always` se aplicam."""
    path = os.path.join(aisef_dir(project), "architecture.json")
    if not os.path.exists(path):
        return (), (), ()
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    styles = (doc.get("approved") or {}).get("styles") or [s["id"] for s in doc.get("styles", []) if s.get("confidence", 0) >= 0.5]
    return tuple(s["id"] for s in doc.get("stacks", [])), tuple(styles), tuple(doc.get("domains", []))


def adopt_styles(project, styles, request_id):
    """Registra em architecture.json o estilo que o USUARIO adotou, so com architecture_decision aprovado."""
    import aisef_detect
    if not styles or not request_id:
        raise SystemExit("--adopt exige os estilos e --request (architecture_decision aprovado)")
    path = os.path.join(aisef_dir(project), "approvals", request_id + ".json")
    if not os.path.exists(path):
        raise SystemExit("pedido %s nao existe" % request_id)
    with open(path, encoding="utf-8") as fh:
        req = json.load(fh)
    if req.get("status") != "approved" or req.get("request_type") != "architecture_decision":
        raise SystemExit("pedido %s precisa ser architecture_decision aprovado pelo usuario" % request_id)
    known = set(aisef_detect.STYLES) | {"modular-monolith", "microservices"}
    unknown = [s for s in styles if s not in known]
    if unknown:
        raise SystemExit("estilo desconhecido: %s (validos: %s)" % (", ".join(unknown), ", ".join(sorted(known))))
    doc = aisef_detect.detect(project)
    doc["approved"] = {"styles": styles, "request_id": request_id, "approved_at": now_iso()}
    aisef_detect.write(project, doc)
    append(project, {"event_type": "decision_recorded", "actor": {"type": "system", "id": "aisef_detect"},
                     "summary": "Estilo de arquitetura adotado: %s (%s)" % (", ".join(styles), request_id)})
    return doc["approved"]


def write_agent_drafts(project, roles=None):
    """Cria os Agent Contracts como 'draft' (nao sobrescreve existentes). Sem `roles`, cria os papeis que se aplicam
    ao projeto pelo catalogo (activation always, ou stack/arch/domain detectados); com `roles`, cria esses
    (inclusive os de ativacao manual, que o usuario pediu)."""
    if roles is None:
        stacks, styles, domains = project_traits(project)
        roles = [r["id"] for r in aisef_catalog.roles() if aisef_catalog.applicable(r, stacks, styles, domains)]
    unknown = [r for r in roles if r not in AGENT_PROFILES]
    if unknown:
        raise SystemExit("papel fora do catalogo de agentes: %s" % ", ".join(unknown))
    created = []
    for role in roles:
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
        if not os.path.exists(path):
            continue  # projeto anterior ao agente: `agents` (sem --activate) cria o draft
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
    if "implementer" in done:
        upgrade_validator(project, when)
    return done


def upgrade_validator(project, when):
    """Projetos anteriores a 0.6.0: o validador ativo passa a validar o implementer (nova versao do contrato,
    registrada como decisao do usuario, porque acontece dentro do `agents --activate` que ele aprovou)."""
    path = os.path.join(aisef_dir(project), "contracts", "agents", "validator.json")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    validates = doc.setdefault("validation_role", {}).setdefault("validates", [])
    if "implementer" in validates:
        return
    validates.insert(0, "implementer")
    doc["contract_version"] += 1
    problems = validate(doc, "agent-contract.schema.v0.1.json")
    if problems:
        raise SystemExit("validator invalido apos a atualizacao:\n - " + "\n - ".join(problems))
    write_json(path, doc)
    append(project, {"event_type": "contract_changed", "actor": {"type": "user", "id": "user"},
                     "summary": "Agent Contract validator v%d: passa a validar o implementer" % doc["contract_version"],
                     "subject": {"kind": "agent_contract", "id": "validator", "version": doc["contract_version"]}})


# Segunda camada: regras 'ask' nativas do Claude Code. Valem mesmo se o hook falhar ou for desligado.
# Sao 'ask' (nao 'deny') para nao impedir o que a politica permite com aprovacao.
NATIVE_ASK_RULES = [
    "Bash(git commit:*)", "Bash(git push:*)", "Bash(git merge:*)", "Bash(git rebase:*)", "Bash(git reset --hard:*)",
    "Bash(git branch -D:*)", "Bash(git branch -d:*)", "Bash(git tag:*)", "Bash(git clean:*)", "Bash(git filter-branch:*)",
    "Bash(gh release:*)", "Bash(gh pr create:*)", "Bash(gh pr merge:*)", "Bash(npm publish:*)", "Bash(twine upload:*)", "Bash(cargo publish:*)",
    "Bash(psql:*)", "Bash(mysql:*)", "Bash(mongosh:*)", "Bash(redis-cli:*)", "Bash(sqlite3:*)", "Bash(sqlcmd:*)",
    "Bash(docker exec:*)", "Bash(docker compose exec:*)", "Bash(kubectl exec:*)", "Bash(kubectl delete:*)",
    "Bash(terraform apply:*)", "Bash(terraform destroy:*)", "Bash(helm install:*)", "Bash(helm upgrade:*)",
    "Bash(printenv:*)", "Bash(cat .env*)",
    "Bash(npx skills add:*)", "Bash(npx skills update:*)", "Bash(claude plugin install:*)",
    "Bash(claude plugin marketplace add:*)", "Bash(claude mcp add:*)", "Edit(./.mcp.json)", "Write(./.mcp.json)",
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
    # sem isto, iniciar a sessao em bypassPermissions desliga as regras acima (o gateway ainda nega o sensivel)
    added["settings"] = []
    if perms.get("disableBypassPermissionsMode") != "disable":
        perms["disableBypassPermissionsMode"] = "disable"
        added["settings"].append("disableBypassPermissionsMode=disable")
    # CLIs de busca (npx skills) mandam uso anonimo por padrao; DO_NOT_TRACK desliga sem mexer no Claude Code.
    # Um valor que o usuario ja definiu e respeitado.
    env = current.setdefault("env", {})
    if "DO_NOT_TRACK" not in env:
        env["DO_NOT_TRACK"] = "1"
        added["settings"].append("env.DO_NOT_TRACK=1")
    if apply and (added["ask"] or added["deny"] or added["settings"]):
        write_json(path, current)
    return path, added
