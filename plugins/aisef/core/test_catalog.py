#!/usr/bin/env python3
"""Catalogo de agentes como fonte unica: consistencia, derivados (perfis, niveis, avaliadores) e ativacao por projeto."""
import copy
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["AISEF_HOME"] = os.path.join(tempfile.mkdtemp(dir=os.environ.get("TMPDIR")), "home")
sys.path.insert(0, HERE)
import aisef_catalog as cat  # noqa: E402
import aisef_new as an  # noqa: E402
import aisef_project as ap  # noqa: E402
import aisef_route as ar  # noqa: E402

fails, total = 0, 0


def check(name, cond, detail=None):
    global fails, total
    total += 1
    if not cond:
        fails += 1
        print("FALHA %s %s" % (name, "" if detail is None else detail))


# ---------------------------------------------------------------- catalogo
check("catalogo valido", cat.check() == [], cat.check())
ids = cat.role_ids()
check("papeis historicos presentes", {"orchestrator", "implementer", "backend", "frontend", "database", "qa", "security",
                                      "devops", "domain", "validator"} <= ids)
check("perfis do Agent Contract vem do catalogo", ap.AGENT_PROFILES == cat.profiles())
check("AGENT_ROLES do aisef_new vem do catalogo", an.AGENT_ROLES == ids)
check("avaliadores incluem qa, security e validator", {"qa", "security", "validator"} <= cat.evaluator_roles())
check("validador valida executores e corretores, nunca avaliadores",
      set(cat.validatable_roles()).isdisjoint(cat.evaluator_roles()) and "implementer" in cat.validatable_roles())
check("contrato do validador lista os papeis validaveis",
      ap.agent_contract("validator", "2026-11-19T00:00:00Z")["validation_role"]["validates"] == cat.validatable_roles())

# ---------------------------------------------------------------- Model Policy
pol = ar.load_policy()
check("niveis padrao da politica vem do catalogo", pol["role_defaults"] == cat.role_defaults(), pol["role_defaults"])
check("politica consistente com os niveis do catalogo", ar.check_policy(pol) == [], ar.check_policy(pol))
check("todo papel roteavel tem nivel", all(r["id"] in pol["role_defaults"] for r in cat.roles()
                                            if r["kind"] not in ("orchestrator", "validator")))

# ---------------------------------------------------------------- erros de catalogo sao detectados
with tempfile.TemporaryDirectory() as tmp:
    base = copy.deepcopy(cat.load())
    os.makedirs(os.path.join(tmp, "prompts"))
    for r in base["roles"]:
        if r.get("prompt"):
            with open(os.path.join(tmp, r["prompt"]), "w", encoding="utf-8") as fh:
                fh.write("x\n")

    def bad(mutate):
        doc = copy.deepcopy(base)
        mutate(doc)
        path = os.path.join(tmp, "c%d.json" % id(doc))
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        return cat.check(path)

    check("papel duplicado e recusado", bad(lambda d: d["roles"].append(copy.deepcopy(d["roles"][1]))))
    check("avaliador com Edit e recusado",
          bad(lambda d: next(r for r in d["roles"] if r["id"] == "qa")["tools"].append("Edit")))
    check("activation invalida e recusada", bad(lambda d: d["roles"][1].update(activation="stack")))
    check("papel roteavel sem nivel e recusado", bad(lambda d: d["roles"][1].update(level=None)))
    check("prompt inexistente e recusado", bad(lambda d: d["roles"][1].update(prompt="prompts/nao-existe.md")))

# ---------------------------------------------------------------- ativacao
role = {"activation": "stack:python"}
check("stack detectada ativa o papel", cat.applicable(role, stacks=("python",)))
check("stack ausente nao ativa", not cat.applicable(role, stacks=("go",)))
check("manual nunca se aplica sozinho", not cat.applicable({"activation": "manual"}, ("python",), ("ddd",), ("x",)))
check("arch ativa pelo estilo", cat.applicable({"activation": "arch:ddd"}, styles=("ddd",)))
check("domain ativa pelo dominio", cat.applicable({"activation": "domain:ml"}, domains=("ml",)))

with tempfile.TemporaryDirectory() as tmp:
    ap.init(tmp, "demo-catalogo")
    made = sorted(f[:-5] for f in os.listdir(os.path.join(tmp, ".aisef", "contracts", "agents")))
    always = sorted(r["id"] for r in cat.roles() if r["activation"] == "always")
    check("init cria so os papeis always", made == always, made)
    stack_roles = [r["id"] for r in cat.roles() if r["activation"].startswith("stack:")]
    if stack_roles:
        sid = cat.get(stack_roles[0])["activation"].split(":", 1)[1]
        with open(os.path.join(tmp, ".aisef", "architecture.json"), "w", encoding="utf-8") as fh:
            json.dump({"stacks": [{"id": sid}], "styles": []}, fh)
        created = ap.write_agent_drafts(tmp)
        check("stack detectada cria o draft do papel da stack", stack_roles[0] in created, created)
    manual = [r["id"] for r in cat.roles() if r["activation"] == "manual"]
    if manual:
        check("papel manual so com pedido explicito", manual[0] in ap.write_agent_drafts(tmp, [manual[0]]))
    try:
        ap.write_agent_drafts(tmp, ["padeiro"])
        check("papel fora do catalogo e recusado", False)
    except SystemExit:
        check("papel fora do catalogo e recusado", True)

print("%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
