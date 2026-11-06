#!/usr/bin/env python3
"""Testes de mutacao do check_project: cada mutacao quebra UMA coisa e exige o codigo de regra esperado."""
import copy, json, os, shutil, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_demo_project as demo
import check_project as cp

POL = os.path.join(HERE, "permission-policy.v0.1.json")
DEF = os.path.join(HERE, "orchestration-defaults.v0.1.json")
NOW = "2026-01-01T00:00:00+00:00"
fails = 0; total = 0


def run(mut=None):
    d = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
    try:
        proj = os.path.join(d, "p"); demo.make(proj)
        if mut: mut(proj)
        return cp.check(proj, HERE, POL, DEF, NOW)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def edit(rel, fn):
    def m(proj):
        p = os.path.join(proj, rel)
        with open(p, encoding="utf-8") as fh: d = json.load(fh)
        fn(d)
        with open(p, "w", encoding="utf-8") as fh: json.dump(d, fh)
    return m


def both(*ms):
    return lambda proj: [m(proj) for m in ms]


def expect(name, mut, code):
    global fails, total
    total += 1
    codes = run(mut).codes()
    ok = code in codes
    print(("OK    " if ok else "FALHA ") + name + ("" if ok else "  (esperado %s, veio %s)" % (code, sorted(codes))))
    fails += not ok


total += 1
r = run()
if r.findings:
    fails += 1; print("FALHA baseline limpo:", r.findings)
else:
    print("OK    baseline: 0 erros, 0 avisos")

def dup_blueprint(p):
    shutil.copy(os.path.join(p, "blueprints/BP-001.json"), os.path.join(p, "blueprints/BP-002.json"))
    edit("blueprints/BP-002.json", lambda d: d.update(blueprint_id="BP-002"))(p)

F = "contracts/features/FEAT-001.json"; T1 = "contracts/tasks/T-001.json"; T2 = "contracts/tasks/T-002.json"
A = "contracts/agents/backend-1.json"; V = "contracts/agents/validator-1.json"

def rename(rel, new):
    def m(proj): os.rename(os.path.join(proj, rel), os.path.join(proj, new))
    return m

def log_edit(fn):
    def m(proj):
        p = os.path.join(proj, "audit/log.jsonl")
        ev = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        fn(ev)
        open(p, "w", encoding="utf-8").write("\n".join(json.dumps(e) for e in ev) + "\n")
    return m

