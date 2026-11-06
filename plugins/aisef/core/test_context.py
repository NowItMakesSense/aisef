#!/usr/bin/env python3
"""Testes do context engineering (aisef_context.py, check_knowledge.py, knowledge-entry.schema).
Projeto de demonstracao (make_demo_project) + mutacoes; cobre pack, remember e check_knowledge."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_demo_project as demo  # noqa: E402
import aisef_context as ctx  # noqa: E402
import check_knowledge as ck  # noqa: E402

work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
fails = total = 0
CTX = os.path.join(HERE, "aisef_context.py")
CK = os.path.join(HERE, "check_knowledge.py")


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)))
    fails += not cond


def mkproject(name):
    proj = os.path.join(work, name)
    demo.make(os.path.join(proj, ".aisef"))
    with open(os.path.join(proj, ".aisef", "config.json"), "w", encoding="utf-8") as fh:
        json.dump({"project_id": "PRJ-T", "schema_version": "0.1.0"}, fh)
    return proj


def put(proj, rel, text="x = 1\n"):
    p = os.path.join(proj, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)


def load(proj, rel):
    with open(os.path.join(proj, ".aisef", rel), encoding="utf-8") as fh:
        return json.load(fh)


def edit(proj, rel, fn):
    d = load(proj, rel)
    fn(d)
    with open(os.path.join(proj, ".aisef", rel), "w", encoding="utf-8") as fh:
        json.dump(d, fh)


def exits(fn):
    """Mensagem do SystemExit, ou None se a funcao terminou normalmente."""
    try:
        fn()
        return None
    except SystemExit as e:
        return str(e)


def run(*args):
    return subprocess.run([sys.executable, "-I"] + list(args), capture_output=True, text=True, encoding="utf-8")


# ------------------------------------------------------------------ pack: camadas
p = mkproject("a")
for rel in ("src/auth/token.py", "src/auth/verify.py", "tests/auth/test_token.py", "src/other/x.py", "node_modules/auth/y.py"):
    put(p, rel)
put(p, "docs/auth.md", "# auth\n")
pack = ctx.build_pack(p, "T-001")
m, r, o = pack["mandatory"], pack["referenced"], pack["on_demand"]
check("pack/obrigatorio: caminho do Task Contract", m["task_contract"] == ".aisef/contracts/tasks/T-001.json")
check("pack/obrigatorio: texto do requisito ligado (so o REQ-001)",
      [x["id"] for x in m["requirements"]] == ["REQ-001"] and m["requirements"][0]["statement"] == "Gerar access token valido")
check("pack/obrigatorio: criterio de aceite com metodo e evidencia",
      m["acceptance_criteria"][0]["id"] == "AC-1" and m["acceptance_criteria"][0]["method"] == "automated_test")
check("pack/decisoes: ADR aprovado (RS256) com a aprovacao de origem",
      [(d["id"], d["chosen"], d["approval"]) for d in m["decisions"]] == [("ADR-001", "RS256", "APR-000")], m["decisions"])
ids = {e["id"] for e in m["blueprint"]["elements"]}
check("pack/blueprint: so elementos que citam os requisitos da tarefa",
      m["blueprint"]["id"] == "BP-001" and {"C-API", "EP-1"} <= ids and "EP-2" not in ids, ids)
check("pack/referenciado: arquivos que casam, sem node_modules nem o que esta fora do caminho",
      r["files"] == ["src/auth/token.py", "src/auth/verify.py", "tests/auth/test_token.py"] and r["truncated"] == 0, r)
check("pack/sob demanda: sem .mcp.json, nenhum grafo", o["graph"]["configured"] == [] and o["graph"]["queries"] == [])
check("pack: sem avisos no projeto de demonstracao", pack["warnings"] == [], pack["warnings"])
txt = ctx.render_pack(pack)
check("pack: texto legivel traz as tres camadas", all(s in txt for s in ("## 1. Obrigatorio", "## 2. Referenciado", "## 3. Sob demanda")))

# ------------------------------------------------------------------ pack: limite
lim = ctx.build_pack(p, "T-001", limit=2)["referenced"]
check("pack/limite: corta e conta o que cortou", len(lim["files"]) == 2 and lim["truncated"] == 1 and lim["matched_total"] == 3, lim)
zero = ctx.build_pack(p, "T-001", limit=0)["referenced"]
check("pack/limite 0: nenhum arquivo listado, tudo contado como cortado", zero["files"] == [] and zero["truncated"] == 3, zero)
edit(p, "contracts/tasks/T-001.json", lambda t: t["scope"].update(paths_forbidden=["src/auth/verify.py"]))
check("pack/paths_forbidden: arquivo proibido nao entra", "src/auth/verify.py" not in ctx.build_pack(p, "T-001")["referenced"]["files"])

# ------------------------------------------------------------------ pack: docs citados
edit(p, "blueprints/BP-001.json",
     lambda b: b["architecture"]["components"][0].update(responsibility="Emitir tokens (ver docs/auth.md e docs/nao-existe.md)"))
edit(p, "contracts/tasks/T-001.json",
     lambda t: t["context"].update(referenced=[{"ref": "src/auth/token.py", "origin": "file", "version": "1"}]))
docs = {d["path"]: d["origin"] for d in ctx.build_pack(p, "T-001")["referenced"]["docs"]}
check("pack/docs: citados no blueprint e no contrato, so os que existem",
      docs == {"docs/auth.md": "blueprint", "src/auth/token.py": "task:referenced"}, docs)

# ------------------------------------------------------------------ pack: decisoes
q = mkproject("b")
edit(q, "approvals/APR-000.json", lambda a: a.update(status="pending"))
pk = ctx.build_pack(q, "T-001")
check("pack/decisoes: aprovacao pendente nao conta; avisa que o blueprint cita ADR sem aprovacao",
      pk["mandatory"]["decisions"] == [] and any("ADR-001" in w for w in pk["warnings"]), pk["warnings"])
q = mkproject("b2")
edit(q, "approvals/APR-000.json", lambda a: a["presented"].update(requirement_ids=["REQ-003"]))
edit(q, "blueprints/BP-001.json", lambda b: b["architecture"].update(decisions=[]))
check("pack/decisoes: aprovacao que cita so outros requisitos fica de fora", ctx.build_pack(q, "T-001")["mandatory"]["decisions"] == [])
edit(q, "contracts/tasks/T-001.json", lambda t: t["requirements"].update(architectural_decision_ids=["ADR-001"]))
check("pack/decisoes: mas entra se o Task Contract cita o ADR",
      [d["id"] for d in ctx.build_pack(q, "T-001")["mandatory"]["decisions"]] == ["ADR-001"])
q = mkproject("b3")
edit(q, "approvals/APR-000.json", lambda a: a.update(feature_id="FEAT-999"))
check("pack/decisoes: aprovacao de outra feature nao entra", ctx.build_pack(q, "T-001")["mandatory"]["decisions"] == [])

# ------------------------------------------------------------------ pack: sem blueprint, tarefa inexistente
s = mkproject("c")
os.remove(os.path.join(s, ".aisef", "blueprints", "BP-001.json"))
ps = ctx.build_pack(s, "T-001")
check("pack/sem blueprint: aviso, camada obrigatoria continua e a decisao aprovada da feature entra",
      ps["mandatory"]["blueprint"] is None and any("blueprint" in w for w in ps["warnings"])
      and [d["id"] for d in ps["mandatory"]["decisions"]] == ["ADR-001"] and ps["mandatory"]["requirements"], ps["warnings"])
check("pack/tarefa inexistente: recusa com mensagem", "T-404" in (exits(lambda: ctx.build_pack(s, "T-404")) or ""))

# ------------------------------------------------------------------ pack: grafo
g = mkproject("g")
with open(os.path.join(g, ".mcp.json"), "w", encoding="utf-8") as fh:
    json.dump({"mcpServers": {"codebase-memory-mcp": {"command": "codebase-memory-mcp", "args": []},
                              "graphify": {"command": "python", "args": ["-m", "graphify.serve", "graphify-out/graph.json"]},
                              "other": {"command": "npx", "args": ["foo"]}}}, fh)
gp = ctx.build_pack(g, "T-001")["on_demand"]["graph"]
tools = {x["tool"] for x in gp["queries"]}
check("pack/grafo: detecta codebase-memory e graphify no .mcp.json",
      [x["profile"] for x in gp["configured"]] == ["codebase-memory", "graphify"], gp["configured"])
check("pack/grafo: consultas com os nomes reais mcp__<servidor>__<ferramenta>",
      {"mcp__codebase-memory-mcp__search_graph", "mcp__codebase-memory-mcp__trace_path", "mcp__codebase-memory-mcp__detect_changes",
       "mcp__graphify__query_graph", "mcp__graphify__get_neighbors"} <= tools, tools)
check("pack/grafo: nota de que o graphify ainda nao gerou graph.json", any("graph.json" in n for n in gp["notes"]))
with open(os.path.join(g, ".mcp.json"), "w", encoding="utf-8") as fh:
    fh.write("{quebrado")
check("pack/grafo: .mcp.json quebrado = nenhum grafo, sem excecao", ctx.detect_graph_servers(g) == [])

# ------------------------------------------------------------------ pack: CLI
cli = run(CTX, "pack", "--project", p, "--task", "T-001", "--json")
check("pack/CLI --json: JSON valido e exit 0", cli.returncode == 0 and json.loads(cli.stdout)["task_id"] == "T-001", cli.stderr)
check("pack/CLI: tarefa inexistente sai != 0", run(CTX, "pack", "--project", p, "--task", "T-404").returncode != 0)

# ------------------------------------------------------------------ remember
k = mkproject("k")
path1 = ctx.remember(k, "Tokens expiram em 15 minutos", "file", "src/auth/token.py", tags=["auth", "jwt"], task_id="T-001", feature_id="FEAT-001")
path2 = ctx.remember(k, "O refresh token fica fora do escopo da FEAT-001", "decision", "ADR-001", detail="Decidido na aprovacao APR-000.")
check("remember: ids sequenciais K-001, K-002", os.path.basename(path1) == "K-001.json" and os.path.basename(path2) == "K-002.json")
e1 = load(k, "knowledge/K-001.json")
check("remember: campos do schema (fonte, tags ordenadas, status active, detail = summary)",
      e1["source"] == {"kind": "file", "ref": "src/auth/token.py"} and e1["tags"] == ["auth", "jwt"] and e1["status"] == "active"
      and e1["detail"] == e1["summary"] and e1["task_id"] == "T-001" and e1["created_by"] == "orchestrator", e1)
os.remove(path2)
check("remember: depois de apagar a K-002 o proximo id volta a K-002 (maior + 1)",
      os.path.basename(ctx.remember(k, "Outro fato do projeto", "task", "T-001")) == "K-002.json")

SECRETS = {
    "chave AWS": "usar a chave AKIAABCDEFGHIJKLMNOP no deploy",
    "token GitHub": "token ghp_" + "a" * 36,
    "atribuicao": "password = hunter2hunter2",
    "JWT": "bearer eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0NTY3.SflKxwRJSMeKKF2QT4fw",
    "credencial em URL": "conectar em https://admin:s3nhaforte@host.exemplo.com/db",
    "URL de banco": "usar postgres" + "://host:5432/db",
    "chave privada": "-----BEGIN RSA PRIVATE" + " KEY-----",
}
for label, text in SECRETS.items():
    msg = exits(lambda: ctx.remember(k, "Fato com " + text, "task", "T-001"))
    check("remember: recusa segredo (%s) sem repetir o valor" % label, msg is not None and "segredo" in msg and text[-8:] not in msg, msg)
check("remember: recusa segredo no detalhe",
      "segredo" in (exits(lambda: ctx.remember(k, "Fato sobre auth", "task", "T-001", detail="api_key: abcdef123456")) or ""))
check("remember: recusa arquivo-fonte sensivel", "segredo" in (exits(lambda: ctx.remember(k, "Variaveis ficam no ambiente", "file", ".env.production")) or ""))
check("remember: arquivo de exemplo (.env.example) e permitido",
      exits(lambda: ctx.remember(k, "Variaveis de exemplo ficam no ambiente", "file", ".env.example")) is None)
check("remember: texto que so cita ferramenta de banco nao e falso positivo",
      exits(lambda: ctx.remember(k, "As migrations rodam com psql em dev", "task", "T-001")) is None)
check("remember: os recusados nao gravaram nada",
      sorted(os.listdir(os.path.join(k, ".aisef", "knowledge"))) == ["K-001.json", "K-002.json", "K-003.json", "K-004.json"],
      sorted(os.listdir(os.path.join(k, ".aisef", "knowledge"))))
check("remember/schema: url precisa ser http(s)", "schema" in (exits(lambda: ctx.remember(k, "Fato com fonte url", "url", "ftp://x")) or ""))
check("remember/schema: arquivo-fonte nao pode sair do projeto",
      "schema" in (exits(lambda: ctx.remember(k, "Fato com fonte fora", "file", "../fora.txt")) or ""))
check("remember/schema: summary curto demais", "schema" in (exits(lambda: ctx.remember(k, "oi", "task", "T-001")) or ""))
check("remember: fora de projeto AISEF recusa", exits(lambda: ctx.remember(work, "Fato qualquer aqui", "task", "T-001")) is not None)
new = os.path.basename(ctx.remember(k, "Tokens agora expiram em 30 minutos", "file", "src/auth/token.py", supersedes="K-001"))[:-5]
old = load(k, "knowledge/K-001.json")
check("remember --supersedes: a antiga vira superseded apontando para a nova",
      old["status"] == "superseded" and old["superseded_by"] == new and load(k, "knowledge/%s.json" % new)["supersedes"] == "K-001", old)
cli = run(CTX, "remember", "--project", k, "--summary", "Fato via linha de comando", "--source-kind", "task", "--source-ref", "T-002",
          "--tags", "cli, teste")
check("remember/CLI: grava e imprime o caminho", cli.returncode == 0 and "K-" in cli.stdout, cli.stderr)
check("remember/CLI: segredo sai != 0",
      run(CTX, "remember", "--project", k, "--summary", "Fato com password = hunter2hunter2", "--source-kind", "task", "--source-ref", "T-002").returncode != 0)

# ------------------------------------------------------------------ pack le o conhecimento (sob demanda)
put(k, "src/auth/token.py")
kp = ctx.build_pack(k, "T-001")["on_demand"]
kids = [x["id"] for x in kp["knowledge"]]
check("pack/conhecimento: ativas e relevantes entram (mais pontuadas antes), superseded fica de fora",
      "K-001" not in kids and new in kids and kp["knowledge"][0]["score"] >= kp["knowledge"][-1]["score"], kp["knowledge"])
check("pack/conhecimento: entrada sem relacao nao aparece", all("exemplo" not in x["summary"] for x in kp["knowledge"]))

# ------------------------------------------------------------------ check_knowledge
kn = ck.validate(os.path.join(k, ".aisef"))
check("check_knowledge: memoria gerada pelo remember nao tem erro", [c for c, _, _ in kn if c not in ck.WARNINGS] == [], kn)
check("check_knowledge: sem pasta knowledge, nada a validar", ck.validate(os.path.join(p, ".aisef")) == [])


def codes(proj):
    return {c for c, _, _ in ck.validate(os.path.join(proj, ".aisef"))}


def kcase(name, mut, expect_code, newfile=None):
    proj = mkproject("kc-" + name.split()[0] + str(total))
    ctx.remember(proj, "Fato base para mutacao", "file", "src/a.py", task_id="T-001", feature_id="FEAT-001")
    put(proj, "src/a.py")
    base = codes(proj)
    if newfile:
        with open(os.path.join(proj, ".aisef", "knowledge", newfile[0]), "w", encoding="utf-8") as fh:
            fh.write(newfile[1])
    else:
        edit(proj, "knowledge/K-001.json", mut)
    got = codes(proj)
    check("check_knowledge: %s -> %s" % (name, expect_code), base == set() and expect_code in got, (base, got))
    return proj


kcase("campo obrigatorio ausente", lambda e: e.pop("tags"), "KNW-SCHEMA")
kcase("status invalido", lambda e: e.update(status="x"), "KNW-SCHEMA")
kcase("superseded sem superseded_by", lambda e: e.update(status="superseded"), "KNW-SCHEMA")
kcase("task inexistente", lambda e: e.update(task_id="T-404"), "KNW-TASK-MISSING")
kcase("feature inexistente", lambda e: e.update(feature_id="FEAT-404"), "KNW-FEATURE-MISSING")
kcase("id diverge do arquivo", lambda e: e.update(id="K-009"), "KNW-ID-NAME")
kcase("segredo no detalhe", lambda e: e.update(detail="senha: abcdef123456"), "KNW-SECRET")
kcase("elo quebrado", lambda e: e.update(supersedes="K-777"), "KNW-LINK")
kcase("arquivo-fonte inexistente", lambda e: e["source"].update(ref="src/sumiu.py"), "KNW-SOURCE-FILE-MISSING")
kcase("decisao-fonte desconhecida", lambda e: e.update(source={"kind": "decision", "ref": "ADR-404"}), "KNW-SOURCE-DECISION-UNKNOWN")
kcase("tarefa-fonte inexistente", lambda e: e.update(source={"kind": "task", "ref": "T-404"}), "KNW-SOURCE-TASK-MISSING")
kcase("JSON quebrado", None, "KNW-JSON", newfile=("K-002.json", "{ruim"))
kcase("nome fora do padrao", None, "KNW-FILENAME", newfile=("notas.json", "{}"))
dup = mkproject("kc-dup")
ctx.remember(dup, "Fato base para duplicar", "task", "T-001")
shutil.copy(os.path.join(dup, ".aisef", "knowledge", "K-001.json"), os.path.join(dup, ".aisef", "knowledge", "K-002.json"))
check("check_knowledge: id repetido em outro arquivo (K-002.json com id K-001) -> KNW-ID-NAME", "KNW-ID-NAME" in codes(dup))
warn = mkproject("kc-warn")
ctx.remember(warn, "Fato sobre arquivo que sumiu", "file", "src/sumiu.py")
check("check_knowledge CLI: so aviso -> exit 0; com --strict -> exit 1",
      run(CK, "--project", warn).returncode == 0 and run(CK, "--project", warn, "--strict").returncode == 1)
bad = mkproject("kc-bad")
ctx.remember(bad, "Fato base para quebrar", "task", "T-001")
edit(bad, "knowledge/K-001.json", lambda e: e.pop("tags"))
check("check_knowledge CLI: erro -> exit 1", run(CK, "--project", bad).returncode == 1)

shutil.rmtree(work, ignore_errors=True)
print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
