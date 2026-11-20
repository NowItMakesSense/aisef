#!/usr/bin/env python3
"""AISEF: detecta stack, estilo de arquitetura e violacoes da regra de dependencia de um projeto, e recomenda melhorias.

So biblioteca padrao, sem modelo e sem rede. Le o repositorio (ignora dependencias, build e pastas ocultas) e grava
`.aisef/architecture.json` (schema architecture.schema.v0.1.json). Tudo e **heuristica com evidencia e confianca**:
nome de pasta nao prova estilo. O orquestrador confirma com o usuario, e o estilo adotado vira ADR aprovado.

Uso:
    python3 -I aisef_detect.py detect --project REPO [--write] [--json]
    python3 -I aisef_detect.py deps   --project REPO [--json]     (so as violacoes da regra de dependencia; sai 1 se houver)
"""
import argparse
import datetime
import fnmatch
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STACKS_PATH = os.path.join(HERE, "detect", "stacks.v0.1.json")
SCHEMA = "architecture.schema.v0.1.json"

IGNORE_DIRS = {"node_modules", ".git", ".hg", ".svn", "venv", ".venv", "env", "__pycache__", "dist", "build", "out", "target",
               "vendor", "bin", "obj", ".next", ".nuxt", ".dart_tool", ".gradle", ".idea", ".vscode", "coverage", ".aisef",
               "graphify-out", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", "Pods", "DerivedData", ".terraform",
               "site-packages", ".cache", "tmp", "temp", "logs"}
SOURCE_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rs", ".java", ".kt", ".kts", ".swift", ".cs", ".fs",
              ".cpp", ".cc", ".cxx", ".hpp", ".hh", ".h", ".c", ".php", ".rb", ".dart", ".gd", ".ets", ".vue", ".svelte", ".scala"}
TEST_RE = re.compile(r"(^|[\\/])(tests?|__tests__|spec|specs)([\\/]|$)|(_test|\.test|\.spec|Test|Tests|_spec)\.[a-z]+$|^test_.*\.py$")
MAX_FILES = 60000
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
STYLES = {
    "clean": ("Clean Architecture / Onion", [({"domain"}, 1), ({"application", "usecases", "use_cases", "usecase", "use-cases", "interactors"}, 2),
                                             ({"infrastructure", "infra", "persistence"}, 1),
                                             ({"presentation", "delivery", "rest"}, 1), ({"repository", "repositories"}, 1)], 4),
    "hexagonal": ("Hexagonal (ports and adapters)", [({"ports", "port"}, 2), ({"adapters", "adapter"}, 2),
                                                     ({"inbound", "outbound", "driving", "driven", "primary", "secondary"}, 1)], 4),
    "ddd-tactical": ("DDD tatico", [({"aggregates", "aggregate"}, 2), ({"valueobjects", "value_objects", "value-objects", "vo"}, 2),
                                    ({"domain_events", "domainevents", "domain-events"}, 2), ({"specifications", "specification"}, 1),
                                    ({"repositories", "repository"}, 1), ({"domain"}, 1)], 4),
    "ddd-strategic": ("DDD estrategico", [({"bounded_contexts", "boundedcontexts", "bounded-contexts", "contexts"}, 3),
                                          ({"anticorruption", "anti_corruption", "acl"}, 2), ({"shared_kernel", "sharedkernel", "shared-kernel"}, 2)], 3),
    "cqrs": ("CQRS", [({"commands", "command"}, 2), ({"queries", "query"}, 2), ({"commandhandlers", "queryhandlers", "handlers"}, 1)], 4),
    "event-sourcing": ("Event sourcing", [({"eventstore", "event_store", "event-store"}, 3), ({"projections", "projection", "projectors"}, 2),
                                          ({"eventsourcing", "event_sourcing"}, 3)], 3),
    "layered-mvc": ("Camadas / MVC", [({"controllers", "controller"}, 2), ({"models", "model"}, 1), ({"views", "templates"}, 1),
                                      ({"services", "service"}, 1), ({"repositories", "repository", "dao"}, 1)], 4),
    "vertical-slices": ("Fatias verticais / feature-sliced", [({"features", "feature", "slices"}, 2), ({"widgets", "pages", "shared", "entities"}, 1)], 3),
    "event-driven": ("Orientado a eventos", [({"consumers", "consumer", "subscribers", "listeners"}, 2), ({"producers", "publishers", "publisher"}, 2),
                                             ({"events", "messaging", "messages"}, 1)], 3),
}
# Sinais por nome de arquivo (cada regex conta como um grupo de sinal do estilo)
FILE_SIGNALS = {
    "ddd-tactical": [(re.compile(r"(?i)aggregate[-_]?root|aggregate\b"), 2),
                     (re.compile(r"(?i)value[-_]?object"), 2),
                     (re.compile(r"(?i)domain[-_]?events?\b"), 2)],
    "hexagonal": [(re.compile(r"(?i)[.-]port\.[a-z]+$|Port\.[a-z]+$"), 2),
                  (re.compile(r"(?i)[.-]adapter\.[a-z]+$|Adapter\.[a-z]+$"), 2)],
}
STYLE_PRACTICE = {"clean": "architecture/clean-architecture", "hexagonal": "architecture/hexagonal", "ddd-tactical": "architecture/ddd-tactical",
                  "ddd-strategic": "architecture/ddd-strategic", "cqrs": "architecture/cqrs-es", "event-sourcing": "architecture/cqrs-es",
                  "layered-mvc": "architecture/layered-mvc", "vertical-slices": "architecture/vertical-slices",
                  "modular-monolith": "architecture/modular-monolith", "microservices": "architecture/microservices",
                  "event-driven": "architecture/event-driven"}
