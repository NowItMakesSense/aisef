#!/usr/bin/env python3
"""Corpus do Execution Gateway (F-02 + S-01): hooks/corpus/gateway.jsonl.

Cada linha e um comando com a decisao esperada (allow, ask, deny). Os marcados `bypass` sao tentativas de contorno
(aspas, bash -c, eval, $(...), variavel como comando, heredoc para shell, codigo inline...) e nunca podem dar allow.
Roda o gateway em processo (rapido) num projeto AISEF temporario. Tambem mede o custo do leitor de comandos."""
import datetime
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "core"))
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_project  # noqa: E402
import gateway  # noqa: E402
import shell_parse  # noqa: E402

CORPUS = os.path.join(HERE, "corpus", "gateway.jsonl")
fails = total = 0


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)))
    fails += not cond


proj = os.path.join(work, "proj")
os.makedirs(proj)
aisef_project.init(proj, "PRJ-CORPUS")
policy = gateway.load_json(gateway.POLICY_PATH)
patterns = gateway.load_patterns()
config = gateway.load_json(os.path.join(proj, ".aisef", "config.json"))
now = datetime.datetime.now(datetime.timezone.utc)


def decide(tool, command):
    data = {"tool_name": tool, "tool_input": {"command": command}, "cwd": proj}
    try:
        d, reason = gateway.decide(data, proj, policy, patterns, config, now)
        return d or "allow", reason or ""
    except gateway.Decision as e:
        return e.level, e.reason


with open(CORPUS, encoding="utf-8") as fh:
    cases = [json.loads(line) for line in fh if line.strip()]

for k in cases:
    got, reason = decide(k["tool"], k["command"])
    if k["bypass"] and got == "allow":
        check("[contorno] %s" % k["name"], False, "passou direto: " + k["command"][:80])
        continue
    check(("[contorno] " if k["bypass"] else "") + "%s -> %s" % (k["name"], k["expect"]), got == k["expect"],
          "veio %s: %s" % (got, reason[:160]))

# S-02: ferramentas de arquivo na chave privada e nas ancoras (caminho absoluto e link simbolico)
key = aisef_project.private_key_path("PRJ-CORPUS")
anchor = aisef_project.anchors_path("PRJ-CORPUS")


def decide_path(tool, **inp):
    try:
        d, _r = gateway.decide({"tool_name": tool, "tool_input": inp, "cwd": proj}, proj, policy, patterns, config, now)
        return d or "allow"
    except gateway.Decision as e:
        return e.level


check("chave: Read negado", decide_path("Read", file_path=key) == "deny")
check("chave: Grep na pasta negado", decide_path("Grep", pattern="PRIVATE", path=os.path.dirname(key)) == "deny")
check("chave: Glob na pasta negado", decide_path("Glob", pattern="*.pem", path=os.path.dirname(key)) == "deny")
check("ancora: Edit negado", decide_path("Edit", file_path=anchor, old_string="a", new_string="b") == "deny")
check("ancora: Write negado", decide_path("Write", file_path=anchor, content="{}") == "deny")

# S-03 (0.17): script que le a chave escrito agora para rodar depois; hook do Git plantado pela ferramenta de arquivo
src = os.path.join(proj, "x.py")
check("S-03: Write de script que monta o caminho da chave pergunta",
      decide_path("Write", file_path=src, content="import os\nk = os.path.join(os.path.expanduser('~'), '.aisef', 'keys')\n") == "ask")
check("S-03: Edit com ~/.aisef/anchors no texto pergunta",
      decide_path("Edit", file_path=src, old_string="a", new_string="open('~/.aisef/anchors/x')") == "ask")
check("S-03: MultiEdit com o caminho da chave pergunta",
      decide_path("MultiEdit", file_path=src, edits=[{"old_string": "a", "new_string": "Path.home() / '.aisef/keys'"}]) == "ask")
check("S-03: Write citando .aisef/keys do projeto (chave publica, sem home) segue livre",
      decide_path("Write", file_path=os.path.join(proj, "README.md"), content="A chave publica fica em .aisef/keys/.") == "allow")
check("S-03: Edit em .git/hooks/pre-commit pergunta",
      decide_path("Edit", file_path=os.path.join(proj, ".git", "hooks", "pre-commit"), old_string="a", new_string="b") == "ask")
check("S-03: Write em .githooks/ pergunta",
      decide_path("Write", file_path=os.path.join(proj, ".githooks", "pre-push"), content="#!/bin/sh") == "ask")
check("S-03: Write em .claude/hooks/ pergunta",
      decide_path("Write", file_path=os.path.join(proj, ".claude", "hooks", "x.sh"), content="#!/bin/sh") == "ask")
check("chave publica do projeto: Read continua so perguntando",
      decide_path("Read", file_path=os.path.join(proj, ".aisef", "keys", "audit-key-1.pem")) == "ask")
link = os.path.join(proj, "atalho")
try:
    os.symlink(os.path.dirname(key), link, target_is_directory=True)
except (OSError, NotImplementedError):
    link = None
if link:
    check("chave: link simbolico para a pasta negado", decide_path("Read", file_path=os.path.join(link, os.path.basename(key))) == "deny")
    check("chave: cat pelo link simbolico negado", decide("Bash", "cat atalho/" + os.path.basename(key))[0] == "deny")
else:
    print("(link simbolico indisponivel neste sistema: casos pulados)")

check("corpus com pelo menos 120 casos (%d)" % len(cases), len(cases) >= 120)
check("pelo menos 30 tentativas de contorno (%d)" % sum(k["bypass"] for k in cases), sum(k["bypass"] for k in cases) >= 30)
check("nomes unicos no corpus", len({k["name"] + k["tool"] for k in cases}) == len(cases))

# custo do leitor: precisa caber com folga nos +20 ms por chamada (meta da S-01)
t0 = time.perf_counter()
reps = 20
for _ in range(reps):
    for k in cases:
        shell_parse.analyze(k["command"], "ps" if k["tool"] == "PowerShell" else "sh")
per_call_ms = (time.perf_counter() - t0) * 1000 / (reps * len(cases))
check("leitor de comandos: %.3f ms por comando (meta: bem abaixo de 20 ms)" % per_call_ms, per_call_ms < 2)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
