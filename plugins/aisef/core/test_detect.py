#!/usr/bin/env python3
"""Deteccao de stack e arquitetura (aisef_detect): repositorios-fixture por estilo, regra de dependencia,
recomendacoes, schema e integracao com o catalogo (drafts dos papeis da stack)."""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["AISEF_HOME"] = os.path.join(tempfile.mkdtemp(dir=os.environ.get("TMPDIR")), "home")
sys.path.insert(0, HERE)
import aisef_detect as det  # noqa: E402
import aisef_project as ap  # noqa: E402
import check_project as cp  # noqa: E402

fails, total = 0, 0
WORK = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))


def check(name, cond, detail=None):
    global fails, total
    total += 1
    if not cond:
        fails += 1
        print("FALHA %s %s" % (name, "" if detail is None else detail))


def repo(name, files):
    root = os.path.join(WORK, name)
    for rel, text in files.items():
        p = os.path.join(root, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
    return root


def styles(doc):
    return {s["id"]: s["confidence"] for s in doc["styles"]}


def stacks(doc):
    return {s["id"] for s in doc["stacks"]}


def valid(doc):
    import jsonschema
    with open(os.path.join(HERE, "architecture.schema.v0.1.json"), encoding="utf-8") as fh:
        return [e.message for e in jsonschema.Draft202012Validator(json.load(fh)).iter_errors(doc)]


# ---------------------------------------------------------------- Clean Architecture em Python, com violacao
clean = repo("clean", {
    "pyproject.toml": "[project]\nname='loja'\ndependencies=['fastapi>=0.110', 'sqlalchemy']\n",
    "src/loja/domain/pedido.py": "from dataclasses import dataclass\nfrom loja.infrastructure.db import Session\nimport sqlalchemy\n",
    "src/loja/domain/__init__.py": "",
    "src/loja/application/criar_pedido.py": "from loja.domain.pedido import Pedido\n",
    "src/loja/infrastructure/db.py": "import sqlalchemy\nfrom loja.domain.pedido import Pedido\n",
    "src/loja/presentation/api.py": "from fastapi import FastAPI\nfrom loja.application.criar_pedido import x\n",
    "tests/test_pedido.py": "from loja.domain.pedido import Pedido\n",
})
d = det.detect(clean)
check("clean: schema valido", valid(d) == [], valid(d))
check("clean: stacks python e fastapi", {"python", "fastapi"} <= stacks(d), stacks(d))
check("clean: estilo clean detectado", styles(d).get("clean", 0) >= 0.5, styles(d))
rules = {(v["rule"], v["file"]) for v in d["violations"]}
check("clean: dominio importando infraestrutura e violacao",
      ("inner-imports-outer", "src/loja/domain/pedido.py") in rules, d["violations"])
check("clean: dominio importando ORM e violacao", ("domain-imports-framework", "src/loja/domain/pedido.py") in rules)
check("clean: infraestrutura importando dominio e permitido",
      not any(v["file"] == "src/loja/infrastructure/db.py" for v in d["violations"]))
check("clean: aplicacao importando dominio e permitido",
      not any(v["file"] == "src/loja/application/criar_pedido.py" for v in d["violations"]))
check("clean: violacao com linha", all(v["line"] >= 1 for v in d["violations"]))
check("clean: recomenda corrigir a regra de dependencia", "REC-DEPENDENCY-RULE" in {r["id"] for r in d["recommendations"]})
check("clean: praticas incluem python e clean", {"common", "lang/python", "architecture/clean-architecture"} <= set(d["practices"]), d["practices"])
check("clean: comandos por stack", "pytest -q" == d["commands"].get("python", {}).get("test"), d["commands"])
check("deps sai 1 com violacao", det.main(["deps", "--project", clean]) == 1)

# ---------------------------------------------------------------- hexagonal em TypeScript, relativo
hexa = repo("hexa", {
    "package.json": json.dumps({"dependencies": {"express": "4"}, "devDependencies": {"typescript": "5"}}),
    "tsconfig.json": "{}",
    "src/domain/order.ts": "export class Order {}\n",
    "src/domain/ports/order-repository.ts": "import { Order } from '../order';\n",
    "src/adapters/inbound/http.ts": "import express from 'express';\nimport { Order } from '../../domain/order';\n",
    "src/adapters/outbound/pg-order-repository.ts": "import { OrderRepository } from '../../domain/ports/order-repository';\n",
    "src/application/place-order.ts": "import { Order } from '../domain/order';\n",
})
d = det.detect(hexa)
check("hexa: stacks typescript e express", {"typescript", "express"} <= stacks(d), stacks(d))
check("hexa: estilo hexagonal", styles(d).get("hexagonal", 0) >= 0.5, styles(d))
check("hexa: sem violacao (dependencias para dentro)", d["violations"] == [], d["violations"])
check("hexa: typescript sem javascript duplicado", "javascript" not in stacks(d), stacks(d))

# ---------------------------------------------------------------- DDD tatico + CQRS em Java
ddd = repo("ddd", {
    "pom.xml": "<project><dependency><artifactId>spring-boot-starter-web</artifactId></dependency></project>",
    "src/main/java/com/acme/orders/domain/model/OrderAggregate.java": "package x;\nimport com.acme.orders.domain.model.Money;\n",
    "src/main/java/com/acme/orders/domain/valueobjects/Money.java": "package x;\n",
    "src/main/java/com/acme/orders/domain/events/OrderPlacedDomainEvent.java": "package x;\n",
    "src/main/java/com/acme/orders/domain/repositories/OrderRepository.java": "package x;\nimport org.springframework.data.Repository;\n",
    "src/main/java/com/acme/orders/application/commands/PlaceOrder.java": "package x;\n",
    "src/main/java/com/acme/orders/application/queries/GetOrder.java": "package x;\n",
    "src/main/java/com/acme/orders/application/handlers/PlaceOrderHandler.java": "package x;\n",
    "CONTEXT.md": "# Linguagem ubiqua\n",
})
d = det.detect(ddd)
s = styles(d)
check("ddd: stacks java e spring", {"java", "spring"} <= stacks(d), stacks(d))
check("ddd: DDD tatico", s.get("ddd-tactical", 0) >= 0.5, s)
check("ddd: CQRS", s.get("cqrs", 0) >= 0.5, s)
check("ddd: glossario conta para DDD estrategico", "ddd-strategic" in s, s)
check("ddd: Spring no dominio e violacao", any(v["rule"] == "domain-imports-framework" for v in d["violations"]), d["violations"])
check("ddd: recomenda conferir CQRS", "REC-CQRS-SEPARATION" in {r["id"] for r in d["recommendations"]})

# ---------------------------------------------------------------- MVC (Rails)
mvc = repo("mvc", {
    "Gemfile": "source 'https://rubygems.org'\ngem 'rails', '~> 7.1'\n",
    "config/routes.rb": "Rails.application.routes.draw do\nend\n",
    "app/controllers/orders_controller.rb": "class OrdersController; end\n",
    "app/models/order.rb": "class Order; end\n",
    "app/views/orders/index.html.erb": "",
    "app/services/charge.rb": "class Charge; end\n",
})
d = det.detect(mvc)
check("mvc: stacks ruby e rails", {"ruby", "rails"} <= stacks(d), stacks(d))
check("mvc: camadas/MVC", styles(d).get("layered-mvc", 0) >= 0.5, styles(d))
check("mvc: recomenda tirar regra de controllers", "REC-MVC-SERVICE-LAYER" in {r["id"] for r in d["recommendations"]})
check("mvc: sem testes gera recomendacao so com codigo suficiente", "REC-TESTS" not in {r["id"] for r in d["recommendations"]})

# ---------------------------------------------------------------- monolito modular (.NET com nomes por ponto)
mm = repo("modular", {
    "Loja.sln": "",
    "src/Modules/Pedidos/Loja.Pedidos.Domain/Pedido.cs": "namespace Loja.Pedidos.Domain;\nusing Loja.Pedidos.Infrastructure;\n",
    "src/Modules/Pedidos/Loja.Pedidos.Application/Criar.cs": "namespace X;\n",
    "src/Modules/Pedidos/Loja.Pedidos.Infrastructure/Repo.cs": "namespace X;\nusing Microsoft.EntityFrameworkCore;\n",
    "src/Modules/Estoque/Loja.Estoque.Domain/Item.cs": "namespace X;\n",
    "src/Modules/Estoque/Loja.Estoque.Application/Baixar.cs": "namespace X;\n",
    "src/Loja.SharedKernel/Entity.cs": "namespace X;\n",
})
d = det.detect(mm)
s = styles(d)
check("modular: stack csharp", "csharp" in stacks(d), stacks(d))
check("modular: monolito modular", s.get("modular-monolith", 0) >= 0.5, s)
check("modular: shared kernel conta para DDD estrategico", "ddd-strategic" in s, s)
check("modular: using de infraestrutura no dominio e violacao",
      any(v["file"].endswith("Pedido.cs") and v["to_layer"] == "infrastructure" for v in d["violations"]), d["violations"])

# ---------------------------------------------------------------- microsservicos
ms = repo("micro", dict({"services/orders/h%d.go" % i: "package main\n" for i in range(5)},
                       **{"services/billing/m%d.py" % i: "" for i in range(5)}, **{
    "docker-compose.yml": "services: {}\n",
    "services/orders/go.mod": "module orders\n",
    "services/orders/main.go": "package main\n",
    "services/billing/pyproject.toml": "[project]\nname='billing'\ndependencies=['kafka-python']\n",
    "services/billing/app.py": "",
    "services/billing/consumers/invoice.py": "",
    "services/billing/producers/paid.py": "",
}))
d = det.detect(ms)
s = styles(d)
check("micro: microsservicos", s.get("microservices", 0) >= 0.5, s)
check("micro: stacks go e python", {"go", "python"} <= stacks(d), stacks(d))
check("micro: orientado a eventos com broker", "event-driven" in s, s)

# ---------------------------------------------------------------- sem padrao, sem testes
flat = repo("flat", dict({"setup.py": "from setuptools import setup\n"}, **{"pkg/m%02d.py" % i: "x = %d\n" % i for i in range(45)}))
d = det.detect(flat)
recs = {r["id"] for r in d["recommendations"]}
check("flat: nenhum estilo", d["styles"] == [], d["styles"])
check("flat: recomenda definir estilo", "REC-DEFINE-STYLE" in recs, recs)
check("flat: recomenda testes", "REC-TESTS" in recs, recs)
check("flat: sem camadas nao procura violacao", d["violations"] == [] and d["scan"]["import_files_scanned"] == 0)
check("flat: schema valido", valid(d) == [], valid(d))

# ---------------------------------------------------------------- dominios e pastas ignoradas
ml = repo("ml", {"requirements.txt": "torch==2.3\nlangchain\n", "train.py": "", "node_modules/x/domain/a.py": "import django\n"})
d = det.detect(ml)
check("ml: dominios ml e rag", {"ml", "rag"} <= set(d["domains"]), d["domains"])
check("ml: pytorch detectado", "pytorch" in stacks(d), stacks(d))
check("pastas de dependencia ignoradas", not any("node_modules" in v["file"] for v in d["violations"]) and d["scan"]["files"] == 2,
      d["scan"])

# ---------------------------------------------------------------- regressao da avaliacao A-03 (repositorios reais)
real = repo("a03", dict({"src/%s.API/F%d.cs" % (n, i): "namespace X;\n" for n in ("Basket", "Catalog") for i in range(5)}, **{
    "Loja.sln": "",
    "src/Ordering.API/Ordering.API.csproj": "<Project/>",
    "src/Ordering.API/Application/Commands/Criar.cs": "using Loja.Ordering.API.Extensions;\n",
    "src/Ordering.API/Extensions/X.cs": "namespace X;\n",
    "src/Basket.API/Basket.API.csproj": "<Project/>",
    "src/Catalog.API/Catalog.API.csproj": "<Project/>",
    "src/Ordering.Domain/AggregatesModel/Order.cs": "namespace X;\n",
    "src/Ordering.Domain/SeedWork/IAggregateRoot.cs": "namespace X;\n",
    "src/Ordering.Infrastructure/Domain/OrderConfig.cs": "using Microsoft.EntityFrameworkCore;\n",
    "web/src/user/user.repository.port.ts": "export interface P {}\n",
    "web/src/user/user.http.adapter.ts": "export class A {}\n",
    "web/src/user/domain/user.entity.ts": "export class U {}\n",
}))
d = det.detect(real)
s = styles(d)
check("A-03: pastas irmas *.API com manifest proprio sao microsservicos", s.get("microservices", 0) >= 0.5, s)
check("A-03: arquivos *.port.ts e *.adapter.ts indicam hexagonal", "hexagonal" in s, s)
check("A-03: IAggregateRoot conta como DDD tatico", "ddd-tactical" in s, s)
check("A-03: Infrastructure/Domain e infraestrutura, nao dominio (EF Core permitido)",
      not any(v["file"].endswith("OrderConfig.cs") for v in d["violations"]), d["violations"])
check("A-03: Application dentro do projeto Ordering.API importando o proprio projeto nao e violacao",
      not any(v["file"].endswith("Criar.cs") for v in d["violations"]), d["violations"])
check("A-03: layer_of", det.layer_of("src/Infrastructure/Domain/Members") == "infrastructure"
      and det.layer_of("src/Loja.Pedidos.Domain") == "domain" and det.layer_of("x/Ordering.API/Application") == "application")

# ---------------------------------------------------------------- integracao: detect grava, cria drafts e passa no check
ap.init(clean, "demo-detect")
check("init sem architecture.json nao cria revisor de stack",
      not os.path.exists(os.path.join(clean, ".aisef", "contracts", "agents", "python-reviewer.json")))
check("comando detect", ap.main(["detect", "--project", clean]) == 0)
check("detect grava architecture.json", os.path.exists(os.path.join(clean, ".aisef", "architecture.json")))
check("detect cria draft do revisor python",
      os.path.exists(os.path.join(clean, ".aisef", "contracts", "agents", "python-reviewer.json")))
check("detect cria draft do revisor fastapi",
      os.path.exists(os.path.join(clean, ".aisef", "contracts", "agents", "fastapi-reviewer.json")))
check("detect nao cria revisor de outra stack",
      not os.path.exists(os.path.join(clean, ".aisef", "contracts", "agents", "go-reviewer.json")))
codes = cp.check(clean).codes()
check("check: estilo detectado e nao adotado vira aviso", "ARCH-PENDING" in codes, sorted(codes))
check("check: violacao da regra de dependencia vira aviso", "ARCH-DEPENDENCY" in codes, sorted(codes))
check("check: sem ARCH-SCHEMA", "ARCH-SCHEMA" not in codes, sorted(codes))
path = os.path.join(clean, ".aisef", "architecture.json")
with open(path, encoding="utf-8") as fh:
    arch = json.load(fh)
arch["approved"] = {"styles": ["clean"], "request_id": "REQ-999", "approved_at": "2026-11-19T10:00:00-03:00"}
with open(path, "w", encoding="utf-8") as fh:
    json.dump(arch, fh)
check("check: estilo adotado sem aprovacao e erro", "ARCH-UNAPPROVED" in cp.check(clean).codes())
det.write(clean, det.detect(clean))
with open(path, encoding="utf-8") as fh:
    check("nova deteccao preserva o estilo aprovado", json.load(fh).get("approved", {}).get("styles") == ["clean"])
check("estilo aprovado vale para a ativacao", ap.project_traits(clean)[1] == ("clean",))

# ---------------------------------------------------------------- adocao do estilo exige architecture_decision aprovado
try:
    ap.adopt_styles(clean, ["clean"], "REQ-NAO-EXISTE")
    check("adocao sem pedido e recusada", False)
except SystemExit:
    check("adocao sem pedido e recusada", True)
os.makedirs(os.path.join(clean, ".aisef", "approvals"), exist_ok=True)
with open(os.path.join(clean, ".aisef", "approvals", "REQ-777.json"), "w", encoding="utf-8") as fh:
    json.dump({"request_id": "REQ-777", "status": "pending", "request_type": "architecture_decision"}, fh)
try:
    ap.adopt_styles(clean, ["clean"], "REQ-777")
    check("adocao com pedido pendente e recusada", False)
except SystemExit:
    check("adocao com pedido pendente e recusada", True)
with open(os.path.join(clean, ".aisef", "approvals", "REQ-777.json"), "w", encoding="utf-8") as fh:
    json.dump({"request_id": "REQ-777", "status": "approved", "request_type": "architecture_decision"}, fh)
try:
    ap.adopt_styles(clean, ["padeiro"], "REQ-777")
    check("estilo desconhecido e recusado", False)
except SystemExit:
    check("estilo desconhecido e recusado", True)
got = ap.adopt_styles(clean, ["clean", "ddd-tactical"], "REQ-777")
with open(path, encoding="utf-8") as fh:
    check("adocao grava o estilo aprovado", json.load(fh)["approved"]["styles"] == ["clean", "ddd-tactical"])
check("estilo adotado ativa papeis por arquitetura", ap.project_traits(clean)[1] == ("clean", "ddd-tactical"))

# ---------------------------------------------------------------- achados do deckloom: servicos magros e fronteira entre modulos
dk = repo("dk", dict({
    "Loja.sln": "", "docker-compose.yml": "services: {}\n",
    "src/Services/A.Service/A.Service.csproj": "<Project/>", "src/Services/A.Service/Program.cs": "x",
    "src/Services/B.Service/B.Service.csproj": "<Project/>", "src/Services/B.Service/Program.cs": "x",
    "src/Modules/Contas/Loja.Contas.Application/IPorta.cs": "namespace X;\n",
    "src/Modules/Contas/Loja.Contas.Domain/Item.cs": "namespace X;\n",
    "src/Modules/Sugestao/Loja.Sugestao.Infrastructure/Adapter.cs":
        "using Loja.Contas.Application;\nusing Loja.Contas.Domain;\nnamespace X;\n",
}))
d = det.detect(dk)
s_ = styles(d)
check("deckloom: servicos so com Program.cs nao sao microsservicos (< 0.5)", s_.get("microservices", 0) < 0.5, s_)
mods = d["modules"]
check("deckloom: modulos analisados e listados", len(mods["roots"]) == 2 and mods["files_scanned"] >= 1, mods)
dep = {(x["to_layer"], x["allowed"]) for x in mods["dependencies"]}
check("deckloom: aplicacao de outro modulo e permitida", ("application", True) in dep, dep)
check("deckloom: dominio de outro modulo e violacao cross-module-internal",
      ("domain", False) in dep and any(v["rule"] == "cross-module-internal" for v in d["violations"]), d["violations"])
check("deckloom: schema valido com modules", valid(d) == [], valid(d))

# ---------------------------------------------------------------- T2 real: decisao de PROJETO (sem feature) -> adopt -> check
import datetime  # noqa: E402
proj2 = repo("t2", {"pyproject.toml": "[project]\nname='x'\n", "src/x/domain/a.py": "", "src/x/application/b.py": "",
                    "src/x/infrastructure/c.py": "", "src/x/presentation/d.py": ""})
ap.init(proj2, "PRJ-T2")
ap.main(["detect", "--project", proj2])
cfg = json.load(open(os.path.join(proj2, ".aisef", "config.json"), encoding="utf-8"))
now = datetime.datetime.now(datetime.timezone.utc).astimezone()
ev_id = next(json.loads(l)["event_id"] for l in open(os.path.join(proj2, ".aisef", "audit", "log.jsonl"), encoding="utf-8")
             if json.loads(l)["event_type"] == "evidence_recorded")
draft = {"schema_version": "0.1.0", "request_id": "APR-001", "request_type": "architecture_decision", "status": "pending",
         "title": "Adotar o estilo de arquitetura do projeto", "summary": "Adotar Clean Architecture como estilo do projeto inteiro.",
         "requested_by": {"type": "orchestrator", "id": "orchestrator"}, "project_id": cfg["project_id"],
         "created_at": now.isoformat(timespec="seconds"),
         "expires_at": (now + datetime.timedelta(days=7)).isoformat(timespec="seconds"),
         "presented": {"impact": "O architecture-reviewer passa a cobrar a regra de dependencia", "evidence_ids": [ev_id]},
         "risk": {"level": "low", "items": []}, "blocks": {"blocked_task_ids": [], "independent_work_continues": True},
         "policy_version": "0.1.0", "audit": {},
         "options": [{"option_id": "OPT-A", "label": "Clean", "description": "Adotar Clean Architecture",
                      "impacts": ["revisao de arquitetura"], "risks": ["cerimonia em CRUD"]},
                     {"option_id": "OPT-B", "label": "Nao adotar", "description": "Seguir sem estilo declarado",
                      "impacts": ["nenhum"], "risks": ["erosao das camadas"]}],
         "recommendation": {"option_id": "OPT-A", "rationale": "As camadas ja existem no codigo; formalizar evita erosao."}}
dpath = os.path.join(WORK, "draft-apr.json")
json.dump(draft, open(dpath, "w", encoding="utf-8"))
ap.request(proj2, dpath)
check("T2: architecture_decision de projeto sem feature_id e aceito pelo request",
      os.path.exists(os.path.join(proj2, ".aisef", "approvals", "APR-001.json")))
bad = dict(draft, request_id="APR-002", request_type="scope_change_decision")
json.dump(bad, open(dpath, "w", encoding="utf-8"))
try:
    ap.request(proj2, dpath)
    check("T2: outro tipo sem feature_id continua recusado", False)
except SystemExit:
    check("T2: outro tipo sem feature_id continua recusado", True)
ap.decide(proj2, "APR-001", "select_option", option="OPT-A")
ap.adopt_styles(proj2, ["clean"], "APR-001")
codes = cp.check(proj2).codes()
check("T2: estilo adotado sem feature, check sem APPROVAL-FEATURE nem ARCH-UNAPPROVED",
      not ({"APPROVAL-FEATURE", "ARCH-UNAPPROVED", "SCHEMA", "ARCH-PENDING"} & set(codes)), sorted(codes))

shutil.rmtree(WORK, ignore_errors=True)
print("%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
