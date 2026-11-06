#!/usr/bin/env python3
"""Testes do painel: schema de dados, construtor, integridade, saneamento e renderizacao real em Chrome headless.

Uso: python3 -I test_panel.py <diretorio-de-trabalho-temporario>
"""
import copy
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import jsonschema  # noqa: E402

import build_panel  # noqa: E402
import make_demo_project  # noqa: E402

work = sys.argv[1]
shutil.rmtree(work, ignore_errors=True)
os.makedirs(work)

schema = json.load(open(os.path.join(HERE, "panel-data.schema.v0.1.json"), encoding="utf-8"))
jsonschema.Draft202012Validator.check_schema(schema)
validator = jsonschema.Draft202012Validator(schema)
print("panel-data schema: valido (Draft 2020-12)")

results = []


def check(label, cond):
    results.append(bool(cond))
    print(("OK   " if cond else "FALHA"), label)


def fresh(name):
    dest = os.path.join(work, name)
    make_demo_project.make(os.path.join(dest, "project"))
    return dest


def run_build(dest):
    return build_panel.build(os.path.join(dest, "project"), os.path.join(dest, "panel"), HERE)


def edit_json(path, fn):
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    fn(d)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=2)


# ------------------------------------------------------------------ projeto integro
print("--- projeto integro")
base = fresh("base")
b = run_build(base)
errs = list(validator.iter_errors(b))
check("dados do painel validam no schema", not errs)
if errs:
    print("     ", errs[0].message[:200])
check("integridade ok, assinaturas e head verificados",
      b["manifest"]["integrity"]["status"] == "ok" and b["manifest"]["integrity"]["signatures_verified"] and b["manifest"]["integrity"]["head_verified"])
check("manifesto marca a visao como derivada, sem segredos nem raciocinio",
      b["manifest"]["derived"] is True and b["manifest"]["contains_secrets"] is False and b["manifest"]["contains_model_reasoning"] is False)
check("1 feature, 3 tarefas, 2 agentes", (len(b["features"]), len(b["tasks"]), len(b["agents"])) == (1, 3, 2))
f = b["features"][0]
check("progresso da feature: 1 de 3 tarefas concluidas (33%)", (f["tasks_completed"], f["tasks_total"], f["progress_pct"]) == (1, 3, 33))
check("RTM: REQ-001 coberto, REQ-002 em andamento, REQ-003 nao iniciado",
      [r["status"] for r in b["rtm"]] == ["covered", "in_progress", "not_started"])
check("requisitos cobertos na feature = 1", f["requirements_covered"] == 1)
t = {x["task_id"]: x for x in b["tasks"]}
check("T-003 aguarda T-002 (dependencia nao concluida)", t["T-003"]["blocked_by"] == ["T-002"] and t["T-001"]["blocked_by"] == [])
check("1 aprovacao pendente, com T-003 bloqueada e trabalho independente continuando",
      len(b["approvals"]["pending"]) == 1 and b["approvals"]["pending"][0]["blocked_task_ids"] == ["T-003"]
      and b["approvals"]["pending"][0]["independent_work_continues"] is True)
d0 = b["decisions"][0]
check("decisao arquitetural: escolhida OPT-A, 1 alternativa descartada, seguiu a recomendacao",
      d0["selected_option"]["option_id"] == "OPT-A" and [o["option_id"] for o in d0["discarded_alternatives"]] == ["OPT-B"] and d0["followed_recommendation"] is True)
check("riscos ordenados do mais grave: high, medium, medium", [r["severity"] for r in b["risks"]] == ["high", "medium", "medium"])
check("agente backend com T-002 em andamento", next(a for a in b["agents"] if a["agent_id"] == "backend-1")["tasks_in_progress"] == ["T-002"])
check("linha do tempo: do mais recente ao mais antigo, 11 eventos",
      len(b["timeline"]) == 11 and b["timeline"][0]["sequence"] == 10 and b["timeline"][-1]["sequence"] == 0)
check("execucao T-001: 6 testes passaram, 1 criterio atendido",
      b["executions"][0]["tests"]["passed"] == 6 and b["executions"][0]["criteria"]["met"] == 1)
eng = b["engineering"]
check("engenharia: 1 blueprint (BP-001) com 2 componentes, 2 endpoints, 1 entidade e 1 ameaca",
      len(eng) == 1 and eng[0]["blueprint_id"] == "BP-001" and len(eng[0]["components"]) == 2
      and len(eng[0]["endpoints"]) == 2 and len(eng[0]["entities"]) == 1 and len(eng[0]["threats"]) == 1)