expect("schema invalido", edit(T1, lambda d: d.pop("objective")), "SCHEMA")
expect("arquivo com nome diferente do id", rename(T2, "contracts/tasks/T-099.json"), "ID-FILE")
expect("requisito: historico incompativel", edit(F, lambda d: d["requirements"][0].update(version=d["requirements"][0]["version"] + 1)), "REQ-HISTORY")
expect("plano cita tarefa inexistente", edit(F, lambda d: d["task_plan"].append(dict(copy.deepcopy(d["task_plan"][0]), task_id="T-404"))), "PLAN-TASK-MISSING")
expect("plano com versao errada", edit(F, lambda d: d["task_plan"][0].update(contract_version=7)), "PLAN-VERSION")
expect("tarefa emitida para outra versao da feature", edit(T1, lambda d: d.update(feature_contract_version=9)), "PLAN-FEATURE-VERSION")
expect("dependencias do plano divergem", edit(F, lambda d: d["task_plan"][0].update(depends_on=["T-002"])), "PLAN-DEPS")
expect("tarefa fora do plano", edit(F, lambda d: d["task_plan"].pop()), "PLAN-ORPHAN-TASK")
expect("RTM sem requisito ativo", edit(F, lambda d: d["rtm"].pop()), "RTM-MISSING")
expect("RTM com versao errada", edit(F, lambda d: d["rtm"][0].update(requirement_version=5)), "RTM-VERSION")
expect("RTM cita tarefa inexistente", edit(F, lambda d: d["rtm"][0]["task_ids"].append("T-404")), "RTM-TASK-MISSING")
expect("RTM cita criterio inexistente", edit(F, lambda d: d["rtm"][0]["criterion_ids"].append("AC-404")), "RTM-CRITERION-UNKNOWN")
expect("criterio da feature cita requisito inexistente", edit(F, lambda d: d["acceptance_criteria"][0]["requirement_ids"].append("REQ-404")), "FEAT-CRITERION-REQ")
expect("decisao arquitetural sem aprovacao", edit(F, lambda d: d["architectural_decisions"].append({"id": "ADR-404", "version": 1})), "FEAT-ARCH-UNKNOWN")
expect("tarefa usa requisito em versao antiga", edit(T1, lambda d: d["requirements"]["requirement_ids"][0].update(version=9)), "TASK-REQ-VERSION")
expect("dependencia inexistente", edit(T2, lambda d: d["dependencies"]["depends_on"].append("T-404")), "DEP-UNKNOWN")
expect("ciclo de dependencias", both(edit(T1, lambda d: d["dependencies"].update(depends_on=["T-002"])), edit(T2, lambda d: d["dependencies"].update(depends_on=["T-001"]))), "DEP-CYCLE")
expect("agente inexistente", edit(T1, lambda d: d["assigned_agent"].update(agent_id="ghost")), "AGENT-UNKNOWN")
expect("versao do agente desatualizada", edit(T1, lambda d: d["assigned_agent"].update(agent_contract_version=9)), "AGENT-VERSION")
expect("ambiente acima do teto do agente", edit(T2, lambda d: d["permissions"].update(environment="staging")), "AGENT-ENV")
expect("recurso fora do teto do agente", edit(T2, lambda d: d["permissions"].update(resources=["deploy_infra"])), "AGENT-RESOURCE")
expect("sem validador independente", edit(V, lambda d: d.update(status="suspended")), "VAL-NO-VALIDATOR")
expect("recurso exige escopo e tarefa nao tem", edit(T1, lambda d: d["permissions"].update(scope_authorization_id=None)), "PERM-SCOPE-REQUIRED")
expect("autorizacao inexistente", edit(T1, lambda d: d["permissions"].update(scope_authorization_id="AUTH-404")), "AUTH-MISSING")
expect("autorizacao nao cobre o recurso", edit("authorizations/AUTH-1.json", lambda d: d.update(resources=["config_ci_iac"])), "AUTH-RESOURCE")
expect("autorizacao expirada e ativa", edit("authorizations/AUTH-1.json", lambda d: d["validity"].update(valid_until="2025-01-01T00:00:00+00:00")), "AUTH-EXPIRED")
expect("concluida sem relatorio", both(lambda p: os.remove(os.path.join(p, "reports/RPT-001.json"))), "STATE-NO-REPORT")
expect("sem evento de validacao", log_edit(lambda ev: [e.update(event_type="task_executed") for e in ev if e["event_type"] == "task_validated"]), "STATE-NO-VALIDATION")
expect("executor valida a propria entrega", log_edit(lambda ev: [e["actor"].update(id="backend-1") for e in ev if e["event_type"] == "task_validated"]), "VAL-SELF-ATTEST")
expect("relatorio de versao antiga", edit("reports/RPT-001.json", lambda d: d.update(contract_version=9)), "REPORT-VERSION")
expect("relatorio sem criterio do contrato", edit(T1, lambda d: d["acceptance_criteria"].append(dict(d["acceptance_criteria"][0], id="AC-NEW"))), "REPORT-CRITERIA-MISSING")
expect("relatorio altera arquivo fora do escopo", edit("reports/RPT-001.json", lambda d: d["files"]["modified"].append({"path": "infra/prod.tf"})), "REPORT-FILE-OUT-OF-SCOPE")
expect("tentativas acima do limite", edit("reports/RPT-001.json", lambda d: d["attempts"].update(fix_attempts_used=4)), "REPORT-ATTEMPTS")
expect("aprovacao aponta evento inexistente", edit("approvals/APR-001.json", lambda d: d["audit"].update(requested_event_ref="events/99")), "APPROVAL-EVENT-REF")
expect("aprovacao pendente expirada", edit("approvals/APR-001.json", lambda d: d.update(expires_at="2025-01-01T00:00:00+00:00")), "APPROVAL-EXPIRED-PENDING")
expect("decisao de aprovacao por agente", log_edit(lambda ev: [e["actor"].update(type="agent", id="backend-1") for e in ev if e["event_type"] == "decision_recorded"]), "APPROVAL-DECIDER")
expect("log fora de ordem no tempo", log_edit(lambda ev: ev[3].update(timestamp="2000-01-01T00:00:00+00:00")), "LOG-TIME-ORDER")
expect("log cita tarefa inexistente", log_edit(lambda ev: [e.update(task_id="T-404") for e in ev if e.get("task_id") == "T-002"]), "LOG-UNKNOWN-TASK")
expect("feature encerrada sem aceite", edit(F, lambda d: (d["state"].update(status="closed"), d.__setitem__("approval", dict(d["approval"], acceptance={"status": "accepted", "approved_by": "user", "approved_at": "2025-12-01T00:00:00+00:00", "final_report_ref": "reports/final.md", "git_operations_authorized": False})))), "STATE-CLOSED-NO-ACCEPT")

