#!/usr/bin/env python3
"""Testes do schema approval-request.v0.1. Uso: python3 -I test_approval_request.py <schema.json>"""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import userlibs  # noqa: E402,F401
import jsonschema  # noqa: E402

schema = json.load(open(sys.argv[1], encoding="utf-8"))
jsonschema.Draft202012Validator.check_schema(schema)
print("approval-request schema: valido (Draft 2020-12)")
v = jsonschema.Draft202012Validator(schema)
ok = lambda d: not list(v.iter_errors(d))

T = "2026-11-05T22:30:00-03:00"
EXP = "2026-11-05T23:00:00-03:00"


def base(rtype, **extra):
    d = {
        "schema_version": "0.1.0", "request_id": "APR-001", "request_type": rtype, "status": "pending",
        "title": "Pedido de aprovacao de teste", "summary": "Resumo em linguagem direta do que sera feito e por que.",
        "requested_by": {"type": "orchestrator", "id": "orq"},
        "project_id": "PRJ-1", "feature_id": "FEAT-001", "task_id": "T-001",
        "created_at": T, "expires_at": EXP,
        "presented": {"impact": "Impacto descrito em detalhe suficiente", "evidence_ids": ["EV-1"]},
        "risk": {"level": "medium", "items": []},
        "blocks": {"blocked_task_ids": ["T-001"], "independent_work_continues": True},
        "policy_version": "0.1.0", "audit": {"requested_event_ref": "events/10"},
    }
    d.update(extra)
    return d


REINFORCED_PRESENTED = {"impact": "Adiciona coluna nullable em users", "rollback_plan": "Migration 0042 down remove a coluna",
                        "justification": "Necessario para REQ-001", "diff_ref": "diffs/0042.sql", "evidence_ids": ["EV-1"]}
OP_PROD = {"environment": "prod", "resource_class": "db_schema", "operation": "apply migration 0042",
           "destructive": False, "sensitive_content_shown": False}
ACKS = ["impact_read", "rollback_read", "diff_reviewed"]

samples = {
    "plan_approval": base("plan_approval", plan={"granularity": "feature", "task_plan_ref": "plans/FEAT-001", "requirements_count": 3, "tasks_count": 7}),
    "scope_authorization": base("scope_authorization", scope_proposal={"environment": "dev", "resources": ["repo_code", "db_schema"], "operations": ["create_table"], "valid_until": "2026-11-06T22:30:00-03:00"}),
    "operation_approval": base("operation_approval", operation={"environment": "dev", "resource_class": "sensitive_files", "operation": "read .env (nome apenas)", "destructive": False, "sensitive_content_shown": False}),
    "reinforced_approval": base("reinforced_approval", operation=OP_PROD, presented=REINFORCED_PRESENTED, validity_minutes=30,
                                required_acknowledgements=ACKS, risk={"level": "high", "items": []}),
    "git_operation": base("git_operation", git={"operation": "commit", "branch": "feat/auth", "covers_only_this_operation": True},
                          operation={"environment": "dev", "resource_class": "git", "operation": "git commit", "destructive": False, "sensitive_content_shown": False}),
    "architecture_decision": base("architecture_decision",
        options=[{"option_id": "OPT-A", "label": "Manter", "description": "Manter a arquitetura atual", "impacts": ["baixo"], "risks": ["limite futuro"]},
                 {"option_id": "OPT-B", "label": "Alterar", "description": "Migrar para o novo modelo", "impacts": ["alto"], "risks": ["migracao"]}],
        recommendation={"option_id": "OPT-A", "rationale": "A arquitetura atual comporta a necessidade sem migracao."}),
    "scope_change_decision": base("scope_change_decision",
        options=[{"option_id": "OPT-A", "label": "Incluir", "description": "Incluir no escopo", "impacts": ["prazo"], "risks": ["regressao"]},
                 {"option_id": "OPT-B", "label": "Adiar", "description": "Tratar em nova feature", "impacts": ["nenhum"], "risks": ["atraso"]}],
        recommendation={"option_id": "OPT-B", "rationale": "Evita alterar o escopo aprovado no meio da execucao."}),
    "feature_acceptance": base("feature_acceptance", acceptance_summary={"final_report_ref": "reports/FEAT-001.md", "requirements_met": 3, "requirements_not_met": 0,
                               "tests_passed": 40, "tests_failed": 0, "pending_items": [], "git_operations_authorized": False}),
}

results = []


def check(label, cond):
    results.append(cond)
    print(("OK   " if cond else "FALHA"), label)


for name, doc in samples.items():
    check("pedido valido aceito: " + name, ok(doc))


def bad(label, name, fn):
    d = copy.deepcopy(samples[name]); fn(d)
    check(label, not ok(d))


