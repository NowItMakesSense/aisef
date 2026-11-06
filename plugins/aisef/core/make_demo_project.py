#!/usr/bin/env python3
"""Cria um projeto AISEF de demonstracao (contratos, aprovacoes, relatorio e log assinado).

Serve de exemplo e de dado de teste para o painel. A chave PRIVADA do Audit Signer nunca vai para o
diretorio do projeto: so a chave publica (keys/audit-key-1.pem).

Uso:
    python3 -I make_demo_project.py <diretorio-de-destino>
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import audit_signing  # noqa: E402

T0 = "2026-11-05T14:00:00-03:00"
# O demo e uma foto fixa: escopo e pedido pendente vencem em 2026-11-06 14:00 (-03:00). Checagens do demo
# usam este relogio (check_project --now), senao passam a acusar expiracao depois dessa data.
DEMO_NOW = "2026-11-05T15:00:00-03:00"


def ts(minute):
    return "2026-11-05T14:%02d:00-03:00" % minute


def write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def agent(agent_id, name, role, validates=None):
    a = {
        "schema_version": "0.1.0", "agent_id": agent_id, "contract_version": 1, "role": role, "name": name,
        "description": "Agente de demonstracao com perfil permanente e tetos de permissao",
        "responsibilities": ["Executar tarefas delegadas dentro do escopo"],
        "task_types": ["validation"] if role == "validator" else ["implementation", "testing"],
        "tools": {"allowed": ["Read", "Edit", "Bash"], "via_execution_gateway": True},
        "permission_ceiling": {"resources": ["repo_code", "db_schema"], "max_environment": "dev",
                               "git_operations": ["status_log_diff"] if role == "validator" else ["status_log_diff", "commit"]},
        "context_access": {"layers": ["mandatory", "referenced"]},
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
        "limits": {"max_fix_attempts": None}, "status": "active",
        "audit": {"created_by": "user", "created_at": T0, "approved_by": "user", "approved_at": T0},
    }
    if validates:
        a["validation_role"]["validates"] = validates
    return a


def task(task_id, title, status, deps, req, crit, parallelizable=False):
    return {
        "schema_version": "0.1.0", "task_id": task_id, "contract_version": 1,
        "feature_id": "FEAT-001", "feature_contract_version": 1, "title": title,
        "objective": "Objetivo da tarefa: " + title,
        "assigned_agent": {"agent_id": "backend-1", "agent_contract_version": 1, "role": "backend"},
        "requirements": {"requirement_ids": [{"id": req, "version": 1}]},
        "scope": {"included": ["modulo auth"], "excluded": ["refresh token"], "paths_allowed": ["src/auth/*", "tests/auth/*"]},
        "dependencies": {"depends_on": deps, "parallelizable": parallelizable},
        "context": {"mandatory": [{"ref": "blueprint", "origin": "blueprint", "version": "1"}]},
        "permissions": {"environment": "dev", "scope_authorization_id": "AUTH-1", "resources": ["repo_code", "db_schema"]},
        "acceptance_criteria": [{"id": crit, "description": "Criterio verificavel de " + title, "required": True,
                                 "verification": {"method": "automated_test", "evidence_expected": "saida do teste"},
                                 "requirement_ids": [req]}],
        "validation": {"independent_validator_required": True},
        "deliverables": {"execution_report_schema": "execution-report/0.1.0"},
        "risk": {"level": "low"}, "limits": {"max_fix_attempts": None},
        "escalation": {"stop_and_report_when": ["scope_exceeded", "unexpected_risk"]},
        "state": {"status": status},
        "audit": {"created_by": "orchestrator", "created_at": T0},
    }


def requirement(rid, statement):
    return {"id": rid, "version": 1, "kind": "functional", "statement": statement, "origin": "user_stated",
            "status": "active",
            "history": [{"version": 1, "statement": statement, "author": "user", "justification": "criacao", "changed_at": T0}]}


def feature():
    return {
        "schema_version": "0.1.0", "feature_id": "FEAT-001", "contract_version": 1, "cycle": {"number": 1},
        "title": "Autenticacao JWT", "objective": "Permitir login com token JWT",
        "problem": "Hoje nao ha autenticacao stateless na API",
        "business_priority": {"level": "high", "set_by": "user"},
        "requirements": [requirement("REQ-001", "Gerar access token valido"),
                         requirement("REQ-002", "Validar assinatura e expiracao do token"),
                         requirement("REQ-003", "Rejeitar tokens invalidos com erro padronizado")],
        "business_rules": [],
        "scope": {"included": ["modulo auth"], "excluded": ["refresh token"]},
        "architectural_decisions": [{"id": "ADR-001", "version": 1}],
        "dependencies": {}, "constraints": [],
        "risks": [{"id": "RISK-1", "description": "Algoritmo de assinatura mal escolhido", "severity": "high",
                   "mitigation": "Seguir a decisao arquitetural ADR-001"},
                  {"id": "RISK-2", "description": "Regressao nas rotas protegidas", "severity": "medium"}],
        "acceptance_criteria": [
            {"id": "AC-F1", "description": "Token valido e aceito pela API", "requirement_ids": ["REQ-001"], "verification": "automated_test"},
            {"id": "AC-F2", "description": "Token expirado e rejeitado", "requirement_ids": ["REQ-002"], "verification": "automated_test"},
            {"id": "AC-F3", "description": "Erro padronizado para token invalido", "requirement_ids": ["REQ-003"], "verification": "automated_test"}],
        "task_plan": [{"task_id": "T-001", "contract_version": 1, "role": "backend"},
                      {"task_id": "T-002", "contract_version": 1, "role": "backend", "depends_on": ["T-001"]},
                      {"task_id": "T-003", "contract_version": 1, "role": "backend", "depends_on": ["T-002"]}],
        "tests": {"integration_required": True, "regression_required": True},
        "rtm": [{"requirement_id": "REQ-001", "requirement_version": 1, "task_ids": ["T-001"], "criterion_ids": ["AC-1"]},
                {"requirement_id": "REQ-002", "requirement_version": 1, "task_ids": ["T-002"], "criterion_ids": ["AC-2"]},
                {"requirement_id": "REQ-003", "requirement_version": 1, "task_ids": ["T-003"], "criterion_ids": ["AC-3"]}],
        "approval": {"plan": {"status": "approved", "granularity": "feature", "approved_by": "user", "approved_at": ts(9)}},
        "state": {"status": "in_execution"},
        "audit": {"created_by": "orchestrator", "created_at": T0},
    }


def blueprint():
    r1, r2, r3 = ["REQ-001"], ["REQ-002"], ["REQ-003"]
    return {
        "schema_version": "0.1.0", "blueprint_id": "BP-001", "contract_version": 1,
        "feature_id": "FEAT-001", "feature_contract_version": 1,
        "title": "Desenho tecnico da autenticacao JWT", "summary": "Servico de autenticacao que emite e valida JWT RS256.",
        "architecture": {
            "components": [
                {"id": "C-API", "name": "API de autenticacao", "kind": "service", "responsibility": "Emitir e validar tokens", "owner_role": "backend", "requirement_ids": ["REQ-001", "REQ-002", "REQ-003"]},
                {"id": "C-DB", "name": "Banco de usuarios", "kind": "datastore", "responsibility": "Guardar usuarios e chaves publicas", "owner_role": "database", "requirement_ids": r1}],
            "interactions": [{"id": "I-1", "from": "C-API", "to": "C-DB", "protocol": "sql", "description": "Le usuarios", "authenticated": True}],
            "decisions": [{"id": "ADR-001", "version": 1}]},
        "backend": {"endpoints": [
            {"id": "EP-1", "component_id": "C-API", "method": "POST", "path": "/auth/token", "auth": "none", "errors": [{"status": 400, "code": "invalid_request"}], "requirement_ids": r1},
            {"id": "EP-2", "component_id": "C-API", "method": "GET", "path": "/auth/verify", "auth": "authenticated",
             "errors": [{"status": 401, "code": "invalid_token"}], "requirement_ids": ["REQ-002", "REQ-003"]}]},
        "database": {
            "entities": [{"id": "ENT-USER", "name": "users", "data_class": "restricted", "requirement_ids": r1, "fields": [
                {"name": "id", "type": "uuid", "primary_key": True}, {"name": "email", "type": "text", "pii": True},
                {"name": "password_hash", "type": "text", "secret": True}]}],
            "migrations": [{"id": "MIG-1", "description": "Cria tabela users", "entity_ids": ["ENT-USER"], "destructive": False, "reversible": True, "rollback": "DROP TABLE users (tabela nova, sem dados)"}]},
        "security": {"threats": [{"id": "TH-1", "description": "Token forjado", "severity": "high", "mitigation": "Assinatura RS256 e validacao de expiracao", "component_ids": ["C-API"]}],
                     "secrets_handling": "Chave privada fora do repositorio; nunca em log (T3)."},
        "devops": {"environments": ["dev"], "rollback": "Reverter o commit e a migracao MIG-1"},
        "test_strategy": {"levels": [{"level": "unit", "covers": ["REQ-001", "REQ-002", "REQ-003"]}]},
        "approval": {"status": "pending"}, "state": {"status": "proposed"},
        "audit": {"created_by": "orchestrator", "created_at": ts(7)}}


def authorization():
    return {
        "schema_version": "0.1.0", "kind": "scope", "authorization_id": "AUTH-1", "project_id": "PRJ-1",
        "feature_id": "FEAT-001", "cycle": 1, "environment": "dev", "resources": ["db_schema"],
        "operations": ["edit_files", "create_table"], "excludes_destructive_operations": True,
        "limits": {"max_operations": 100},
        "validity": {"valid_from": ts(9), "valid_until": "2026-11-06T14:00:00-03:00"},
        "termination_condition": ["expiry", "feature_accepted"],
        "stop_conditions": ["scope_exceeded", "environment_changed", "unexpected_risk",
                            "architectural_decision_needed", "mandatory_approval_needed"],
        "policy_version": "0.1.0", "status": "active", "granted_by": "user", "granted_at": ts(9), "revocable": True,
        "history": [{"event": "granted", "at": ts(9), "by": "user"}],
    }


def report_t001():
    return {
        "schema_version": "0.1.0", "report_id": "RPT-001", "task_id": "T-001", "contract_version": 1,
        "agent": {"agent_id": "backend-1", "agent_contract_version": 1, "role": "backend"},
        "status": "executed",
        "timing": {"started_at": ts(10), "finished_at": ts(25)},
        "attempts": {"fix_attempts_used": 1, "specialist_consultations_used": 0},
        "files": {"created": [{"path": "src/auth/jwt.py"}], "modified": [], "deleted": []},
        "changes": [{"summary": "Geracao de access token", "reason": "REQ-001"}],
        "tests": {"executed": 6, "passed": 6, "failed": 0, "skipped": 0},
        "evidence": [{"id": "EV-1", "type": "test_output", "ref": "evidence/EV-1.txt", "secrets_redacted": True}],
        "criteria_results": [{"criterion_id": "AC-1", "required": True, "result": "met", "evidence_ids": ["EV-1"]}],
        "problems": [], "risks": [], "pending": [], "limitations": [],
        "intervention": {"needed": False},
        "technical_report": {"ref": "reports/RPT-001.md", "sha256": "a" * 64},
        "integrity": {"created_at": ts(25), "event_log_ref": "events/T-001"},
    }


def approval_common(request_id, rtype, status, **extra):
    d = {
        "schema_version": "0.1.0", "request_id": request_id, "request_type": rtype, "status": status,
        "title": "Pedido de aprovacao " + request_id,
        "summary": "Resumo em linguagem direta do que sera feito, por que, e o que muda ao aprovar.",
        "requested_by": {"type": "orchestrator", "id": "orq"},
        "project_id": "PRJ-1", "feature_id": "FEAT-001",
        "created_at": ts(6), "expires_at": "2026-11-06T14:00:00-03:00",
        "presented": {"impact": "Impacto descrito com detalhe suficiente", "evidence_ids": ["EV-1"]},
        "risk": {"level": "medium", "items": []},
        "blocks": {"blocked_task_ids": [], "independent_work_continues": True},
        "policy_version": "0.1.0", "audit": {"requested_event_ref": "events/6"},
    }
    d.update(extra)
    return d


def approvals():
    arch = approval_common(
        "APR-000", "architecture_decision", "approved", title="Algoritmo de assinatura do JWT",
        options=[{"option_id": "OPT-A", "label": "RS256", "description": "Assinatura assimetrica com chave publica",
                  "impacts": ["gestao de chaves"], "risks": ["rotacao de chaves"]},
                 {"option_id": "OPT-B", "label": "HS256", "description": "Segredo compartilhado simetrico",
                  "impacts": ["mais simples"], "risks": ["segredo compartilhado entre servicos"]}],
        recommendation={"option_id": "OPT-A", "rationale": "Permite validar tokens sem expor a chave de assinatura."},
        decision={"choice": "select_option", "selected_option_id": "OPT-A", "decided_by": "user", "decided_at": ts(8)},
        resulting_ref={"kind": "architectural_decision", "id": "ADR-001", "version": 1})
    arch["audit"]["requested_event_ref"] = "events/2"
    arch["audit"]["decided_event_ref"] = "events/3"
    pend = approval_common(
        "APR-001", "scope_authorization", "pending", title="Escopo de trabalho em dev para a T-003",
        scope_proposal={"environment": "dev", "resources": ["db_schema"], "operations": ["create_table"],
                        "valid_until": "2026-11-06T14:00:00-03:00"},
        task_id="T-003", blocks={"blocked_task_ids": ["T-003"], "independent_work_continues": True},
        created_at=ts(40), audit={"requested_event_ref": "events/10"},
        risk={"level": "medium", "items": [{"description": "Cria tabela de sessoes", "severity": "medium",
                                              "mitigation": "Somente em dev, com rollback por migration"}]})
    return [arch, pend]


def build_log(project, signer):
    base = {"schema_version": "0.1.0", "log_id": "PRJ-1", "project_id": "PRJ-1"}
    actor = lambda t, i: {"type": t, "id": i}
    steps = [
        (0, "E0", "genesis", actor("system", "aisef"), "Log criado", {}),
        (1, "E1", "contract_created", actor("orchestrator", "orq"), "Feature Contract FEAT-001 criado",
         {"feature_id": "FEAT-001", "subject": {"kind": "feature_contract", "id": "FEAT-001", "version": 1}}),
        (6, "E2", "approval_requested", actor("orchestrator", "orq"), "Decisao de algoritmo de assinatura aguardando o usuario",
         {"feature_id": "FEAT-001"}),
        (8, "E3", "decision_recorded", actor("user", "usuario"), "Decisao ADR-001: RS256 para assinatura do JWT",
         {"feature_id": "FEAT-001", "subject": {"kind": "architectural_decision", "id": "ADR-001", "version": 1}}),
        (9, "E4", "approval_granted", actor("user", "usuario"), "Plano da FEAT-001 aprovado",
         {"feature_id": "FEAT-001"}),
        (10, "E5", "task_started", actor("agent", "backend-1"), "T-001 iniciada", {"feature_id": "FEAT-001", "task_id": "T-001"}),
        (25, "E6", "task_executed", actor("agent", "backend-1"), "T-001 executada", {"feature_id": "FEAT-001", "task_id": "T-001"}),
        (30, "E7", "task_validated", actor("validator", "validator-1"), "T-001 validada: criterios atendidos",
         {"feature_id": "FEAT-001", "task_id": "T-001"}),
        (32, "E8", "task_completed", actor("orchestrator", "orq"), "T-001 concluida", {"feature_id": "FEAT-001", "task_id": "T-001"}),
        (35, "E9", "task_started", actor("agent", "backend-1"), "T-002 iniciada", {"feature_id": "FEAT-001", "task_id": "T-002"}),
        (40, "E10", "approval_requested", actor("orchestrator", "orq"), "Escopo para T-003 aguardando aprovacao",
         {"feature_id": "FEAT-001", "task_id": "T-003"}),
    ]
    log = []
    for minute, eid, etype, act, summary, extra in steps:
        signer.append(log, {**base, "event_id": eid, "timestamp": ts(minute), "event_type": etype,
                            "actor": act, "summary": summary, **extra})
    return log


def make(dest):
    signer = audit_signing.AuditSigner("audit-key-1")
    write(os.path.join(dest, "contracts/features/FEAT-001.json"), feature())
    write(os.path.join(dest, "contracts/tasks/T-001.json"), task("T-001", "Gerar access token", "completed", [], "REQ-001", "AC-1"))
    write(os.path.join(dest, "contracts/tasks/T-002.json"), task("T-002", "Validar assinatura e expiracao", "in_progress", ["T-001"], "REQ-002", "AC-2"))
    write(os.path.join(dest, "contracts/tasks/T-003.json"), task("T-003", "Rejeitar tokens invalidos", "ready", ["T-002"], "REQ-003", "AC-3"))
    write(os.path.join(dest, "blueprints/BP-001.json"), blueprint())
    write(os.path.join(dest, "contracts/agents/backend-1.json"), agent("backend-1", "Agente Backend", "backend"))
    write(os.path.join(dest, "contracts/agents/validator-1.json"), agent("validator-1", "Agente Validador", "validator", ["backend"]))
    for a in approvals():
        write(os.path.join(dest, "approvals/%s.json" % a["request_id"]), a)
    write(os.path.join(dest, "authorizations/AUTH-1.json"), authorization())
    write(os.path.join(dest, "reports/RPT-001.json"), report_t001())
    log = build_log(dest, signer)
    os.makedirs(os.path.join(dest, "audit"), exist_ok=True)
    with open(os.path.join(dest, "audit/log.jsonl"), "w", encoding="utf-8") as fh:
        for ev in log:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
    write(os.path.join(dest, "audit/head.json"), signer.head)
    os.makedirs(os.path.join(dest, "keys"), exist_ok=True)
    with open(os.path.join(dest, "keys/audit-key-1.pem"), "wb") as fh:
        fh.write(signer.public_key_pem())
    return dest


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    print("projeto de demonstracao criado em", make(sys.argv[1]))