check("engenharia: ER em Mermaid marca PK, dado pessoal e segredo, sem nenhum valor de dado",
      eng[0]["graphs"]["er"].startswith("erDiagram") and "uuid id PK" in eng[0]["graphs"]["er"]
      and '"segredo"' in eng[0]["graphs"]["er"] and '"pii"' in eng[0]["graphs"]["er"])
g = b["graphs"]["dependencies"]
check("grafo: 3 nos, 2 arestas (T-001 -> T-002 -> T-003), nenhum ausente",
      len(g["nodes"]) == 3 and [(e["from"], e["to"]) for e in g["edges"]] == [("T-001", "T-002"), ("T-002", "T-003")] and g["missing_nodes"] == [])
check("Mermaid comeca com 'flowchart TD' e tem a aresta n_T_001 --> n_T_002",
      g["mermaid"].startswith("flowchart TD") and "n_T_001 --> n_T_002" in g["mermaid"])
for name in ("manifest", "overview", "features", "tasks", "rtm", "approvals", "decisions", "agents", "risks", "timeline", "graphs", "executions", "source_errors"):
    if not os.path.exists(os.path.join(base, "panel", "data", name + ".json")):
        check("arquivo por area gerado: " + name, False)
        break
else:
    check("um arquivo JSON por area gerado, alem do pacote e do data.js",
          os.path.exists(os.path.join(base, "panel", "panel-data.json")) and os.path.exists(os.path.join(base, "panel", "data.js")))
dj = open(os.path.join(base, "panel", "data.js"), encoding="utf-8").read()
check("data.js nao contem '<' cru (seguro para inclusao em pagina)", "<" not in dj and dj.startswith("window.AISEF_DATA = "))
check("chave privada nao esta no projeto (so a publica)", not any("PRIVATE" in open(os.path.join(dp, fn), "rb").read().decode("latin1")
      for dp, _, fns in os.walk(os.path.join(base, "project")) for fn in fns))

mutated = copy.deepcopy(b); mutated["manifest"]["derived"] = False
check("schema rejeita manifesto que nao e derivado", bool(list(validator.iter_errors(mutated))))
mutated = copy.deepcopy(b); mutated["manifest"]["contains_model_reasoning"] = True
check("schema rejeita raciocinio de modelo nos dados", bool(list(validator.iter_errors(mutated))))
mutated = copy.deepcopy(b); mutated["tasks"][0]["status_extra"] = "x"
check("schema rejeita campo desconhecido em tarefa", bool(list(validator.iter_errors(mutated))))

# ------------------------------------------------------------------ integridade
print("--- integridade do historico")
d = fresh("tamper")
lp = os.path.join(d, "project", "audit", "log.jsonl")
lines = open(lp, encoding="utf-8").read().splitlines()
ev = json.loads(lines[4]); ev["summary"] = "T-001 iniciada (alterada por fora)"
lines[4] = json.dumps(ev, ensure_ascii=False)
open(lp, "w", encoding="utf-8").write("\n".join(lines) + "\n")
bb = run_build(d)
check("evento adulterado: integridade 'broken' com erro de hash", bb["manifest"]["integrity"]["status"] == "broken" and any("hash" in e for e in bb["manifest"]["integrity"]["errors"]))
check("painel adulterado continua valido no schema (o aviso vem no manifesto)", not list(validator.iter_errors(bb)))

d = fresh("truncate")
lp = os.path.join(d, "project", "audit", "log.jsonl")
lines = open(lp, encoding="utf-8").read().splitlines()
open(lp, "w", encoding="utf-8").write("\n".join(lines[:-2]) + "\n")
bb = run_build(d)
check("log truncado: detectado pelo head assinado", bb["manifest"]["integrity"]["status"] == "broken" and any("truncado" in e for e in bb["manifest"]["integrity"]["errors"]))

d = fresh("nohead")
os.remove(os.path.join(d, "project", "audit", "head.json"))
bb = run_build(d)
check("sem head: 'warning' (truncamento nao detectavel), nao 'ok'", bb["manifest"]["integrity"]["status"] == "warning" and not bb["manifest"]["integrity"]["head_verified"])

d = fresh("nokeys")
shutil.rmtree(os.path.join(d, "project", "keys"))
bb = run_build(d)
check("sem chave publica: 'warning', assinaturas nao verificadas", bb["manifest"]["integrity"]["status"] == "warning" and not bb["manifest"]["integrity"]["signatures_verified"])

d = fresh("nolog")
shutil.rmtree(os.path.join(d, "project", "audit"))
bb = run_build(d)
check("sem log: 'warning' e painel vazio de eventos", bb["manifest"]["integrity"]["status"] == "warning" and bb["timeline"] == [])