BROKER_DEPS = {"kafkajs", "kafka-python", "confluent-kafka", "amqplib", "pika", "nats", "nats.py", "@aws-sdk/client-sqs", "bullmq",
               "celery", "rabbitmq", "spring-kafka", "spring-rabbit", "masstransit", "sarama"}
FRAMEWORK_IMPORTS = ("django", "flask", "fastapi", "sqlalchemy", "sqlmodel", "pydantic_settings", "typeorm", "prisma", "@prisma",
                     "sequelize", "mongoose", "@nestjs", "express", "next", "react", "vue", "@angular", "org.springframework",
                     "jakarta.persistence", "javax.persistence", "org.hibernate", "io.quarkus", "microsoft.entityframeworkcore",
                     "microsoft.aspnetcore", "gorm.io", "github.com/gin-gonic", "github.com/labstack/echo", "illuminate", "activerecord",
                     "androidx", "android.")


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


def load_stacks():
    with open(STACKS_PATH, encoding="utf-8") as fh:
        return json.load(fh)["stacks"]


# ------------------------------------------------------------------ varredura
def scan(project):
    """Lista arquivos relativos (com '/') e diretorios, ignorando dependencias, build e ocultos."""
    files, dirs = [], set()
    for root, dnames, fnames in os.walk(project):
        dnames[:] = sorted(d for d in dnames if d not in IGNORE_DIRS and not d.startswith("."))
        rel = os.path.relpath(root, project).replace(os.sep, "/")
        if rel != ".":
            dirs.add(rel)
        for f in sorted(fnames):
            files.append(f if rel == "." else rel + "/" + f)
            if len(files) >= MAX_FILES:
                return files, dirs, True
    return files, dirs, False


