#!/usr/bin/env python3
"""Testes do grafo nativo de imports (G-06): aisef_imports.Resolver, aisef_graph.build_native/ensure_native e o
raio de impacto pelo related(). Somente stdlib."""
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_graph as ag  # noqa: E402
import aisef_imports as ai  # noqa: E402

work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
fails = total = 0


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)))
    fails += not cond


def put(proj, rel, text):
    p = os.path.join(proj, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)


def project(name, files, aisef=True):
    proj = os.path.join(work, name)
    for rel, text in files.items():
        put(proj, rel, text)
    if aisef:
        put(proj, ".aisef/config.json", json.dumps({"project_id": "PRJ-T", "schema_version": "0.1.0"}))
    return proj


def edges(proj):
    g = ag.build_native(proj)
    return {(l["source"], l["target"]) for l in g["links"]}


# ------------------------------------------------------------------ Python
py = project("py", {
    "src/shop/__init__.py": "",
    "src/shop/orders.py": "from .pricing import total\nfrom . import util\nimport os\n",
    "src/shop/pricing.py": "from shop.tax import rate\n",
    "src/shop/tax.py": "RATE = 1\n",
    "src/shop/util.py": "",
    "src/shop/api/views.py": "from ..orders import place\nfrom shop import pricing\n",
    "tests/test_orders.py": "from shop.orders import place\n",
})
e = edges(py)
check("python: relativo com um ponto", ("src/shop/orders.py", "src/shop/pricing.py") in e, e)
check("python: 'from . import x' liga ao __init__ do pacote", ("src/shop/orders.py", "src/shop/__init__.py") in e, e)
check("python: absoluto pelo sufixo (layout src/)", ("src/shop/pricing.py", "src/shop/tax.py") in e, e)
check("python: relativo com dois pontos", ("src/shop/api/views.py", "src/shop/orders.py") in e, e)
check("python: pacote sem modulo cai no __init__", ("src/shop/api/views.py", "src/shop/__init__.py") in e, e)
check("python: teste aparece como quem depende do codigo", ("tests/test_orders.py", "src/shop/orders.py") in e, e)
check("python: biblioteca padrao (os) fica de fora", not any(t.endswith("os.py") for _s, t in e), e)

# ------------------------------------------------------------------ TypeScript
ts = project("ts", {
    "src/app/page.tsx": "import { Button } from '../ui/Button'\nimport x from '@/lib/api'\nimport React from 'react'\n",
    "src/ui/Button.tsx": "export const Button = 1\n",
    "src/ui/index.ts": "export * from './Button'\n",
    "src/lib/api/index.ts": "const u = require('./http')\n",
    "src/lib/api/http.ts": "",
    "src/feature/a.ts": "import '../ui'\n",
})
e = edges(ts)
check("ts: relativo com extensao inferida", ("src/app/page.tsx", "src/ui/Button.tsx") in e, e)
check("ts: alias @/ com index", ("src/app/page.tsx", "src/lib/api/index.ts") in e, e)
check("ts: require relativo", ("src/lib/api/index.ts", "src/lib/api/http.ts") in e, e)
check("ts: import de pasta resolve o index", ("src/feature/a.ts", "src/ui/index.ts") in e, e)
check("ts: pacote do npm fica de fora", all("react" not in t for _s, t in e), e)

# ------------------------------------------------------------------ C# (namespace = pasta)
cs = project("cs", {
    "src/Loja.Pedidos.Domain/Entities/Pedido.cs": "namespace Loja.Pedidos.Domain.Entities;\n",
    "src/Loja.Pedidos.Domain/Entities/Item.cs": "namespace Loja.Pedidos.Domain.Entities;\n",
    "src/Loja.Pedidos.Application/CriarPedido.cs": "using System;\nusing Loja.Pedidos.Domain.Entities;\n",
})
e = edges(cs)
check("c#: using de namespace liga aos arquivos da pasta",
      {("src/Loja.Pedidos.Application/CriarPedido.cs", "src/Loja.Pedidos.Domain/Entities/Pedido.cs"),
       ("src/Loja.Pedidos.Application/CriarPedido.cs", "src/Loja.Pedidos.Domain/Entities/Item.cs")} <= e, e)
check("c#: System fica de fora", len(e) == 2, e)

# ------------------------------------------------------------------ Java, Go, Rust
jv = project("jv", {
    "src/main/java/com/acme/orders/Order.java": "package com.acme.orders;\n",
    "src/main/java/com/acme/api/Ctrl.java": "import com.acme.orders.Order;\nimport java.util.List;\n",
    "src/main/java/com/acme/api/All.java": "import com.acme.orders.*;\n",
})
e = edges(jv)
check("java: classe pelo sufixo do pacote",
      ("src/main/java/com/acme/api/Ctrl.java", "src/main/java/com/acme/orders/Order.java") in e, e)
