#!/usr/bin/env python3
"""AISEF detect: imports, camadas, regra de dependencia, fronteiras entre modulos e recomendacoes

H-01 (0.14): saiu de aisef_detect.py sem mudar o codigo; aisef_detect reexporta tudo."""
import argparse
import datetime
import fnmatch
import json
import os
import re
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_imports  # noqa: E402


SOURCE_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rs", ".java", ".kt", ".kts", ".swift", ".cs", ".fs",
              ".cpp", ".cc", ".cxx", ".hpp", ".hh", ".h", ".c", ".php", ".rb", ".dart", ".gd", ".ets", ".vue", ".svelte", ".scala"}
TEST_RE = re.compile(r"(^|[\\/])(tests?|__tests__|spec|specs)([\\/]|$)|(_test|\.test|\.spec|Test|Tests|_spec)\.[a-z]+$|^test_.*\.py$")
MAX_IMPORT_FILES = 6000
MAX_FILE_BYTES = 300_000

# ------------------------------------------------------------------ estilos de arquitetura (sinais por nome de pasta)
LAYER_ALIASES = {
    "domain": {"domain", "domains"},
    "application": {"application", "app_service", "appservices", "usecases", "use_cases", "usecase", "use-cases", "interactors", "services_app"},
    "infrastructure": {"infrastructure", "infra", "adapters", "adapter", "persistence", "repositories_impl", "gateways", "db", "database"},
    "presentation": {"presentation", "api", "web", "ui", "http", "controllers", "rest", "graphql", "cli", "handlers_http", "routes"},
}
LAYER_RANK = {"domain": 0, "application": 1, "infrastructure": 2, "presentation": 2}
FRAMEWORK_IMPORTS = ("django", "flask", "fastapi", "sqlalchemy", "sqlmodel", "pydantic_settings", "typeorm", "prisma", "@prisma",
                     "sequelize", "mongoose", "@nestjs", "express", "next", "react", "vue", "@angular", "org.springframework",
                     "jakarta.persistence", "javax.persistence", "org.hibernate", "io.quarkus", "microsoft.entityframeworkcore",
                     "microsoft.aspnetcore", "gorm.io", "github.com/gin-gonic", "github.com/labstack/echo", "illuminate", "activerecord",
                     "androidx", "android.")