def read_text(project, rel, limit=MAX_FILE_BYTES):
    try:
        with open(os.path.join(project, rel), encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return ""


def manifest_deps(project, files):
    """Nomes de dependencias por ecossistema, lidos dos manifests (sem resolver versoes)."""
    deps = {"python": set(), "node": set(), "jvm": set(), "php": set(), "ruby": set(), "dart": set()}
    for rel in files:
        if rel.count("/") > 3:
            continue
        base = rel.rsplit("/", 1)[-1]
        if base == "package.json":
            try:
                doc = json.loads(read_text(project, rel))
                for k in ("dependencies", "devDependencies", "peerDependencies"):
                    deps["node"].update((doc.get(k) or {}).keys())
            except ValueError:
                pass
        elif fnmatch.fnmatch(base, "requirements*.txt"):
            for m in re.finditer(r"(?m)^\s*([A-Za-z0-9_.\-]+)", read_text(project, rel)):
                deps["python"].add(m.group(1).lower().replace("_", "-"))
        elif base in ("pyproject.toml", "setup.py", "setup.cfg", "Pipfile"):
            text = read_text(project, rel)
            # especificacoes entre aspas ("fastapi>=0.110", 'django') e linhas "nome = versao" (Pipfile, poetry)
            for m in re.finditer(r"""['"]([A-Za-z0-9_.\-]+)\s*(?:\[[^\]]*\])?\s*(?:[<>=~!;@][^'"]*)?['"]""", text):
                deps["python"].add(m.group(1).lower().replace("_", "-"))
            for m in re.finditer(r"(?m)^\s*([A-Za-z0-9_.\-]+)\s*=\s*[\"'{\[]", text):
                deps["python"].add(m.group(1).lower().replace("_", "-"))
        elif base in ("pom.xml", "build.gradle", "build.gradle.kts"):
            deps["jvm"].update(re.findall(r"[a-z0-9.\-]*(spring-boot|quarkus|kotlin)[a-z0-9.\-]*", read_text(project, rel).lower()))
        elif base == "composer.json":
            try:
                doc = json.loads(read_text(project, rel))
                deps["php"].update((doc.get("require") or {}).keys())
            except ValueError:
                pass
        elif base == "Gemfile":
            deps["ruby"].update(re.findall(r"""^\s*gem\s+['"]([^'"]+)""", read_text(project, rel), re.M))
        elif base == "pubspec.yaml":
            deps["dart"].update(re.findall(r"^\s{2}([a-z_][a-z0-9_]*):", read_text(project, rel), re.M))
    return deps


def detect_stacks(project, files, deps):
    found = []
    ext_count = {}
    for rel in files:
        ext = os.path.splitext(rel)[1].lower()
        if ext in SOURCE_EXT:
            ext_count[ext] = ext_count.get(ext, 0) + 1
    total_src = sum(ext_count.values()) or 1
    shallow = [f for f in files if f.count("/") <= 3]
    for s in load_stacks():
        ev = []
        for pat in s.get("markers", []):
            hit = next((f for f in shallow if fnmatch.fnmatch(f.rsplit("/", 1)[-1], pat) or fnmatch.fnmatch(f, pat)), None)
            if hit:
                ev.append("arquivo " + hit)
        for eco, names in (s.get("deps") or {}).items():
            for n in names:
                if n in deps.get(eco, ()) or any(d == n or d.startswith(n + "-") for d in deps.get(eco, ())):
                    ev.append("dependencia %s (%s)" % (n, eco))
        n_ext = sum(ext_count.get(e, 0) for e in s.get("extensions", []))
        if n_ext >= 3 and n_ext / total_src >= 0.05:
            ev.append("%d arquivos %s" % (n_ext, "/".join(s["extensions"])))
        # framework so conta com marcador ou dependencia; linguagem tambem por arquivos-fonte
        if s["kind"] == "framework" and not any(e.startswith(("arquivo", "dependencia")) for e in ev):
            continue
        if s["id"] == "javascript" and ev and all(e.startswith("arquivo") for e in ev) and ext_count.get(".ts", 0) + ext_count.get(".tsx", 0) > ext_count.get(".js", 0):
            continue  # projeto TypeScript com package.json: nao listar JavaScript a parte
        if ev:
            found.append({"id": s["id"], "name": s["name"], "kind": s["kind"], "evidence": ev[:5]})
    return found, ext_count


def package_manager(files):
    root = set(f.rsplit("/", 1)[-1] for f in files if f.count("/") <= 1)
    for lock, pm in (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"), ("bun.lockb", "bun"), ("bun.lock", "bun"),
                     ("package-lock.json", "npm"), ("poetry.lock", "poetry"), ("uv.lock", "uv"), ("Pipfile.lock", "pipenv"),
                     ("requirements.txt", "pip"), ("Cargo.lock", "cargo"), ("go.sum", "go"), ("composer.lock", "composer"),
                     ("Gemfile.lock", "bundler"), ("pubspec.lock", "pub")):
        if lock in root:
            return pm
    return None


def stack_commands(stack_ids):
    """Comandos sugeridos por stack (build, test, lint, typecheck), para o verify-loop e o precheck."""
    return {s["id"]: s["commands"] for s in load_stacks() if s["id"] in stack_ids and s.get("commands")}


# ------------------------------------------------------------------ estilos
def segments(path):
    """Segmentos em minusculas; separa tambem por ponto (nomes de projeto .NET/Java: Loja.Pedidos.Domain)."""
    return [p.lower() for p in re.split(r"[\\/.]", path) if p]


def detect_styles(project, files, dirs, deps):
    seg_paths = {}
    for d in sorted(dirs):
        for s in segments(d):
            seg_paths.setdefault(s, d)
    styles = []
    for sid, (name, groups, threshold) in STYLES.items():
        score, ev, hit_groups = 0, [], 0
        for names, weight in groups:
            hit = next((n for n in sorted(names) if n in seg_paths), None)
            if hit:
                score += weight
                hit_groups += 1
                ev.append("pasta " + seg_paths[hit])
        if sid == "cqrs" and not ({"commands", "command"} & set(seg_paths) and {"queries", "query"} & set(seg_paths)):
            continue  # CQRS exige os dois lados
        if sid == "event-driven" and any(d in BROKER_DEPS for eco in deps.values() for d in eco):
            score += 2
            ev.append("dependencia de broker de mensagens")
        if sid == "ddd-strategic":
            for f in files:
                if f.rsplit("/", 1)[-1].upper() in ("CONTEXT.MD", "GLOSSARY.MD", "UBIQUITOUS_LANGUAGE.MD", "CONTEXT-MAP.MD") and f.count("/") <= 2:
                    score += 2
                    ev.append("arquivo " + f)
                    break
        if sid in FILE_SIGNALS:
            names = [f.rsplit("/", 1)[-1] for f in files if os.path.splitext(f)[1] in SOURCE_EXT]
            for rx, weight in FILE_SIGNALS[sid]:
                hits = [n for n in names if rx.search(n)]
                if hits:
                    score += weight
                    hit_groups += 1
                    ev.append("arquivos %s" % ", ".join(hits[:3]))
        if hit_groups < 2 and sid not in ("ddd-strategic", "event-sourcing"):
            continue  # um sinal isolado (ex.: so "models") nao basta
        if score:
            conf = round(min(1.0, score / float(threshold * 1.5)), 2)
            if conf >= 0.3:
                styles.append({"id": sid, "name": name, "confidence": conf, "evidence": ev[:5]})
    mm = modular_monolith(dirs)
    if mm:
        styles.append(mm)
    ms = microservices(files, dirs)
    if ms:
        styles.append(ms)
    return sorted(styles, key=lambda s: -s["confidence"])


def children(dirs, parent):
    return sorted(d for d in dirs if d.startswith(parent + "/") and d.count("/") == parent.count("/") + 1)


def module_roots(dirs):
    """Pastas de modulo do monolito modular (filhas de modules/, contexts/...), ou [] se nao houver."""
    parents = sorted((d for d in dirs if d.rsplit("/", 1)[-1].lower() in
                      ("modules", "contexts", "boundedcontexts", "bounded_contexts", "bounded-contexts")), key=len)
    for parent in parents:
        kids = children(dirs, parent)
        if len(kids) >= 2:
            return kids
    return []


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


def modular_monolith(dirs):
    parents = sorted((d for d in dirs if d.rsplit("/", 1)[-1].lower() in
                      ("modules", "contexts", "boundedcontexts", "bounded_contexts", "bounded-contexts")), key=len)
    for parent in parents:
        kids = children(dirs, parent)
        if len(kids) >= 2:
            layered = [k for k in kids if any(d.startswith(k + "/") and segments(d)[-1] in
                                              {"domain", "application", "infrastructure", "api", "public"} for d in dirs)]
            conf = 0.5 + (0.3 if len(layered) >= 2 else 0) + (0.1 if len(kids) >= 4 else 0)
            return {"id": "modular-monolith", "name": "Monolito modular", "confidence": round(min(conf, 1.0), 2),
                    "evidence": ["%d modulos em %s/" % (len(kids), parent)] + ["modulo com camadas: " + k for k in layered[:3]]}
    return None


MIN_SERVICE_FILES = 5


def microservices(files, dirs):
    manifests = ("package.json", "pyproject.toml", "go.mod", "pom.xml", "build.gradle", "build.gradle.kts", "Cargo.toml", "Dockerfile",
                 "*.csproj", "*.fsproj")
    named = ("services", "apps", "microservices")
    deployable = re.compile(r"(?i)(?:^|[._-])(?:api|service|svc|worker|processor)$")
    parents = sorted(set(dirs) | {""}, key=lambda d: (d.rsplit("/", 1)[-1].lower() not in named, len(d)))
    for parent in parents:
        kids = children(dirs, parent) if parent else sorted(d for d in dirs if "/" not in d)
        own = [k for k in kids if any(f.startswith(k + "/") and f.count("/") == k.count("/") + 1
                                      and any(fnmatch.fnmatch(f.rsplit("/", 1)[-1], m) for m in manifests) for f in files)]
        if parent.rsplit("/", 1)[-1].lower() not in named:
            # pasta qualquer: so conta servico com nome de servico implantavel (Ordering.API, billing-service, x-worker)
            own = [k for k in own if deployable.search(k.rsplit("/", 1)[-1])]
            if len(own) < 3:
                continue
        if len(own) >= 2:
            ev = ["%d servicos com manifest proprio em %s/" % (len(own), parent)]
            compose = [f for f in files if fnmatch.fnmatch(f.rsplit("/", 1)[-1], "docker-compose*.y*ml") or f.rsplit("/", 1)[-1] in ("compose.yaml", "compose.yml")]
            if compose:
                ev.append("arquivo " + compose[0])
            # servico com pouco codigo (so um Program.cs ou health check) e esqueleto, nao microsservico de fato
            size = {k: sum(1 for f in files if f.startswith(k + "/") and os.path.splitext(f)[1] in SOURCE_EXT and not TEST_RE.search(f))
                    for k in own}
            real = [k for k in own if size[k] >= MIN_SERVICE_FILES]
            thin = [k for k in own if size[k] < MIN_SERVICE_FILES]
            if thin:
                ev.append("%d servico(s) com menos de %d arquivos de codigo (esqueleto?): %s"
                          % (len(thin), MIN_SERVICE_FILES, ", ".join(k.rsplit("/", 1)[-1] for k in thin[:4])))
            conf = 0.5 + 0.1 * len(real) if len(real) >= 2 else 0.35 + 0.05 * len(real)
            return {"id": "microservices", "name": "Microsservicos", "confidence": round(min(1.0, conf), 2), "evidence": ev}
    return None


# ------------------------------------------------------------------ regra de dependencia
IMPORT_RES = {
    ".py": [re.compile(r"^\s*from\s+([\w.]+)\s+import", re.M), re.compile(r"^\s*import\s+([\w.]+)", re.M)],
    ".ts": [re.compile(r"""(?:import|export)\s[^'"]*?from\s+['"]([^'"]+)['"]"""), re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)"""),
            re.compile(r"""^\s*import\s+['"]([^'"]+)['"]""", re.M)],
    ".java": [re.compile(r"^\s*import\s+(?:static\s+)?([\w.]+)", re.M)],
    ".cs": [re.compile(r"^\s*using\s+(?:static\s+)?([\w.]+)\s*;", re.M)],
    ".go": [re.compile(r"""^\s*(?:import\s+)?(?:\w+\s+)?"([^"]+)"\s*$""", re.M)],
    ".php": [re.compile(r"^\s*use\s+([\w\\]+)", re.M)],
    ".rb": [re.compile(r"""^\s*require(?:_relative)?\s+['"]([^'"]+)['"]""", re.M)],
    ".dart": [re.compile(r"""^\s*import\s+['"]([^'"]+)['"]""", re.M)],
    ".rs": [re.compile(r"^\s*use\s+([\w:]+)", re.M)],
}
for _e in (".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte"):
    IMPORT_RES[_e] = IMPORT_RES[".ts"]
