#!/usr/bin/env python3
"""M-07: o placar dos revisores (sem modelo). Respostas sinteticas medem recall, falso alarme e precisao; fixture
quebrado e detectado; a execucao monta o comando certo (subprocess simulado)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bench_reviewers as br  # noqa: E402

fails = total = 0


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)[:500]))
    fails += not cond


cases = br.load_cases()
by = {c["id"]: c for c in cases}
sqli = by["sec-sql-injection"]
ln = br.bug_line(sqli)

# parse
txt = 'Analise...\n```json\n{"findings": [{"file": "app/users.py", "line": %d, "severity": "high", "summary": "x"}]}\n```' % ln
check("parse: bloco ```json", br.parse_findings(txt) == [{"file": "app/users.py", "line": ln, "severity": "high",
                                                          "summary": "x"}])
check("parse: usa o ultimo bloco valido", br.parse_findings('```json\n{"findings": [1]}\n```\nfim\n```json\n'
                                                            '{"findings": []}\n```') == [])
check("parse: JSON solto sem cerca", br.parse_findings('nada grave. {"findings": []}') == [])
check("parse: sem JSON -> None", br.parse_findings("achei um problema de SQL") is None)
check("parse: JSON quebrado -> None", br.parse_findings('```json\n{"findings": [\n```') is None)

# acerto
check("acerta pela linha (+-3)", br.hits_bug({"file": "app/users.py", "line": ln + 2, "summary": "?"}, sqli))
check("linha longe e sem palavra-chave: nao acerta", not br.hits_bug({"file": "app/users.py", "line": ln + 9,
                                                                      "summary": "nome ruim"}, sqli))
check("acerta pela palavra-chave sem linha", br.hits_bug({"file": "app/users.py", "summary": "SQL injection no LIKE"}, sqli))
check("outro arquivo nao acerta", not br.hits_bug({"file": "app/other.py", "line": ln, "summary": "injection"}, sqli))
check("caso limpo: nada acerta", not br.hits_bug({"file": "app/report.py", "line": 1, "summary": "x"},
                                                 by["clean-extract-function"]))
check("severidade em portugues e desconhecida", br.severity({"severity": "Alta"}) == 3
      and br.severity({"severity": "baixa"}) == 1 and br.severity({}) == 2)

# placar
hit = {"file": "app/users.py", "line": ln, "severity": "critical", "summary": "sql injection"}
noise = {"file": "app/report.py", "line": 2, "severity": "medium", "summary": "estilo"}
low = {"file": "app/report.py", "line": 2, "severity": "low", "summary": "nit"}
runs = [
    {"agent": "security", "case": "sec-sql-injection", "findings": [hit], "cost_usd": 0.01},
    {"agent": "security", "case": "sec-path-traversal", "findings": [], "cost_usd": 0.01},
    {"agent": "security", "case": "clean-extract-function", "findings": [low], "cost_usd": 0.01},
    {"agent": "code-reviewer", "case": "sec-sql-injection", "findings": None, "cost_usd": 0.02},
    {"agent": "code-reviewer", "case": "clean-extract-function", "findings": [noise], "cost_usd": 0.02},
    {"agent": "code-reviewer", "case": "logic-off-by-one", "findings": [], "cost_usd": 0.02},
]
s = br.score(runs, cases)
check("recall do security: 1 de 2", s["security"]["detected"] == 1 and s["security"]["recall"] == 0.5, s["security"])
check("achado low em caso limpo nao e falso alarme", s["security"]["false_alarm_rate"] == 0.0)
check("precisao: achado serio que acerta / achados serios", s["security"]["precision"] == 1.0)
check("falso alarme medium em caso limpo conta", s["code-reviewer"]["false_alarm_rate"] == 1.0)
check("resposta sem JSON conta como nao detectado e aparece em unparsed",
      s["code-reviewer"]["unparsed"] == 1 and s["code-reviewer"]["recall"] == 0.0, s["code-reviewer"])
check("veredito: recall 0 -> cortar?", s["code-reviewer"]["verdict"] == "cortar?")
check("veredito: recall 0,5 -> revisar", s["security"]["verdict"] == "revisar")
check("veredito: paga", br.verdict({"recall": 0.8, "false_alarm_rate": 0.0}) == "paga"
      and br.verdict({"recall": 0.8, "false_alarm_rate": 0.5}) == "revisar")
check("custo somado", s["code-reviewer"]["cost_usd"] == 0.06)
md = br.render(s, {"date": "2026-11-25", "model": "sonnet", "reps": 1, "cases": len(cases)})
check("relatorio em tabela com veredito", "| security | 50% (1/2)" in md and "cortar?" in md, md)

# escopo
check("agentes do caso: categoria + linguagem", br.agents_for(by["db-update-without-where"]) == ["code-reviewer",
                                                                                                  "database-reviewer"])
check("caso limpo: todo revisor especialista mais o da linguagem", {"security", "silent-failure-hunter",
      "pr-test-analyzer", "database-reviewer", "type-design-analyzer", "code-reviewer", "python-reviewer"}
      == set(br.agents_for(by["clean-good-test"])), br.agents_for(by["clean-good-test"]))
check("caso .ts chama o typescript-reviewer", "typescript-reviewer" in br.agents_for(by["types-string-sum"]))

# fixture quebrado e detectado
tmp = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
real = br.CASES
br.CASES = os.path.join(tmp, "reviewers")
shutil.copytree(real, br.CASES)
cj = os.path.join(br.CASES, "logic-mutable-default", "case.json")
c = json.load(open(cj, encoding="utf-8"))
c["bug"]["match"] = "if tag not in tags"  # linha que ja existia antes: nao e o bug da mudanca
json.dump(c, open(cj, "w", encoding="utf-8"))
_cs, problems = br.check_fixtures()
check("fixture: bug numa linha que a mudanca nao acrescentou e erro", any("nao foi acrescentada" in x for x in problems),
      problems)
c["bug"]["match"] = "tags"
json.dump(c, open(cj, "w", encoding="utf-8"))
_cs, problems = br.check_fixtures()
check("fixture: trecho ambiguo e erro", any("exatamente uma linha" in x for x in problems), problems)
shutil.rmtree(os.path.join(br.CASES, "clean-good-test"))
shutil.rmtree(os.path.join(br.CASES, "clean-error-context"))
_cs, problems = br.check_fixtures()
check("fixture: menos de 4 limpos e erro", any("limpos" in x for x in problems), problems)
br.CASES = real
check("fixtures do repositorio validos", br.check_fixtures()[1] == [])

# execucao com subprocess simulado
seen = {}


def fake_run(cmd, cwd=None, **kw):
    seen["cmd"], seen["files"] = cmd, sorted(os.listdir(os.path.join(cwd, "app")))
    body = json.dumps({"result": txt, "total_cost_usd": 0.03, "is_error": False})
    return subprocess.CompletedProcess(cmd, 0, body, "")


orig = br.subprocess.run
br.subprocess.run = fake_run
try:
    r = br.run_one("claude", "security", sqli, "sonnet", 60)
finally:
    br.subprocess.run = orig
cmd = seen["cmd"]
sysp = cmd[cmd.index("--append-system-prompt") + 1] if "--append-system-prompt" in cmd else ""
check("run: system prompt e o corpo do agente, sem frontmatter",
      "# security" in sysp and "name: security" not in sysp and not sysp.startswith("---"), sysp[:200])
check("run: so Read, Grep e Glob", cmd[cmd.index("--allowedTools") + 1:] == ["Read", "Grep", "Glob"], cmd)
check("run: o prompt leva o diff do caso", "search_users" in cmd[2] and "+++ b/app/users.py" in cmd[2])
check("run: o agente trabalha na pasta after/", seen["files"] == ["users.py"])
check("run: achados e custo lidos do JSON do claude -p", r["findings"] and r["cost_usd"] == 0.03, r)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
