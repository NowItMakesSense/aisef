#!/usr/bin/env python3
"""AISEF: gera documentos validos a partir de um BRIEF curto (economia de tokens).

O modelo escreve so o conteudo que importa num brief JSON de poucas linhas; este script expande para
os contratos completos (campos obrigatorios, RTM, versoes, auditoria), valida contra os schemas e grava.
Ajustes finos depois sao Edits pequenos nos arquivos gerados.

Uso:
    python3 -I aisef_new.py feature   --project REPO --brief brief.json   (Feature Contract + Tasks + pedido de plano)
    python3 -I aisef_new.py blueprint --project REPO --brief brief.json   (Engineering Blueprint + pedido de ADR opcional)
    python3 -I aisef_new.py quick     --project REPO --title "..." --why "..." [--path GLOB ...] [--test-cmd "..."]
                                      (caminho rapido de manutencao, ver skill aisef)
    python3 -I aisef_new.py example feature|blueprint                     (imprime um brief de exemplo)

Brief de feature (so os campos marcados com * sao obrigatorios):
    {"id"*: "FEAT-002", "title"*: "...", "objective"*: "...", "problem"*: "...", "priority": "medium",
     "requirements"*: {"REQ-010": "texto", "REQ-011": {"text": "...", "origin": "investigated", "kind": "non_functional"}},
     "scope_in"*: ["..."], "scope_out": ["..."], "risks": [["descricao", "medium", "mitigacao"]],
     "tasks"*: [{"id": "T-010", "title": "...", "role": "backend", "reqs": ["REQ-010"],
                 "criteria": {"AC-10": "descricao verificavel"}, "paths": ["src/x/*"], "depends_on": [],
                 "test_cmd": "pytest -q", "risk": "low", "resources": ["repo_code"],
                 "complexity": "normal"}]}
    ("complexity": trivial | normal | complex, opcional; entra no Task Contract e alimenta o roteador aisef_route.py)
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_project as ap  # noqa: E402

AGENT_ROLES = {"orchestrator", "backend", "frontend", "database", "qa", "security", "devops", "domain", "validator"}
MAINT_FEATURE = "FEAT-MAINT"
MAINT_REQ = "REQ-MAINT"

EXAMPLES = {
    "feature": {
        "id": "FEAT-002", "title": "Recuperacao de senha", "objective": "Permitir redefinir a senha por e-mail",
        "problem": "Usuarios bloqueados dependem do suporte", "priority": "high",
        "requirements": {"REQ-010": "Enviar link de redefinicao valido por 30 minutos",
                         "REQ-011": "Invalidar o link apos o uso"},
        "scope_in": ["fluxo de redefinicao por e-mail"], "scope_out": ["redefinicao por SMS"],
        "risks": [["Enumeracao de usuarios pela resposta da API", "medium", "Resposta identica para e-mail existente ou nao"]],
        "tasks": [{"id": "T-010", "title": "Emitir token de redefinicao", "role": "backend", "reqs": ["REQ-010"],
                   "criteria": {"AC-10": "Token expira em 30 minutos (teste automatizado)"}, "paths": ["src/auth/*", "tests/auth/*"]},
                  {"id": "T-011", "title": "Consumir e invalidar o token", "role": "backend", "reqs": ["REQ-011"],
                   "criteria": {"AC-11": "Segundo uso do mesmo token e recusado (teste automatizado)"},
                   "paths": ["src/auth/*", "tests/auth/*"], "depends_on": ["T-010"]}]},
    "blueprint": {
        "id": "BP-002", "feature": "FEAT-002", "title": "Desenho da recuperacao de senha",
        "summary": "Endpoint que emite token de uso unico e outro que o consome",
        "components": {"C-AUTH": ["service", "Servico de autenticacao", "Emitir e consumir tokens", "backend", ["REQ-010", "REQ-011"]]},
        "endpoints": [["POST", "/auth/reset", "none", ["REQ-010"]], ["POST", "/auth/reset/confirm", "none", ["REQ-011"]]],
        "entities": {"ENT-RESET": ["password_resets", "restricted", ["REQ-010", "REQ-011"],
                                   [["id", "uuid", "pk"], ["token_hash", "text", "secret"], ["expires_at", "timestamptz"]]]},
        "migrations": [["MIG-10", "Cria password_resets", ["ENT-RESET"], "DROP TABLE password_resets (tabela nova)"]],
        "threats": [["TH-10", "Token adivinhavel", "high", "Token aleatorio de 256 bits, guardado so o hash", ["C-AUTH"]]],
        "tests": {"unit": ["REQ-010", "REQ-011"], "integration": ["REQ-010", "REQ-011"]},
        "environments": ["dev"], "rollback": "Reverter o commit e a migracao MIG-10"},
}


def load_brief(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def need(brief, *keys):
    missing = [k for k in keys if not brief.get(k)]
    if missing:
        raise SystemExit("brief incompleto, faltam: " + ", ".join(missing))


def task_doc(t, feature_id, feature_version, env, now):
    role = t.get("role", "backend")
    if role not in AGENT_ROLES:
        raise SystemExit("papel desconhecido em %s: %s" % (t["id"], role))
    criteria = [{"id": cid, "description": text, "required": True,
                 "verification": {"method": "automated_test", "evidence_expected": "saida do comando de teste",
                                  **({"command": t["test_cmd"]} if t.get("test_cmd") else {})},
                 "requirement_ids": t["reqs"]} for cid, text in t["criteria"].items()]
    doc = {
        "schema_version": "0.1.0", "task_id": t["id"], "contract_version": 1, "kind": "task",
        "feature_id": feature_id, "feature_contract_version": feature_version, "title": t["title"],
        "objective": t.get("objective") or t["title"],
        "assigned_agent": {"agent_id": role, "agent_contract_version": 1, "role": role},
        "requirements": {"requirement_ids": [{"id": r, "version": 1} for r in t["reqs"]]},
        "scope": {"included": t.get("scope_in") or [t["title"]], "excluded": t.get("scope_out", []),
                  **({"paths_allowed": t["paths"]} if t.get("paths") else {})},
        "dependencies": {"depends_on": t.get("depends_on", []), "parallelizable": bool(t.get("parallelizable"))},
        "context": {"mandatory": [{"ref": "contracts/features/%s.json" % feature_id, "origin": "feature_contract",
                                   "version": str(feature_version)}]},
        "permissions": {"environment": env, "scope_authorization_id": t.get("scope_authorization_id"),
                        "resources": t.get("resources", ["repo_code"])},
        "acceptance_criteria": criteria,
        "validation": {"independent_validator_required": t.get("independent_validation", True),
                       "validator_role": t.get("validator_role", "validator")},
        "deliverables": {"execution_report_schema": "execution-report/0.1.0"},
        **({"complexity": t["complexity"]} if t.get("complexity") else {}),
        "risk": {"level": t.get("risk", "low")}, "limits": {"max_fix_attempts": None},
        "escalation": {"stop_and_report_when": ["scope_exceeded", "unexpected_risk", "requirement_conflict",
                                                "max_attempts_reached"]},
        "state": {"status": "draft"},
        "audit": {"created_by": "orchestrator", "created_at": now},
    }
    return doc


def feature_docs(brief, project, now):
    need(brief, "id", "title", "objective", "problem", "requirements", "scope_in", "tasks")
    cfg = ap.load_config(project)
    fid = brief["id"]
    reqs = []
    for rid, spec in brief["requirements"].items():
        spec = {"text": spec} if isinstance(spec, str) else spec
        reqs.append({"id": rid, "version": 1, "kind": spec.get("kind", "functional"), "statement": spec["text"],
                     "origin": spec.get("origin", "user_stated"), "status": "active",
                     "history": [{"version": 1, "statement": spec["text"], "author": "user",
                                  "justification": "criacao", "changed_at": now}]})
    known = {r["id"] for r in reqs}
    tasks = [task_doc(t, fid, 1, cfg.get("environment", "dev"), now) for t in brief["tasks"]]
    for t in brief["tasks"]:
        unknown = set(t["reqs"]) - known
        if unknown:
            raise SystemExit("%s cita requisito inexistente: %s" % (t["id"], ", ".join(sorted(unknown))))
    criteria, rtm = [], []
    for r in reqs:
        task_ids = [t["id"] for t in brief["tasks"] if r["id"] in t["reqs"]]
        crit_ids = [cid for t in brief["tasks"] if r["id"] in t["reqs"] for cid in t["criteria"]]
        if not task_ids:
            raise SystemExit("%s nao tem tarefa: toda exigencia precisa de tarefa e criterio (RTM)" % r["id"])
        rtm.append({"requirement_id": r["id"], "requirement_version": 1, "task_ids": task_ids, "criterion_ids": crit_ids})
    for t in brief["tasks"]:
        for cid, text in t["criteria"].items():
            criteria.append({"id": cid, "description": text, "requirement_ids": t["reqs"], "verification": "automated_test"})
    feature = {
        "schema_version": "0.1.0", "feature_id": fid, "contract_version": 1, "cycle": {"number": 1},
        "title": brief["title"], "objective": brief["objective"], "problem": brief["problem"],
        "business_priority": {"level": brief.get("priority", "medium"), "set_by": "user"},
        "requirements": reqs, "business_rules": [],
        "scope": {"included": brief["scope_in"], "excluded": brief.get("scope_out", [])},
        "architectural_decisions": [], "dependencies": {}, "constraints": [],
        "risks": [{"id": "RISK-%s-%d" % (fid, i + 1), "description": r[0], "severity": r[1],
                   **({"mitigation": r[2]} if len(r) > 2 else {})} for i, r in enumerate(brief.get("risks", []))],
        "acceptance_criteria": criteria,
        "task_plan": [{"task_id": t["id"], "contract_version": 1, "role": t.get("role", "backend"),
                       **({"depends_on": t["depends_on"]} if t.get("depends_on") else {})} for t in brief["tasks"]],
        "tests": {"integration_required": True, "regression_required": True},
        "rtm": rtm,
        "approval": {"plan": {"status": "pending"}},
        "state": {"status": "awaiting_plan_approval"},
        "audit": {"created_by": "orchestrator", "created_at": now},
    }
    return feature, tasks


def plan_request(project, feature, title, summary, now, task_ids):
    cfg = ap.load_config(project)
    n = len([f for f in os.listdir(os.path.join(ap.aisef_dir(project), "approvals")) if f.endswith(".json")]) + 1
    rid = "APR-%03d" % n
    while os.path.exists(os.path.join(ap.aisef_dir(project), "approvals", rid + ".json")):
        n += 1
        rid = "APR-%03d" % n
    return {
        "schema_version": "0.1.0", "request_id": rid, "request_type": "plan_approval", "status": "pending",
        "title": title, "summary": summary,
        "requested_by": {"type": "orchestrator", "id": "orchestrator"},
        "project_id": cfg["project_id"], "feature_id": feature["feature_id"],
        "created_at": now, "expires_at": ap.iso_in(days=7),
        "presented": {"impact": "Plano da feature %s: %d requisito(s), %d tarefa(s). Ver contracts/features/%s.json"
                      % (feature["feature_id"], len(feature["requirements"]), len(task_ids), feature["feature_id"]),
                      "requirement_ids": [r["id"] for r in feature["requirements"]], "evidence_ids": []},
        "risk": {"level": "low", "items": []},
        "blocks": {"blocked_task_ids": task_ids, "independent_work_continues": True},
        "plan": {"granularity": "feature", "task_plan_ref": "contracts/features/%s.json#task_plan" % feature["feature_id"],
                 "requirements_count": len(feature["requirements"]), "tasks_count": len(task_ids)},
        "policy_version": "0.1.0", "audit": {"requested_event_ref": "events/pending"},
    }


def write_all(project, docs, request=None, event_summary=None, feature_id=None):
    """Valida tudo antes de gravar qualquer coisa; grava, registra o evento e liga o pedido ao evento."""
    problems = []
    for rel, doc, schema in docs:
        problems += ["%s: %s" % (rel, p) for p in ap.validate(doc, schema)]
    if request:
        problems += ["pedido: " + p for p in ap.validate(request, "approval-request.schema.v0.1.json")]
    if problems:
        raise SystemExit("nada foi gravado; documento invalido:\n - " + "\n - ".join(problems[:20]))
    root = ap.aisef_dir(project)
    for rel, doc, _schema in docs:
        if os.path.exists(os.path.join(root, rel)):
            raise SystemExit("%s ja existe; para mudar, crie nova versao (nada foi gravado)" % rel)
    for rel, doc, _schema in docs:
        ap.write_json(os.path.join(root, rel), doc)
    partial = {"event_type": "contract_created", "actor": {"type": "orchestrator", "id": "orchestrator"},
               "summary": event_summary}
    if feature_id:
        partial["feature_id"] = feature_id
    ap.append(project, partial)
    if request:
        ev = ap.append(project, {"event_type": "approval_requested", "actor": {"type": "orchestrator", "id": "orchestrator"},
                                 "summary": "%s aguardando decisao" % request["request_id"],
                                 **({"feature_id": request["feature_id"]} if request.get("feature_id") else {})})
        request["audit"]["requested_event_ref"] = "events/%d" % ev["sequence"]
        ap.write_json(os.path.join(root, "approvals", request["request_id"] + ".json"), request)


def cmd_feature(project, brief):
    now = ap.now_iso()
    feature, tasks = feature_docs(brief, project, now)
    request = plan_request(project, feature, "Plano da feature %s: %s" % (feature["feature_id"], feature["title"]),
                           feature["objective"], now, [t["task_id"] for t in tasks])
    docs = [("contracts/features/%s.json" % feature["feature_id"], feature, "feature-contract.schema.v0.1.json")]
    docs += [("contracts/tasks/%s.json" % t["task_id"], t, "task-contract.schema.v0.1.json") for t in tasks]
    write_all(project, docs, request, "Feature Contract %s v1 e %d tarefa(s) criados" % (feature["feature_id"], len(tasks)),
              feature["feature_id"])
    print("criados: %s; pedido de aprovacao do plano: %s" % (", ".join(r for r, _d, _s in docs), request["request_id"]))


def cmd_blueprint(project, b):
    need(b, "id", "feature", "title", "summary", "components", "tests", "rollback")
    now = ap.now_iso()
    with open(os.path.join(ap.aisef_dir(project), "contracts", "features", b["feature"] + ".json"), encoding="utf-8") as fh:
        feature = json.load(fh)
    comps = [{"id": cid, "kind": c[0], "name": c[1], "responsibility": c[2], "owner_role": c[3], "requirement_ids": c[4]}
             for cid, c in b["components"].items()]
    main = comps[0]["id"]
    endpoints = []
    for i, e in enumerate(b.get("endpoints", [])):
        method, path, auth, reqs = e[:4]
        errors = [{"status": 400, "code": "invalid_request"}]
        if auth != "none":
            errors.append({"status": 401, "code": "unauthenticated"})
        ep = {"id": "EP-%s-%d" % (b["id"], i + 1), "component_id": e[4] if len(e) > 4 else main, "method": method,
              "path": path, "auth": auth, "errors": errors, "requirement_ids": reqs}
        if auth == "role_based":
            ep["roles"] = e[5] if len(e) > 5 else []
        endpoints.append(ep)
    entities = []
    for eid, (name, data_class, reqs, fields) in b.get("entities", {}).items():
        fl = []
        for f in fields:
            d = {"name": f[0], "type": f[1]}
            for flag in f[2:]:
                if flag == "pk":
                    d["primary_key"] = True
                elif flag in ("pii", "secret", "nullable"):
                    d[flag] = True
                elif isinstance(flag, str) and flag.startswith("fk:"):
                    ent, field = flag[3:].split(".")
                    d["references"] = {"entity_id": ent, "field": field}
            fl.append(d)
        entities.append({"id": eid, "name": name, "data_class": data_class, "requirement_ids": reqs, "fields": fl})
    doc = {
        "schema_version": "0.1.0", "blueprint_id": b["id"], "contract_version": 1,
        "feature_id": b["feature"], "feature_contract_version": feature["contract_version"],
        "title": b["title"], "summary": b["summary"],
        "architecture": {"components": comps,
                         "interactions": [{"id": "I-%s-%d" % (b["id"], i + 1), "from": x[0], "to": x[1], "protocol": x[2],
                                           "description": x[3] if len(x) > 3 else "", "authenticated": True}
                                          for i, x in enumerate(b.get("interactions", []))],
                         "decisions": [{"id": d, "version": 1} for d in b.get("decisions", [])]},
        "security": {"threats": [{"id": t[0], "description": t[1], "severity": t[2], "mitigation": t[3], "component_ids": t[4]}
                                 for t in b.get("threats", [])],
                     "secrets_handling": b.get("secrets_handling") or "Nenhum segredo novo nesta feature; segredos existentes seguem fora do codigo e dos logs (T3)."},
        "devops": {"environments": b.get("environments", ["dev"]), "rollback": b["rollback"],
                   **({"deploy_strategy": b["deploy_strategy"]} if b.get("deploy_strategy") else {})},
        "test_strategy": {"levels": [{"level": lvl, "covers": reqs} for lvl, reqs in b["tests"].items()]},
        "approval": {"status": "pending"}, "state": {"status": "proposed"},
        "audit": {"created_by": "orchestrator", "created_at": now},
    }
    if endpoints:
        doc["backend"] = {"endpoints": endpoints}
    if b.get("screens"):
        doc["frontend"] = {"screens": [{"id": s[0], "name": s[1], "route": s[2], "calls_endpoint_ids": s[3], "requirement_ids": s[4]}
                                       for s in b["screens"]]}
    if entities:
        doc["database"] = {"entities": entities,
                           "migrations": [{"id": m[0], "description": m[1], "entity_ids": m[2], "destructive": False,
                                           "reversible": True, "rollback": m[3]} for m in b.get("migrations", [])]}
    write_all(project, [("blueprints/%s.json" % b["id"], doc, "engineering-blueprint.schema.v0.1.json")],
              None, "Engineering Blueprint %s v1 criado" % b["id"], b["feature"])
    print("criado: blueprints/%s.json (proposto; peca aprovacao com aisef-approve)" % b["id"])


def cmd_quick(project, title, why, paths, test_cmd):
    """Caminho rapido: tarefa de manutencao na feature permanente FEAT-MAINT (plano aprovado uma vez)."""
    now = ap.now_iso()
    root = ap.aisef_dir(project)
    fpath = os.path.join(root, "contracts", "features", MAINT_FEATURE + ".json")
    tasks_dir = os.path.join(root, "contracts", "tasks")
    n = 1
    while os.path.exists(os.path.join(tasks_dir, "T-MAINT-%03d.json" % n)):
        n += 1
    tid = "T-MAINT-%03d" % n
    brief_task = {"id": tid, "title": title, "objective": "%s (motivo: %s)" % (title, why), "role": "orchestrator", "reqs": [MAINT_REQ],
                  "criteria": {"AC-%s" % tid: "Suite de testes passa sem regressao apos a mudanca"},
                  "paths": paths, "test_cmd": test_cmd, "independent_validation": False,
                  "validator_role": "orchestrator"}
    if not os.path.exists(fpath):
        brief = {"id": MAINT_FEATURE, "title": "Manutencao continua",
                 "objective": "Mudancas pequenas sem alteracao de comportamento (caminho rapido)",
                 "problem": "Ajustes triviais nao justificam o ciclo completo de feature",
                 "priority": "low",
                 "requirements": {MAINT_REQ: {"text": "Mudancas de manutencao nao alteram comportamento observavel nem contratos",
                                              "origin": "decision", "kind": "non_functional"}},
                 "scope_in": ["correcoes triviais, textos, ajustes de configuracao local, atualizacoes de dependencia sem quebra"],
                 "scope_out": ["mudanca de comportamento", "API, schema de banco, seguranca, CI/CD, producao"],
                 "tasks": [brief_task]}
        cmd_feature(project, brief)
        print("primeira vez: aprove o plano de %s (aisef-approve) para liberar o caminho rapido" % MAINT_FEATURE)
        return
    with open(fpath, encoding="utf-8") as fh:
        feature = json.load(fh)
    cfg = ap.load_config(project)
    task = task_doc(brief_task, MAINT_FEATURE, feature["contract_version"], cfg.get("environment", "dev"), now)
    task["state"]["status"] = "ready" if feature["approval"]["plan"]["status"] == "approved" else "draft"
    feature["task_plan"].append({"task_id": tid, "contract_version": 1, "role": "orchestrator"})
    rtm = next(r for r in feature["rtm"] if r["requirement_id"] == MAINT_REQ)
    rtm["task_ids"].append(tid)
    rtm["criterion_ids"].append("AC-" + tid)
    feature["acceptance_criteria"].append({"id": "AC-" + tid, "description": "Suite de testes passa sem regressao apos a mudanca",
                                           "requirement_ids": [MAINT_REQ], "verification": "automated_test"})
    problems = ap.validate(feature, "feature-contract.schema.v0.1.json") + ap.validate(task, "task-contract.schema.v0.1.json")
    if problems:
        raise SystemExit("nada foi gravado:\n - " + "\n - ".join(problems))
    ap.write_json(os.path.join(tasks_dir, tid + ".json"), task)
    ap.write_json(fpath, feature)
    ap.append(project, {"event_type": "contract_created", "actor": {"type": "orchestrator", "id": "orchestrator"},
                        "summary": "Tarefa de manutencao %s: %s" % (tid, title), "feature_id": MAINT_FEATURE})
    print("criada: %s (%s)" % (tid, task["state"]["status"]))


def main(argv):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["feature", "blueprint", "quick", "example"])
    p.add_argument("what", nargs="?")
    p.add_argument("--project", default=os.getcwd())
    p.add_argument("--brief")
    p.add_argument("--title")
    p.add_argument("--why")
    p.add_argument("--path", action="append", default=[])
    p.add_argument("--test-cmd")
    a = p.parse_args(argv)
    if a.command == "example":
        print(json.dumps(EXAMPLES[a.what or "feature"], ensure_ascii=False, indent=1))
        return 0
    project = os.path.abspath(a.project)
    if a.command == "quick":
        if not (a.title and a.why):
            p.error("--title e --why sao obrigatorios")
        cmd_quick(project, a.title, a.why, a.path, a.test_cmd)
        return 0
    if not a.brief:
        p.error("--brief e obrigatorio")
    (cmd_feature if a.command == "feature" else cmd_blueprint)(project, load_brief(a.brief))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