IMPORT_RES[".kt"] = IMPORT_RES[".java"]
IMPORT_RES[".scala"] = IMPORT_RES[".java"]


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


# ------------------------------------------------------------------ orquestracao
def detect(project):
    files, dirs, truncated = scan(project)
    deps = manifest_deps(project, files)
    stacks, ext_count = detect_stacks(project, files, deps)
    styles = detect_styles(project, files, dirs, deps)
    violations, scanned = dependency_violations(project, files, styles)
    modules = module_roots(dirs)
    mod_deps, mod_scanned = module_dependencies(project, files, modules) if modules else ([], 0)
    for d in mod_deps:
        if not d["allowed"]:
            violations.append({"rule": "cross-module-internal", "file": d["file"], "line": d["line"], "import": d["import"],
                               "from_layer": layer_of(os.path.dirname(d["file"])) or "application",
                               "to_layer": d["to_layer"], "severity": "high"})
    stack_ids = [s["id"] for s in stacks]
    layers = {}
    for d in sorted(dirs):
        lay = layer_of(d)
        if lay and segments(d)[-1] in LAYER_ALIASES[lay] and len(layers.setdefault(lay, [])) < 10:
            layers[lay].append(d)
    domains = []
    if "pytorch" in stack_ids or any(d in deps["python"] for d in ("scikit-learn", "tensorflow", "xgboost", "lightgbm")):
        domains.append("ml")
    if any(d in deps["python"] | deps["node"] for d in ("langchain", "llama-index", "chromadb", "faiss-cpu", "pinecone-client",
                                                         "@pinecone-database/pinecone", "qdrant-client", "weaviate-client", "pgvector")):
        domains.append("rag")
    practices = ["common"]
    for s in load_stacks():
        if s["id"] in stack_ids:
            practices += [p for p in s.get("practices", []) if p not in practices]
    practices += [STYLE_PRACTICE[s["id"]] for s in styles if s["confidence"] >= 0.5 and s["id"] in STYLE_PRACTICE
                  and STYLE_PRACTICE[s["id"]] not in practices]
    n_tests = sum(1 for f in files if os.path.splitext(f)[1] in SOURCE_EXT and TEST_RE.search(f))
    return {
        "schema_version": "0.1.0",
        "generated_at": now_iso(),
        "generated_by": "aisef_detect",
        "scan": {"files": len(files), "source_files": sum(ext_count.values()), "test_files": n_tests,
                 "import_files_scanned": scanned, "truncated": truncated},
        "stacks": stacks,
        "package_manager": package_manager(files),
        "commands": stack_commands(stack_ids),
        "styles": styles,
        "layers": layers,
        "violations": violations[:200],
        "modules": {"roots": modules, "files_scanned": mod_scanned,
                    "dependencies": [{k: d[k] for k in ("from_module", "to_module", "to_layer", "allowed", "file", "line")}
                                     for d in mod_deps][:200]},
        "domains": domains,
        "practices": practices,
        "recommendations": recommend(stacks, styles, violations, files, ext_count),
    }