B = "blueprints/BP-001.json"
expect("blueprint: feature em outra versao", edit(B, lambda d: d.update(feature_contract_version=9)), "BP-FEATURE-VERSION")
expect("blueprint: requisito inexistente", edit(B, lambda d: d["architecture"]["components"][0]["requirement_ids"].append("REQ-404")), "BP-REQ-UNKNOWN")
expect("blueprint: interacao com componente inexistente", edit(B, lambda d: d["architecture"]["interactions"][0].update(to="C-404")), "BP-COMPONENT-UNKNOWN")
expect("blueprint: endpoint em componente inexistente", edit(B, lambda d: d["backend"]["endpoints"][0].update(component_id="C-404")), "BP-COMPONENT-UNKNOWN")
expect("blueprint: tela chama endpoint inexistente", edit(B, lambda d: d.update(frontend={"screens": [{"id": "S-1", "name": "Login", "route": "/login", "calls_endpoint_ids": ["EP-404"], "requirement_ids": ["REQ-001"]}]})), "BP-ENDPOINT-UNKNOWN")
expect("blueprint: FK para entidade inexistente", edit(B, lambda d: d["database"]["entities"][0]["fields"].append({"name": "org_id", "type": "uuid", "references": {"entity_id": "ENT-404", "field": "id"}})), "BP-ENTITY-UNKNOWN")
expect("blueprint: FK para campo inexistente", edit(B, lambda d: d["database"]["entities"][0]["fields"].append({"name": "org_id", "type": "uuid", "references": {"entity_id": "ENT-USER", "field": "nope"}})), "BP-FIELD-UNKNOWN")
expect("blueprint: migracao de entidade inexistente", edit(B, lambda d: d["database"]["migrations"][0].update(entity_ids=["ENT-404"])), "BP-ENTITY-UNKNOWN")
expect("blueprint: decisao arquitetural sem aprovacao", edit(B, lambda d: d["architecture"]["decisions"].append({"id": "ADR-404", "version": 1})), "BP-ADR-UNAPPROVED")
expect("blueprint: requisito sem elemento no desenho", edit(B, lambda d: (d["architecture"]["components"][0].update(requirement_ids=["REQ-001"]), d["backend"]["endpoints"][1].update(requirement_ids=["REQ-002"]))), "BP-REQ-UNCOVERED")
expect("blueprint: requisito sem teste", edit(B, lambda d: d["test_strategy"]["levels"][0].update(covers=["REQ-001"])), "BP-REQ-UNTESTED")
expect("blueprint: aprovacao aponta pedido inexistente", edit(B, lambda d: (d["approval"].update(status="approved", approved_by="user", approved_at="2026-01-01T00:00:00+00:00", request_ref="APR-404"), d["state"].update(status="approved"))), "BP-APPROVAL-REF")
expect("blueprint: dois vigentes para a feature", dup_blueprint, "BP-MULTIPLE-ACTIVE")

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