print("--- conteudo por tipo")
bad("plan_approval sem plano rejeitado", "plan_approval", lambda d: d.pop("plan"))
bad("scope_authorization sem proposta rejeitado", "scope_authorization", lambda d: d.pop("scope_proposal"))
bad("proposta de escopo em producao rejeitada", "scope_authorization", lambda d: d["scope_proposal"].__setitem__("environment", "prod"))
bad("operation_approval sem operacao rejeitado", "operation_approval", lambda d: d.pop("operation"))
bad("operation_approval em producao sem 'access' rejeitado", "operation_approval", lambda d: d["operation"].__setitem__("environment", "prod"))
bad("operation_approval em producao para arquivo sensivel rejeitado (so reforcada)", "operation_approval", lambda d: d["operation"].update({"environment": "prod", "access": "read"}))
bad("operation_approval em producao com escrita rejeitado (so reforcada)", "operation_approval", lambda d: d["operation"].update({"environment": "prod", "resource_class": "db_schema", "access": "write"}))
bad("operation_approval em producao com execucao rejeitado (so reforcada)", "operation_approval", lambda d: d["operation"].update({"environment": "prod", "resource_class": "deploy_infra", "access": "execute"}))
bad("operation_approval em producao destrutiva rejeitado", "operation_approval", lambda d: d["operation"].update({"environment": "prod", "resource_class": "db_schema", "access": "read", "destructive": True}))
d = copy.deepcopy(samples["operation_approval"])
d["operation"].update({"environment": "prod", "resource_class": "db_schema", "operation": "ler schema de producao", "access": "read"})
check("operation_approval em producao: leitura de db_schema aceita", ok(d))
d["operation"].update({"resource_class": "repo_code", "operation": "ler codigo implantado em producao"})
check("operation_approval em producao: leitura de repo_code aceita", ok(d))
bad("operation_approval de Git rejeitado (Git tem tipo proprio)", "operation_approval", lambda d: d["operation"].__setitem__("resource_class", "git"))
bad("operation_approval destrutiva em staging rejeitada (T1)", "operation_approval", lambda d: d["operation"].update({"environment": "staging", "destructive": True}))
d = copy.deepcopy(samples["operation_approval"]); d["operation"]["destructive"] = True
check("operation_approval destrutiva em dev aceita (T1: por operacao)", ok(d))
bad("conteudo de segredo exibido rejeitado", "operation_approval", lambda d: d["operation"].__setitem__("sensitive_content_shown", True))
bad("reforcada sem rollback rejeitada", "reinforced_approval", lambda d: d["presented"].pop("rollback_plan"))
bad("reforcada sem diff rejeitada", "reinforced_approval", lambda d: d["presented"].pop("diff_ref"))
bad("reforcada sem justificativa rejeitada", "reinforced_approval", lambda d: d["presented"].pop("justification"))
bad("reforcada com validade acima de 30 min rejeitada", "reinforced_approval", lambda d: d.__setitem__("validity_minutes", 45))
bad("reforcada sem as 3 confirmacoes exigidas rejeitada", "reinforced_approval", lambda d: d.__setitem__("required_acknowledgements", ["impact_read"]))
bad("reforcada marcada como risco baixo rejeitada", "reinforced_approval", lambda d: d["risk"].__setitem__("level", "low"))
bad("git_operation sem bloco git rejeitada", "git_operation", lambda d: d.pop("git"))
bad("git_operation com recurso nao-git rejeitada", "git_operation", lambda d: d["operation"].__setitem__("resource_class", "repo_code"))
bad("git que cobre mais de uma operacao rejeitado", "git_operation", lambda d: d["git"].__setitem__("covers_only_this_operation", False))
bad("git force_push sem rollback/diff/confirmacoes rejeitado", "git_operation", lambda d: d["git"].__setitem__("operation", "force_push"))
d = copy.deepcopy(samples["git_operation"])
d["git"]["operation"] = "force_push"; d["validity_minutes"] = 30; d["required_acknowledgements"] = ACKS
d["presented"] = REINFORCED_PRESENTED; d["operation"]["destructive"] = True
check("git force_push completo aceito", ok(d))
d["operation"]["destructive"] = False
check("git force_push marcado como nao destrutivo rejeitado", not ok(d))
d = copy.deepcopy(samples["git_operation"])
d["git"]["operation"] = "pull_request"; d["operation"]["operation"] = "gh pr create --base main --head feat/x"
check("git pull_request (abrir PR) aceito como operacao nao destrutiva, sem confirmacoes reforcadas", ok(d))
bad("git com operacao desconhecida rejeitado", "git_operation", lambda d: d["git"].__setitem__("operation", "open_pr"))
bad("decisao arquitetural com 1 opcao rejeitada", "architecture_decision", lambda d: d["options"].pop())
bad("decisao arquitetural sem recomendacao rejeitada", "architecture_decision", lambda d: d.pop("recommendation"))
bad("mudanca de escopo sem opcoes rejeitada", "scope_change_decision", lambda d: d.pop("options"))
bad("aceite de feature sem relatorio final rejeitado", "feature_acceptance", lambda d: d.pop("acceptance_summary"))
bad("aceite de feature autorizando git rejeitado", "feature_acceptance", lambda d: d["acceptance_summary"].__setitem__("git_operations_authorized", True))