def write(project, doc):
    path = os.path.join(project, ".aisef", "architecture.json")
    old = None
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            old = json.load(fh)
    if old and old.get("approved") and not doc.get("approved"):
        doc["approved"] = old["approved"]  # a decisao do usuario sobrevive a uma nova deteccao
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return path


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


def main(argv=None):
    ap = argparse.ArgumentParser(description="AISEF: deteccao de stack e arquitetura")
    ap.add_argument("command", choices=["detect", "deps"])
    ap.add_argument("--project", default=".")
    ap.add_argument("--write", action="store_true", help="grava .aisef/architecture.json")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    project = os.path.abspath(a.project)
    doc = detect(project)
    if a.command == "deps":
        if a.json:
            print(json.dumps(doc["violations"], ensure_ascii=False, indent=2))
        else:
            for v in doc["violations"]:
                print("%s:%d  %s -> %s  (%s)" % (v["file"], v["line"], v["from_layer"], v["to_layer"], v["import"]))
            print("%d violacao(oes) da regra de dependencia" % len(doc["violations"]))
        return 1 if doc["violations"] else 0
    if a.write:
        print("gravado " + write(project, doc), file=sys.stderr)
    print(json.dumps(doc, ensure_ascii=False, indent=2) if a.json else summary(doc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
