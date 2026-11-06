#!/usr/bin/env python3
"""Testes do hook consultivo graph_nudge.py: sem MCP de grafo = silencio; com MCP = lembrete com os nomes reais;
nunca bloqueia; fail-open em JSON quebrado ou erro; limite por sessao; desligavel por config."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "graph_nudge.py")
RUN_SH = os.path.join(HERE, "run.sh")
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
tmp = os.path.join(work, "tmp")
os.makedirs(tmp)
ENV = dict(os.environ, TMPDIR=tmp, TEMP=tmp, TMP=tmp, PYTHONIOENCODING="utf-8")
ENV.pop("CLAUDE_PROJECT_DIR", None)
fails = total = 0


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)))
    fails += not cond


def project(name, config=True, mcp=None, raw_mcp=None, nudge_cfg=None):
    p = os.path.join(work, name)
    os.makedirs(os.path.join(p, ".aisef"))
    if config:
        cfg = {"project_id": "PRJ-N"}
        if nudge_cfg is not None:
            cfg["graph_nudge"] = nudge_cfg
        with open(os.path.join(p, ".aisef", "config.json"), "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)
    if mcp is not None:
        with open(os.path.join(p, ".mcp.json"), "w", encoding="utf-8") as fh:
            json.dump({"mcpServers": mcp}, fh)
    if raw_mcp is not None:
        with open(os.path.join(p, ".mcp.json"), "w", encoding="utf-8") as fh:
            fh.write(raw_mcp)
    return p


def fire(proj, tool="Grep", session="s", stdin=None, args=None):
    payload = stdin if stdin is not None else json.dumps(
        {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": args or {"pattern": "verifyToken"},
         "session_id": session, "cwd": proj})
    r = subprocess.run([sys.executable, "-I", HOOK], input=payload, capture_output=True, text=True, encoding="utf-8", env=ENV)
    return r


CBM = {"codebase-memory-mcp": {"command": "codebase-memory-mcp", "args": []}}
GFY = {"graphify": {"command": "python", "args": ["-m", "graphify.serve", "graphify-out/graph.json"]}}

# ------------------------------------------------------------------ silencio
r = fire(project("sem-mcp"))
check("sem .mcp.json: silencio e exit 0", r.returncode == 0 and r.stdout == "", r.stdout + r.stderr)
r = fire(project("mcp-outro", mcp={"docs": {"command": "npx", "args": ["docs-mcp"]}}))
check("com .mcp.json sem graph MCP: silencio", r.returncode == 0 and r.stdout == "", r.stdout)
r = fire(project("sem-aisef", config=False, mcp=CBM))
check("projeto sem .aisef/config.json: silencio mesmo com graph MCP", r.returncode == 0 and r.stdout == "", r.stdout)
r = fire(project("bash", mcp=CBM), tool="Bash")
check("ferramenta que nao e Grep/Glob: silencio", r.returncode == 0 and r.stdout == "", r.stdout)

# ------------------------------------------------------------------ lembrete
r = fire(project("cbm", mcp=CBM), session="cbm")
out = json.loads(r.stdout) if r.stdout else {}
h = out.get("hookSpecificOutput", {})
ctxt = h.get("additionalContext", "")
check("codebase-memory: lembrete como additionalContext de PreToolUse, exit 0",
      r.returncode == 0 and h.get("hookEventName") == "PreToolUse" and ctxt, r.stdout + r.stderr)
check("codebase-memory: cita os nomes reais das ferramentas e o termo buscado",
      "mcp__codebase-memory-mcp__search_graph" in ctxt and "mcp__codebase-memory-mcp__trace_path" in ctxt and "verifyToken" in ctxt, ctxt)
check("nunca decide permissao (sem permissionDecision)", "permissionDecision" not in h and set(out) == {"hookSpecificOutput"}, out)
r = fire(project("gfy", mcp=GFY), tool="Glob", session="gfy", args={"pattern": "**/*.md"})
ctxt = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout else ""
check("graphify em Glob: lembrete com query_graph", "mcp__graphify__query_graph" in ctxt and "Glob" in ctxt, r.stdout)
r = fire(project("ambos", mcp=dict(CBM, **GFY)), session="ambos")
ctxt = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout else ""
check("os dois configurados: lembra dos dois", "mcp__graphify__query_graph" in ctxt and "mcp__codebase-memory-mcp__search_graph" in ctxt, ctxt)
r = fire(project("nome-livre", mcp={"meu-grafo": {"command": "uvx", "args": ["codebase-memory-mcp"]}}), session="livre")
check("servidor com outro nome no .mcp.json e reconhecido pelo comando; nome da ferramenta usa a chave",
      "mcp__meu-grafo__search_graph" in r.stdout, r.stdout)
r = fire(project("unicode", mcp=CBM), session="uni", args={"pattern": "ação"})
check("padrao com acento nao quebra o hook", r.returncode == 0 and "additionalContext" in r.stdout, r.stdout + r.stderr)

# ------------------------------------------------------------------ limite por sessao
pcap = project("cap", mcp=CBM)
outs = [fire(pcap, session="cap-1").stdout for _ in range(5)]
check("limite por sessao: 3 lembretes (padrao) e depois silencio", [bool(o) for o in outs] == [True, True, True, False, False], [bool(o) for o in outs])
check("limite por sessao: outra sessao recomeca", bool(fire(pcap, session="cap-2").stdout))
pcfg = project("cap-cfg", mcp=CBM, nudge_cfg={"max_per_session": 1})
outs = [bool(fire(pcfg, session="x").stdout) for _ in range(3)]
check("config.json -> graph_nudge.max_per_session respeitado", outs == [True, False, False], outs)
check("config.json -> graph_nudge.enabled=false desliga", fire(project("off", mcp=CBM, nudge_cfg={"enabled": False}), session="off").stdout == "")
check("max_per_session invalido: silencio, sem erro",
      fire(project("cap-bad", mcp=CBM, nudge_cfg={"max_per_session": "tres"}), session="bad").stdout == "")

# ------------------------------------------------------------------ fail-open
r = fire(project("quebrado", mcp=CBM), stdin="{nao e json")
check("stdin quebrado: silencio e exit 0", r.returncode == 0 and r.stdout == "", r.stdout + r.stderr)
r = fire(project("vazio", mcp=CBM), stdin="")
check("stdin vazio: silencio e exit 0", r.returncode == 0 and r.stdout == "", r.stdout + r.stderr)
r = fire(project("mcp-quebrado", raw_mcp="{quebrado"), session="mq")
check(".mcp.json quebrado: silencio e exit 0", r.returncode == 0 and r.stdout == "", r.stdout + r.stderr)
r = fire(project("mcp-estranho", mcp=["nao", "e", "dict"]), session="me")
check(".mcp.json com formato inesperado: silencio e exit 0", r.returncode == 0 and r.stdout == "", r.stdout + r.stderr)
r = fire(project("cfg-quebrada", mcp=CBM), session="cq")
with open(os.path.join(work, "cfg-quebrada", ".aisef", "config.json"), "w", encoding="utf-8") as fh:
    fh.write("{quebrado")
r = fire(os.path.join(work, "cfg-quebrada"), session="cq2")
check("config.json quebrado: silencio e exit 0", r.returncode == 0 and r.stdout == "", r.stdout + r.stderr)
r = fire(project("json-lista", mcp=CBM), stdin="[1, 2, 3]")
check("stdin JSON que nao e objeto: silencio e exit 0", r.returncode == 0 and r.stdout == "", r.stdout + r.stderr)

# ------------------------------------------------------------------ via run.sh e hooks.json
if shutil.which("sh"):
    pr = project("runsh", mcp=CBM)
    env = dict(ENV, CLAUDE_PROJECT_DIR=pr, AISEF_PYTHON=sys.executable, AISEF_HOOKS=HERE, AISEF_SCRIPT="graph_nudge.py", AISEF_PHASE="post")
    payload = json.dumps({"tool_name": "Grep", "tool_input": {"pattern": "x"}, "session_id": "sh", "cwd": pr})
    r = subprocess.run(["sh", "-c", '. "%s"' % RUN_SH.replace("\\", "/")], input=payload, capture_output=True, text=True, encoding="utf-8", env=env)
    check("via run.sh (como no hooks.json): lembrete e exit 0", r.returncode == 0 and "additionalContext" in r.stdout, r.stdout + r.stderr)
    pr = project("runsh-sem", config=False, mcp=CBM)
    r = subprocess.run(["sh", "-c", '. "%s"' % RUN_SH.replace("\\", "/")], input=payload, capture_output=True, text=True, encoding="utf-8",
                       env=dict(env, CLAUDE_PROJECT_DIR=pr))
    check("via run.sh em projeto sem AISEF: sai na hora, em silencio", r.returncode == 0 and r.stdout == "", r.stdout + r.stderr)
else:
    print("PULADO via run.sh (sem sh no PATH)")

with open(os.path.join(HERE, "hooks.json"), encoding="utf-8") as fh:
    pre = json.load(fh)["hooks"]["PreToolUse"]
nudge = [e for e in pre if any("graph_nudge.py" in h["command"] for h in e["hooks"])]
check("hooks.json: graph_nudge registrado so para Grep|Glob, na fase post (fail-open)",
      len(nudge) == 1 and nudge[0]["matcher"] == "Grep|Glob" and "AISEF_PHASE=post" in nudge[0]["hooks"][0]["command"], nudge)
check("hooks.json: o gateway continua registrado", any("gateway.py" in h["command"] for e in pre for h in e["hooks"]))

shutil.rmtree(work, ignore_errors=True)
print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
