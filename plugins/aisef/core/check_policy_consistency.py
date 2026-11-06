#!/usr/bin/env python3
"""Verificador de consistencia: politica x schema de autorizacao x schema do Approval Center (RASCUNHO v0.1).

Cruza o que a matriz da politica exige com o que os schemas de fato conseguem emitir. Se a politica pede
'approve_scope' para algo que o schema de autorizacao nao permite, ou 'approve_operation' onde o Approval
Center nao aceita, o pedido seria impossivel de atender. Isto e o embriao do validador de consistencia.

Uso:
    python3 -I check_policy_consistency.py <policy.json> <authorization.schema.json> <approval-request.schema.json>
Saida: lista de conflitos; codigo de saida 1 se houver algum.
"""
import json
import sys

READ_ACTIONS = {"read", "read_content", "read_rows"}
LEVELS = ["allow", "approve_scope", "approve_operation", "approve_reinforced", "deny"]


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def scope_capabilities(auth):
    """Extrai do schema de autorizacao o que um escopo consegue cobrir."""
    sa = auth["$defs"]["scope_authorization"]
    envs = set(sa["properties"]["environment"]["enum"])
    resources = set(sa["properties"]["resources"]["items"]["enum"])
    staging_resources = None
    for rule in sa.get("allOf", []):
        cond = rule.get("if", {}).get("properties", {}).get("environment", {})
        if cond.get("const") == "staging":
            staging_resources = set(rule["then"]["properties"]["resources"]["items"]["enum"])
    return envs, resources, staging_resources


def operation_capabilities(approval):
    """Extrai do schema do Approval Center o que operation_approval aceita em producao."""
    prod_read_resources = None
    prod_requires_read_only = False
    for rule in approval.get("allOf", []):
        props = rule.get("if", {}).get("properties", {})
        if props.get("request_type", {}).get("const") != "operation_approval":
            continue
        env = props.get("operation", {}).get("properties", {}).get("environment", {})
        if env.get("const") == "prod":
            op = rule["then"]["properties"]["operation"]["properties"]
            prod_read_resources = set(op.get("resource_class", {}).get("enum", []))
            prod_requires_read_only = op.get("access", {}).get("const") == "read"
    return prod_read_resources, prod_requires_read_only


def iter_cells(matrix):
    for resource, actions in matrix.items():
        for action, value in actions.items():
            if action.startswith("$"):
                continue
            if resource == "git":
                yield resource, action, None, value
                continue
            for env, level in value.items():
                yield resource, action, env, level


def check(policy, auth, approval):
    conflicts = []
    scope_envs, scope_resources, staging_resources = scope_capabilities(auth)
    prod_read_resources, prod_read_only = operation_capabilities(approval)

    for resource, action, env, level in iter_cells(policy["matrix"]):
        if level == "not_applicable_via_git" or env is None:
            continue
        cell = "%s.%s em %s = %s" % (resource, action, env, level)
        if level not in LEVELS:
            conflicts.append("%s: nivel desconhecido" % cell)
            continue
        if level == "approve_scope":
            if env not in scope_envs:
                conflicts.append("%s: o schema de autorizacao nao permite escopo em '%s' (T2)" % (cell, env))
            if resource not in scope_resources:
                conflicts.append("%s: '%s' nao pode entrar em escopo no schema de autorizacao" % (cell, resource))
            elif env == "staging" and staging_resources is not None and resource not in staging_resources:
                conflicts.append("%s: em staging o escopo so cobre %s" % (cell, sorted(staging_resources)))
        elif level == "approve_operation":
            if env == "prod":
                if action not in READ_ACTIONS:
                    conflicts.append("%s: em producao, aprovacao por operacao so e aceita para leitura" % cell)
                elif not prod_read_only or prod_read_resources is None or resource not in prod_read_resources:
                    conflicts.append("%s: o Approval Center nao aceita operation_approval de leitura de '%s' em producao" % (cell, resource))

    # Git: cada operacao tem pedido proprio (git_operation) e os reforcados exigem as confirmacoes
    git = policy["matrix"].get("git", {})
    request_ops = set(approval["properties"]["git"]["properties"]["operation"]["enum"])
    for op, level in git.items():
        if op.startswith("$"):
            continue
        if level not in ("allow", "approve_operation", "approve_reinforced"):
            conflicts.append("git.%s = %s: nao ha tipo de pedido correspondente" % (op, level))
        elif level != "allow" and op not in request_ops:
            conflicts.append("git.%s = %s: o Approval Center nao aceita git.operation '%s' (o pedido teria de usar outro tipo)" % (op, level, op))
    for op in sorted(request_ops - set(k for k in git if not k.startswith("$"))):
        conflicts.append("git.operation '%s' do Approval Center nao existe na matriz da politica" % op)

    # T2: producao nunca por escopo
    t2 = next((r for r in policy["transversal_rules"] if r["id"] == "T2"), None)
    if t2 and t2.get("scope_authorization_allowed") is False and "prod" in scope_envs:
        conflicts.append("T2 proibe escopo em producao, mas o schema de autorizacao aceita environment 'prod'")

    # Validade reforcada
    max_policy = t2.get("validity_minutes_max") if t2 else None
    rein = auth["$defs"]["reinforced_approval"]["properties"]["validity_minutes"].get("maximum")
    req = approval["properties"]["validity_minutes"].get("maximum")
    for name, val in (("schema de autorizacao", rein), ("schema do Approval Center", req)):
        if max_policy is not None and val != max_policy:
            conflicts.append("validade maxima da aprovacao reforcada: politica=%s, %s=%s" % (max_policy, name, val))

    # Datasets: classes usadas na politica precisam existir nos schemas
    classes = set(policy["dataset_overrides"]["classes"])
    auth_classes = set(c for c in auth["$defs"]["scope_authorization"]["properties"]["dataset_classification"]["enum"] if c)
    if classes != auth_classes:
        conflicts.append("classes de dataset diferem: politica=%s, autorizacao=%s" % (sorted(classes), sorted(auth_classes)))

    # Niveis de dataset em staging que dependem de escopo precisam ser possiveis
    for cname, c in policy["dataset_overrides"]["classes"].items():
        for action in ("read_rows", "write"):
            level = c.get(action)
            if level == "approve_scope" and "db_data" not in (staging_resources or scope_resources):
                conflicts.append("dataset %s %s = approve_scope mas db_data nao cabe em escopo de staging" % (cname, action))
    return conflicts


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    policy, auth, approval = (load(p) for p in sys.argv[1:4])
    found = check(policy, auth, approval)
    if found:
        print("%d conflito(s):" % len(found))
        for c in found:
            print(" -", c)
        sys.exit(1)
    print("politica, autorizacao e Approval Center consistentes")