# ------------------------------------------------------------------ fontes invalidas
print("--- contratos invalidos")
d = fresh("badcontract")
edit_json(os.path.join(d, "project", "contracts", "tasks", "T-002.json"), lambda x: x.__setitem__("acceptance_criteria", []))
bb = run_build(d)
check("contrato sem criterios de aceite fica fora das visoes e vai para source_errors",
      [e["file"] for e in bb["source_errors"]] == [os.path.join("contracts", "tasks", "T-002.json")] and len(bb["tasks"]) == 2)
check("RTM acusa vinculo quebrado para a tarefa excluida",
      next(r for r in bb["rtm"] if r["requirement_id"] == "REQ-002")["status"] == "broken_link"
      and next(r for r in bb["rtm"] if r["requirement_id"] == "REQ-002")["missing_task_ids"] == ["T-002"])
check("grafo registra a dependencia inexistente (T-002) como no ausente", bb["graphs"]["dependencies"]["missing_nodes"] == ["T-002"])
check("dados continuam validos no schema", not list(validator.iter_errors(bb)))

d = fresh("badjson")
open(os.path.join(d, "project", "contracts", "tasks", "T-003.json"), "w").write("{ isto nao e json")
bb = run_build(d)
check("JSON ilegivel vai para source_errors sem derrubar o construtor", any("ilegivel" in " ".join(e["errors"]) for e in bb["source_errors"]))

# ------------------------------------------------------------------ saneamento
print("--- saneamento (Mermaid, segredos)")
EVIL = 'x"]; click n_T_001 call alert(1) <img src=x onerror=alert(2)> %%{init} `'
d = fresh("evil")
edit_json(os.path.join(d, "project", "contracts", "tasks", "T-002.json"), lambda x: x.__setitem__("title", EVIL))
bb = run_build(d)
mm = bb["graphs"]["dependencies"]["mermaid"]
labels = re.findall(r'\["([^"]*)"\]', mm)
check("rotulos do Mermaid so com caracteres seguros",
      labels and all(re.fullmatch(r"[A-Za-z0-9 _.,:+/\-À-ſ]*", l) for l in labels))
non_edge = [l for l in mm.splitlines() if "-->" not in l and "classDef" not in l]
check("nenhuma linha do Mermaid virou diretiva 'click' e nenhum caractere de controle sobrou nos rotulos",
      not any(l.strip().startswith("click") for l in mm.splitlines()) and not any(re.search(r"[()<>;`{}]", l) for l in non_edge)
      and all(re.fullmatch(r"\s*[A-Za-z0-9_]+ --> [A-Za-z0-9_]+", l) for l in mm.splitlines() if "-->" in l))

d = fresh("secret")
edit_json(os.path.join(d, "project", "approvals", "APR-001.json"),
          lambda x: x.__setitem__("summary", "Usar password=hunter2hunter2 e token ghp_" + "a" * 36 + " no deploy de teste."))
bb = run_build(d)
blob = json.dumps(bb)
check("segredos nas fontes foram mascarados no painel", "hunter2" not in blob and "ghp_" not in blob and "[REDACTED]" in blob)
check("manifesto contabiliza as redacoes e sobe o aviso", bb["manifest"]["redactions"] >= 2 and bb["manifest"]["integrity"]["status"] == "warning")
check("data.js tambem nao contem o segredo", "hunter2" not in open(os.path.join(d, "panel", "data.js"), encoding="utf-8").read())

# ------------------------------------------------------------------ pagina
print("--- pagina HTML")
html = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
check("uma unica atribuicao a .innerHTML na pagina (saida do Mermaid em modo strict)", len(re.findall(r"\.innerHTML\s*=", html)) == 1 and 'securityLevel: "strict"' in html)
check("sem eval, document.write nem outerHTML", not re.search(r"\beval\s*\(|document\.write|outerHTML|insertAdjacentHTML", html))
script = re.findall(r"<script>(.*?)</script>", html, re.S)[0]
js_path = os.path.join(work, "panel_script.js")
open(js_path, "w", encoding="utf-8").write(script)
node = shutil.which("node")
if node:
    r = subprocess.run([node, "--check", js_path], capture_output=True, text=True)
    check("sintaxe do JavaScript do painel valida (node --check)", r.returncode == 0)
else:
    print("(node ausente: checagem de sintaxe pulada)")