print("--- ciclo de vida e decisao")
for st in ("approved", "rejected", "changes_requested"):
    bad("%s sem decisao rejeitado" % st, "plan_approval", lambda d, st=st: d.__setitem__("status", st))
d = copy.deepcopy(samples["plan_approval"])
d["status"] = "approved"
d["decision"] = {"choice": "approve", "decided_by": "user", "decided_at": T}
d["audit"]["decided_event_ref"] = "events/11"
check("plano aprovado pelo usuario aceito", ok(d))
x = copy.deepcopy(d); x["decision"]["decided_by"] = "orchestrator"
check("decisao por quem nao e o usuario rejeitada", not ok(x))
x = copy.deepcopy(d); del x["audit"]["decided_event_ref"]
check("decisao sem evento de auditoria rejeitada", not ok(x))
x = copy.deepcopy(d); x["decision"]["choice"] = "reject"
check("aprovado com escolha 'reject' rejeitado", not ok(x))
x = copy.deepcopy(d); x["status"] = "rejected"; x["decision"]["choice"] = "reject"
check("rejeitado com escolha 'reject' aceito", ok(x))
x["resulting_ref"] = {"kind": "feature_contract", "id": "FEAT-001", "version": 2}
check("rejeitado gerando artefato rejeitado", not ok(x))
x = copy.deepcopy(d); x["status"] = "changes_requested"; x["decision"]["choice"] = "request_changes"
check("alteracoes solicitadas aceitas", ok(x))
x = copy.deepcopy(samples["plan_approval"]); x["decision"] = {"choice": "approve", "decided_by": "user", "decided_at": T}
check("pendente com decisao rejeitado", not ok(x))
for st in ("expired", "withdrawn"):
    x = copy.deepcopy(samples["plan_approval"]); x["status"] = st
    check("%s sem decisao aceito" % st, ok(x))
x = copy.deepcopy(samples["plan_approval"]); x["status"] = "superseded"
check("substituido sem indicar o substituto rejeitado", not ok(x))
x["superseded_by"] = "APR-002"
check("substituido indicando o substituto aceito", ok(x))
x = copy.deepcopy(d); x["decision"]["choice"] = "select_option"; x["decision"]["selected_option_id"] = "OPT-A"
check("plano aprovado com 'select_option' rejeitado", not ok(x))

arch = copy.deepcopy(samples["architecture_decision"])
arch["status"] = "approved"; arch["audit"]["decided_event_ref"] = "events/12"
arch["decision"] = {"choice": "select_option", "selected_option_id": "OPT-A", "decided_by": "user", "decided_at": T}
check("decisao arquitetural com opcao escolhida aceita", ok(arch))
x = copy.deepcopy(arch); x["decision"]["choice"] = "approve"
check("decisao arquitetural aprovada sem escolher opcao rejeitada", not ok(x))
x = copy.deepcopy(arch); del x["decision"]["selected_option_id"]
check("select_option sem option_id rejeitado", not ok(x))

scope = copy.deepcopy(samples["scope_authorization"])
scope["status"] = "approved"; scope["audit"]["decided_event_ref"] = "events/13"
scope["decision"] = {"choice": "approve", "decided_by": "user", "decided_at": T}
check("escopo aprovado sem autorizacao gerada rejeitado", not ok(scope))
scope["resulting_ref"] = {"kind": "scope_authorization", "id": "AUTH-1"}
check("escopo aprovado com autorizacao gerada aceito", ok(scope))

rein = copy.deepcopy(samples["reinforced_approval"])
rein["status"] = "approved"; rein["audit"]["decided_event_ref"] = "events/14"
rein["decision"] = {"choice": "approve", "decided_by": "user", "decided_at": T, "acknowledged": ["impact_read", "rollback_read"]}
rein["resulting_ref"] = {"kind": "reinforced_approval", "id": "APR-R1"}
check("reforcada aprovada sem todas as confirmacoes rejeitada", not ok(rein))
rein["decision"]["acknowledged"] = ACKS
check("reforcada aprovada com todas as confirmacoes aceita", ok(rein))
x = copy.deepcopy(rein); del x["decision"]["acknowledged"]
check("reforcada aprovada sem lista de confirmacoes rejeitada", not ok(x))
x = copy.deepcopy(rein); x["status"] = "rejected"; x["decision"] = {"choice": "reject", "decided_by": "user", "decided_at": T}; del x["resulting_ref"]
check("reforcada recusada sem confirmacoes aceita (recusar nao exige)", ok(x))

n_fail = results.count(False)
print("\n%d verificacoes, %d falhas" % (len(results), n_fail))
sys.exit(0 if n_fail == 0 else 1)