check("java: import com * liga a pasta",
      ("src/main/java/com/acme/api/All.java", "src/main/java/com/acme/orders/Order.java") in e, e)
go = project("go", {
    "internal/orders/order.go": "package orders\n",
    "cmd/api/main.go": 'package main\nimport (\n\t"fmt"\n\t"github.com/acme/shop/internal/orders"\n)\n',
})
e = edges(go)
check("go: caminho do modulo casa com a pasta", ("cmd/api/main.go", "internal/orders/order.go") in e, e)
rs = project("rs", {"src/orders/model.rs": "", "src/main.rs": "use crate::orders::model::Order;\nuse std::io;\n"})
e = edges(rs)
check("rust: crate:: resolve o modulo (item no fim)", ("src/main.rs", "src/orders/model.rs") in e, e)

# ------------------------------------------------------------------ ambiguidade
amb = {"app%d/models.py" % i: "" for i in range(5)}
amb["main.py"] = "import models\n"
e = edges(project("amb", amb))
check("ambiguo demais (5 models.py) e descartado, sem inventar dependencia", not any(s == "main.py" for s, _t in e), e)
r = ai.Resolver(["a/x.py", "b/x.py"])
check("ambiguo pequeno (2) liga aos dois", r.resolve("main.py", "x") == ["a/x.py", "b/x.py"], r.resolve("main.py", "x"))

# ------------------------------------------------------------------ related() sobre o grafo nativo
rel = ag.ensure_native(py)
check("ensure_native grava em .aisef/runtime/graph.json", rel == ".aisef/runtime/graph.json"
      and os.path.isfile(os.path.join(py, rel)), rel)
g = ag.load(os.path.join(py, rel))
out = ag.related(g, ["src/shop/orders.py"], {"T-001"})
kinds = {(i["kind"], i["file"]) for i in out["items"]}
check("related: quem importa o arquivo da tarefa vira impacto (inclusive o teste)",
      {("impact", "tests/test_orders.py"), ("impact", "src/shop/api/views.py")} <= kinds, kinds)
check("related: o que o arquivo da tarefa importa vira dependencia", ("dependency", "src/shop/pricing.py") in kinds, kinds)

# reconstroi so quando muda
path = os.path.join(py, rel)
m0 = os.path.getmtime(path)
time.sleep(0.05)
ag.ensure_native(py)
check("ensure_native: sem mudanca, nao reconstroi", os.path.getmtime(path) == m0)
time.sleep(0.05)
put(py, "src/shop/new.py", "from shop.orders import place\n")
ag.ensure_native(py)
g = ag.load(os.path.join(py, rel))
check("ensure_native: arquivo novo reconstroi e entra no grafo",
      ("src/shop/new.py", "src/shop/orders.py") in {(l["source"], l["target"]) for l in g[1]})
os.remove(os.path.join(py, "src/shop/new.py"))
ag.ensure_native(py)
check("ensure_native: arquivo removido sai do grafo", "src/shop/new.py" not in ag.load(os.path.join(py, rel))[0])

check("ensure_native: sem .aisef/config.json nao grava nada",
      ag.ensure_native(project("noaisef", {"a.py": "import b\n", "b.py": ""}, aisef=False)) is None
      and not os.path.exists(os.path.join(work, "noaisef", ".aisef")))
check("ensure_native: sem codigo devolve None", ag.ensure_native(project("empty", {"README.md": "x"})) is None)
check("CLI build-native: sai 0 e mostra o tamanho", ag.main(["build-native", "--project", py]) == 0)

# ------------------------------------------------------------------ desempenho: 5.000 arquivos
big = os.path.join(work, "big")
for i in range(5000):
    put(big, "pkg/m%d/mod%d.py" % (i // 50, i), "from pkg.m%d.mod%d import x\nimport os\n" % ((i + 1) // 50 % 100, (i + 1) % 5000))
put(big, ".aisef/config.json", "{}")
ag.ensure_native(big)  # 1a leitura de arquivos recem-criados passa pelo antivirus no Windows: nao e o caso real
t0 = time.time()
ag.ensure_native(big, force=True)
dt = time.time() - t0
g = ag.load(os.path.join(big, ag.NATIVE_GRAPH))
check("desempenho: 5.000 arquivos em menos de 5 s (%.2f s)" % dt, dt < 5 and len(g[0]) == 5000 and len(g[1]) >= 4900,
      (dt, len(g[0]), len(g[1])))

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