chrome = (shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
          or shutil.which("chrome") or next((p for p in (
              os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
              os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
              os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe")) if os.path.exists(p)), None))


def dump(dest, tab, offline=False):
    build_panel.install_page(os.path.join(dest, "panel"))
    url = pathlib.Path(dest, "panel", "index.html").resolve().as_uri() + "#" + tab
    net = ["--host-resolver-rules=MAP * ~NOTFOUND"] if offline else []
    r = subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"] + net + [
                        "--virtual-time-budget=4000", "--enable-logging=stderr", "--v=0", "--dump-dom", url],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
    # O dump inclui o codigo-fonte dos <script>. Sem remove-lo, textos que existem so no codigo
    # (rotulos da interface) passariam como se tivessem sido renderizados.
    return re.sub(r"<script\b.*?</script>", "", r.stdout, flags=re.S), r.stderr


if chrome:
    expected = {
        "overview": ["Integridade do histórico verificada", "Aprovações pendentes", "Tarefas por estado"],
        "features": ["FEAT-001", "Autenticacao JWT", "1/3 tarefas"],
        "tasks": ["T-001", "Gerar access token", "Execuções entregues", "RPT-001"],
        "rtm": ["REQ-001 v1", "Coberto", "Não iniciado"],
        "approvals": ["Escopo de trabalho em dev para a T-003", "o trabalho independente continua", "APR-000"],
        "decisions": ["Algoritmo de assinatura do JWT", "seguiu a recomendação", "HS256"],
        "agents": ["Agente Backend", "Agente Validador"],
        "risks": ["Algoritmo de assinatura mal escolhido", "Regressao nas rotas protegidas"],
        "timeline": ["T-001 concluida", "Escopo para T-003 aguardando aprovacao"],
        "engineering": ["Desenho tecnico da autenticacao JWT", "POST /auth/token", "Token forjado", "dado pessoal", "MIG-1"],
        "deps": [],  # tratado a parte: SVG do Mermaid (com internet) ou codigo de fallback (sem internet)
    }
    js_errors = []
    for tab, needles in expected.items():
        out, err = dump(base, tab)
        body = out[out.find("<body"):] if "<body" in out else out
        missing = [n for n in needles if n not in body]
        if tab == "deps":
            drawn = "<svg" in body
            fallback = "flowchart TD" in body and "n_T_001 --&gt; n_T_002" in body
            print("      (deps: %s)" % ("diagrama SVG desenhado pelo Mermaid" if drawn else "fallback com o codigo Mermaid" if fallback else "NADA"))
            missing = [] if (drawn or fallback) else ["svg ou fallback"]
        check("Chrome renderiza a aba '%s' com o conteudo esperado" % tab, not missing)
        if missing:
            print("      faltando:", missing)
        js_errors += [l for l in err.splitlines() if "Uncaught" in l or "SyntaxError" in l or "TypeError" in l]
    check("nenhum erro de JavaScript no console durante as 10 abas", not js_errors)
    if js_errors:
        print("     ", js_errors[:3])

    out, _ = dump(base, "engineering", offline=True)
    body = out[out.find("<body"):]
    check("Chrome sem rede: aba Engenharia desenha arquitetura e ER (2 SVGs)", body.count("<svg") >= 2)
    out, _ = dump(base, "deps", offline=True)
    check("Chrome sem rede: Mermaid local desenha o diagrama (SVG)", "<svg" in out[out.find("<body"):])

    tamper = os.path.join(work, "tamper")
    out, _ = dump(tamper, "overview")
    check("Chrome: log adulterado mostra o aviso de integridade comprometida", "INTEGRIDADE COMPROMETIDA" in out and 'class="broken"' in out)

    out, _ = dump(os.path.join(work, "evil"), "tasks")
    check("Chrome: HTML injetado num titulo e exibido como texto, nao interpretado",
          "&lt;img src=x onerror=alert(2)&gt;" in out and "<img src=x" not in out and "<img src=\"x\"" not in out)
    out, _ = dump(os.path.join(work, "secret"), "approvals")
    check("Chrome: segredo mascarado nao aparece na pagina", "hunter2" not in out and "REDACTED" in out)

    out, _ = dump(os.path.join(work, "nolog"), "overview")
    check("Chrome: sem log aparece o aviso (nao 'verificado')", 'class="warning"' in out and "verificada: cadeia" not in out)

    nodata = os.path.join(work, "nodata"); os.makedirs(os.path.join(nodata, "panel"))
    out, _ = dump(nodata, "overview")
    check("Chrome: sem data.js a pagina explica o que fazer", "data.js não encontrado" in out)
else:
    print("(Chrome ausente: renderizacao real pulada)")

n_fail = results.count(False)
print("\n%d verificacoes, %d falhas" % (len(results), n_fail))
sys.exit(0 if n_fail == 0 else 1)
