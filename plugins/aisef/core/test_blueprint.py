#!/usr/bin/env python3
"""Testes do schema do Engineering Blueprint (validacao isolada de um documento)."""
import copy, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import userlibs  # noqa: F401
import jsonschema
import make_demo_project as demo
S = json.load(open(os.path.join(HERE, "engineering-blueprint.schema.v0.1.json")))
V = jsonschema.Draft202012Validator(S, format_checker=jsonschema.FormatChecker())
fails = total = 0

def case(name, mut, valid):
    global fails, total
    total += 1
    d = copy.deepcopy(demo.blueprint())
    mut(d)
    ok = V.is_valid(d) == valid
    print(("OK    " if ok else "FALHA ") + name)
    fails += not ok

case("demo valido", lambda d: None, True)
case("campo desconhecido", lambda d: d.update(extra=1), False)
case("sem componentes", lambda d: d["architecture"].update(components=[]), False)
case("componente sem requisito", lambda d: d["architecture"]["components"][0].update(requirement_ids=[]), False)
case("requisitos duplicados", lambda d: d["architecture"]["components"][0].update(requirement_ids=["REQ-001", "REQ-001"]), False)
case("protocolo invalido", lambda d: d["architecture"]["interactions"][0].update(protocol="telepatia"), False)
case("endpoint path sem barra", lambda d: d["backend"]["endpoints"][0].update(path="auth"), False)
case("endpoint autenticado sem erro 401/403", lambda d: d["backend"]["endpoints"][1].update(errors=[{"status": 400, "code": "x"}]), False)
case("endpoint autenticado com 403", lambda d: d["backend"]["endpoints"][1].update(errors=[{"status": 403, "code": "x"}]), True)
case("role_based sem roles", lambda d: d["backend"]["endpoints"][1].update(auth="role_based"), False)
case("role_based com roles", lambda d: d["backend"]["endpoints"][1].update(auth="role_based", roles=["admin"]), True)
case("status de erro 200", lambda d: d["backend"]["endpoints"][0]["errors"][0].update(status=200), False)
case("entidade sem campos", lambda d: d["database"]["entities"][0].update(fields=[]), False)
case("classe de dados invalida", lambda d: d["database"]["entities"][0].update(data_class="secreto"), False)
case("migracao reversivel sem rollback", lambda d: d["database"]["migrations"][0].update(rollback=None), False)
case("migracao destrutiva e irreversivel", lambda d: d["database"]["migrations"][0].update(destructive=True, reversible=False, rollback=None), False)
case("migracao destrutiva reversivel", lambda d: d["database"]["migrations"][0].update(destructive=True), True)
case("ameaca sem mitigacao", lambda d: d["security"]["threats"][0].update(mitigation=""), False)
case("ameaca sem componente", lambda d: d["security"]["threats"][0].update(component_ids=[]), False)
case("sem secrets_handling", lambda d: d["security"].pop("secrets_handling"), False)
case("prod sem estrategia de deploy", lambda d: d["devops"].update(environments=["dev", "prod"]), False)
case("prod com estrategia", lambda d: d["devops"].update(environments=["dev", "prod"], deploy_strategy="canary"), True)
case("sem rollback no devops", lambda d: d["devops"].pop("rollback"), False)
case("sem estrategia de testes", lambda d: d["test_strategy"].update(levels=[]), False)
case("aprovado sem aprovador", lambda d: d["approval"].update(status="approved"), False)
case("aprovado por agente", lambda d: d["approval"].update(status="approved", approved_by="agent", approved_at="2026-01-01T00:00:00+00:00", request_ref="APR-9"), False)
case("aprovado pelo usuario", lambda d: (d["approval"].update(status="approved", approved_by="user", approved_at="2026-01-01T00:00:00+00:00", request_ref="APR-9"), d["state"].update(status="approved")), True)
case("estado aprovado sem aprovacao", lambda d: d["state"].update(status="approved"), False)
case("versao 0", lambda d: d.update(contract_version=0), False)
print("\n%d testes, %d falhas" % (total, fails)); sys.exit(1 if fails else 0)