def read_text(project, rel, limit=MAX_FILE_BYTES):
    try:
        with open(os.path.join(project, rel), encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return ""


# ------------------------------------------------------------------ estilos
def segments(path):
    """Segmentos em minusculas; separa tambem por ponto (nomes de projeto .NET/Java: Loja.Pedidos.Domain)."""
    return [p.lower() for p in re.split(r"[\\/.]", path) if p]


def module_dependencies(project, files, modules):
    """Imports de um modulo para outro. Camada de aplicacao/API do outro modulo e a API publica dele (permitido);
    dominio ou infraestrutura do outro modulo e violacao da fronteira. So nomes que aparecem como segmento do import."""
    names = {m: m.rsplit("/", 1)[-1].lower() for m in modules}
    out, scanned = [], 0
    for m in modules:
        own = [f for f in files if f.startswith(m + "/") and os.path.splitext(f)[1] in IMPORT_RES and not TEST_RE.search(f)]
        for rel in own[:MAX_IMPORT_FILES]:
            text = read_text(project, rel)
            scanned += 1
            for rx in IMPORT_RES[os.path.splitext(rel)[1]]:
                for mt in rx.finditer(text):
                    imp = mt.group(1)
                    segs = set(segments(import_target(rel, imp)))
                    for other, name in names.items():
                        if other == m or name not in segs:
                            continue
                        to_layer = layer_of(import_target(rel, imp))
                        out.append({"from_module": names[m], "to_module": name, "file": rel,
                                    "line": text.count("\n", 0, mt.start()) + 1, "import": imp,
                                    "to_layer": to_layer or "unknown",
                                    "allowed": to_layer not in ("domain", "infrastructure")})
    return out, scanned


# ------------------------------------------------------------------ regra de dependencia
IMPORT_RES = aisef_imports.IMPORT_RES  # fonte unica desde a 0.13 (G-06)


def is_framework(imp, fw):
    if fw.endswith((".", "/")):
        return imp.startswith(fw)
    return imp == fw or imp.startswith(fw + ".") or imp.startswith(fw + "/")


def layers_in(path_like):
    out = []
    for s in segments(path_like):
        for layer, names in LAYER_ALIASES.items():
            if s in names:
                out.append(layer)
    return out


def layer_of(path_like):
    """Camada pelo segmento mais interno que casa com um alias (src/orders/domain/x.py -> domain). Excecao: dentro de
    uma pasta de infraestrutura, tudo e infraestrutura (Infrastructure/Domain/... e o mapeamento do dominio, nao ele)."""
    found = layers_in(path_like)
    if not found:
        return None
    return "infrastructure" if "infrastructure" in found[:-1] else found[-1]


def import_target(rel, imp):
    """Caminho comparavel do import: relativo resolvido contra o arquivo; absoluto como segmentos."""
    if imp.startswith("."):
        base = os.path.dirname(rel)
        return os.path.normpath(os.path.join(base, imp)).replace(os.sep, "/")
    return re.sub(r"[.:\\]+", "/", imp)


def dependency_violations(project, files, styles):
    """Regra de dependencia: camada interna nao importa camada externa nem framework. So roda quando ha camadas."""
    layered = [f for f in files if os.path.splitext(f)[1] in IMPORT_RES and not TEST_RE.search(f) and layer_of(os.path.dirname(f))]
    if not any(layer_of(os.path.dirname(f)) == "domain" for f in layered):
        return [], 0
    violations, scanned = [], 0
    for rel in layered[:MAX_IMPORT_FILES]:
        src_layer = layer_of(os.path.dirname(rel))
        text = read_text(project, rel)
        scanned += 1
        for rx in IMPORT_RES[os.path.splitext(rel)[1]]:
            for m in rx.finditer(text):
                imp = m.group(1)
                line = text.count("\n", 0, m.start()) + 1
                low = imp.lower().replace("\\", ".")
                if src_layer == "domain" and any(is_framework(low, fw) for fw in FRAMEWORK_IMPORTS):
                    violations.append({"rule": "domain-imports-framework", "file": rel, "line": line, "import": imp,
                                       "from_layer": src_layer, "to_layer": "framework", "severity": "high"})
                    continue
                tgt_layer = layer_of(import_target(rel, imp))
                if tgt_layer and tgt_layer in layers_in(os.path.dirname(rel)):
                    continue  # mesmo projeto ou pasta-mae (ex.: Application dentro de Ordering.API): nao cruza camada
                if tgt_layer and LAYER_RANK[tgt_layer] > LAYER_RANK[src_layer]:
                    violations.append({"rule": "inner-imports-outer", "file": rel, "line": line, "import": imp,
                                       "from_layer": src_layer, "to_layer": tgt_layer, "severity": "high"})
    return violations, scanned


# ------------------------------------------------------------------ recomendacoes
def recommend(stacks, styles, violations, files, ext_count):
    recs = []
    sids = {s["id"] for s in styles if s["confidence"] >= 0.5}
    n_src = sum(ext_count.values())
    n_tests = sum(1 for f in files if os.path.splitext(f)[1] in SOURCE_EXT and TEST_RE.search(f))

    def add(rid, title, why, impact, effort, suggested):
        recs.append({"id": rid, "title": title, "why": why, "impact": impact, "effort": effort, "suggested": suggested})

    if violations:
        add("REC-DEPENDENCY-RULE", "Corrigir a regra de dependencia",
            "%d import(s) de camada interna para externa ou para framework (ex.: %s:%d importa %s)" % (
                len(violations), violations[0]["file"], violations[0]["line"], violations[0]["import"]),
            "high", "medium", ["architecture-reviewer", "architect", "practice:architecture/clean-architecture"])
    if not sids and n_src >= 40:
        add("REC-DEFINE-STYLE", "Definir e registrar um estilo de arquitetura",
            "%d arquivos-fonte sem estrutura reconhecivel de camadas ou modulos" % n_src, "high", "medium",
            ["architect", "practice:architecture/layered-mvc", "practice:architecture/modular-monolith", "practice:architecture/vertical-slices"])
    if "layered-mvc" in sids and not sids & {"clean", "hexagonal", "ddd-tactical"}:
        add("REC-MVC-SERVICE-LAYER", "Tirar regra de negocio de controllers e modelos",
            "estrutura MVC detectada; regras de negocio tendem a se espalhar por controllers e modelos conforme o projeto cresce",
            "medium", "medium", ["architect", "architecture-reviewer", "practice:architecture/layered-mvc", "practice:architecture/clean-architecture"])
    if "ddd-tactical" in sids and "ddd-strategic" not in sids:
        add("REC-DDD-GLOSSARY", "Registrar a linguagem ubiqua e os contextos delimitados",
            "padroes taticos de DDD sem glossario (CONTEXT.md) nem contextos explicitos", "medium", "low",
            ["domain", "skill:mattpocock-skills:domain-modeling", "practice:architecture/ddd-strategic"])
    if sids & {"clean", "hexagonal"} and "ddd-tactical" not in sids:
        add("REC-CONSIDER-DDD", "Avaliar DDD tatico no nucleo, se o dominio for rico",
            "camadas limpas detectadas; se ha regras de negocio complexas, agregados e objetos de valor protegem invariantes. Em CRUD simples, nao vale o custo",
            "medium", "high", ["architect", "practice:architecture/ddd-tactical"])
    if "cqrs" in sids:
        add("REC-CQRS-SEPARATION", "Conferir a separacao entre comandos e consultas",
            "CQRS detectado: comando nao devolve dado de leitura e consulta nao muda estado", "medium", "low",
            ["architecture-reviewer", "practice:architecture/cqrs-es"])
    if "microservices" in sids:
        add("REC-SERVICE-BOUNDARIES", "Conferir fronteiras e dados por servico",
            "varios servicos detectados: cada um com o proprio banco e contrato explicito (OpenAPI, AsyncAPI, protobuf)",
            "high", "medium", ["architect", "practice:architecture/microservices", "practice:architecture/contract-first"])
    if n_src >= 10 and n_tests == 0:
        add("REC-TESTS", "Criar a base de testes e adotar TDD nas fatias",
            "%d arquivos-fonte e nenhum teste encontrado" % n_src, "high", "medium",
            ["implementer", "pr-test-analyzer", "practice:common/testing"])
    return recs


def summary(doc):
    out = ["Stacks: " + (", ".join(s["name"] for s in doc["stacks"]) or "nenhuma reconhecida")
           + (" (gerenciador: %s)" % doc["package_manager"] if doc["package_manager"] else "")]
    if doc["styles"]:
        out.append("Arquitetura (heuristica, confirmar com o usuario):")
        out += ["  - %s: confianca %.2f (%s)" % (s["name"], s["confidence"], "; ".join(s["evidence"][:2])) for s in doc["styles"]]
    else:
        out.append("Arquitetura: nenhum estilo reconhecido")
    if doc["violations"]:
        out.append("Violacoes da regra de dependencia: %d" % len(doc["violations"]))
        out += ["  - %s:%d %s -> %s (%s)" % (v["file"], v["line"], v["from_layer"], v["to_layer"], v["import"]) for v in doc["violations"][:5]]
    mods = doc.get("modules") or {}
    if mods.get("roots"):
        deps_ = mods["dependencies"]
        pairs = sorted({"%s -> %s (%s%s)" % (d["from_module"], d["to_module"], d["to_layer"], "" if d["allowed"] else ", VIOLACAO")
                        for d in deps_})
        out.append("Fronteiras entre modulos: %d modulo(s), %d arquivo(s) analisados, %d dependencia(s) entre modulos%s"
                   % (len(mods["roots"]), mods["files_scanned"], len(deps_), (": " + "; ".join(pairs[:6])) if pairs else ""))
    if doc["recommendations"]:
        out.append("Recomendacoes (decisao do usuario):")
        out += ["  - %s: %s. %s" % (r["id"], r["title"], r["why"]) for r in doc["recommendations"]]
    out.append("Praticas aplicaveis: " + ", ".join(doc["practices"]))
    return "\n".join(out)
