#!/usr/bin/env python3
"""F-05: log em camadas. Edicoes de arquivo e MCP liberados vao para a telemetria (cadeia de hash, sem assinatura);
shell, ciclo de vida, decisoes e o que o gateway negou ou perguntou ficam no log assinado."""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(os.path.dirname(HERE), "hooks")
sys.path.insert(0, HERE)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_metrics as mt  # noqa: E402
import aisef_migrate as mg  # noqa: E402
import aisef_project as ap  # noqa: E402
import aisef_telemetry as tm  # noqa: E402
import audit_chain  # noqa: E402
import check_project as cp  # noqa: E402

fails = total = 0


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)[:400]))
    fails += not cond


def hook(proj, tool, **inp):
    payload = {"tool_name": tool, "tool_input": inp, "cwd": proj, "session_id": "S"}
    subprocess.run([sys.executable, "-I", os.path.join(HOOKS, "audit_hook.py")], input=json.dumps(payload), text=True,
                   capture_output=True, env=dict(os.environ, CLAUDE_PROJECT_DIR=proj))


def signed(proj):
    return audit_chain.read_log_dir(os.path.join(proj, ".aisef", "audit"))


check("modo: sem a chave = signed (comportamento anterior)", tm.mode({}) == "signed")
check("split: Edit/Write/MCP vao para a telemetria; Bash nao", tm.routes_to_telemetry({"audit": {"telemetry": "split"}}, "Edit")
      and tm.routes_to_telemetry({"audit": {"telemetry": "split"}}, "mcp__x__y")
      and not tm.routes_to_telemetry({"audit": {"telemetry": "split"}}, "Bash"))
check("signed: nada vai para a telemetria", not tm.routes_to_telemetry({"audit": {"telemetry": "signed"}}, "Edit"))

proj = os.path.join(work, "proj")
os.makedirs(proj)
ap.init(proj, "PRJ-TEL")
check("init grava audit.telemetry split", ap.load_config(proj)["audit"]["telemetry"] == "split")

# feature tipica: ciclo de vida no log assinado, muitas edicoes e alguns comandos
for i in range(3):
    ap.append(proj, {"event_type": "delegation", "actor": {"type": "orchestrator", "id": "orchestrator"},
                     "summary": "T-%d delegada" % i})
for i in range(12):
    hook(proj, "Edit", file_path=os.path.join(proj, "src", "f%d.py" % i))
hook(proj, "mcp__github__get_issue", number=1)
hook(proj, "Bash", command="pytest -q")
hook(proj, "PowerShell", command="npm run build")
log = signed(proj)
tele = tm.read(proj)
check("edicoes e MCP na telemetria (13), shell no log assinado (2)", len(tele) == 13 and
      sum(1 for e in log if e["event_type"] == "tool_used") == 2, (len(tele), [e["event_type"] for e in log]))
check("telemetria nao e versionada (.gitignore proprio)",
      open(os.path.join(proj, ".aisef", "telemetry", ".gitignore"), encoding="utf-8").read().strip() == "*")
check("cadeia da telemetria integra", tm.verify(proj) == [])
m = mt.compute_metrics(proj, run_check=False)
check("metrics: tool_used_share abaixo de 0,5 numa feature tipica (meta do plano)", m["noise"]["tool_used_share"] < 0.5,
      m["noise"])
check("metrics: conta a telemetria a parte", m["noise"]["telemetry_events"] == 13, m["noise"])

# adulteracao
path = os.path.join(proj, ".aisef", "telemetry", "telemetry.jsonl")
lines = open(path, encoding="utf-8").read().splitlines()
bad = json.loads(lines[3])
bad["summary"] = "Edit: outro.py"
open(path, "w", encoding="utf-8").write("\n".join(lines[:3] + [json.dumps(bad)] + lines[4:]) + "\n")
check("telemetria: conteudo alterado e detectado", any("alterado" in x for x in tm.verify(proj)), tm.verify(proj))
open(path, "w", encoding="utf-8").write("\n".join(lines[:5] + lines[6:]) + "\n")
check("telemetria: registro removido e detectado", any("sequencia" in x or "prev_hash" in x for x in tm.verify(proj)))
rep = cp.check(proj, policy_path=os.path.join(HERE, "permission-policy.v0.1.json"))
check("check: TELEMETRY-CHAIN como aviso (nao e o log assinado)", any(
    f["rule"] == "TELEMETRY-CHAIN" and f["severity"] == "warning" for f in rep.findings), [f["rule"] for f in rep.findings])
open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")

# rotacao
tm.ROTATE_BYTES = 200
for i in range(3):
    tm.append(proj, {"event_type": "tool_used", "summary": "Edit: r%d.py" % i, "data": {"tool": "Edit"}})
tm.ROTATE_BYTES = 5 * 1024 * 1024
files = sorted(os.listdir(os.path.join(proj, ".aisef", "telemetry")))
check("rotacao: arquivo antigo preservado e cadeia continua entre arquivos",
      any(f.startswith("telemetry-") for f in files) and tm.verify(proj) == [] and len(tm.read(proj)) == 16, files)

# projeto antigo: signed ate o migrate
old = os.path.join(work, "old")
os.makedirs(old)
ap.init(old, "PRJ-OLD")
cfg = ap.load_config(old)
cfg.pop("audit")
ap.write_json(os.path.join(old, ".aisef", "config.json"), cfg)
hook(old, "Edit", file_path=os.path.join(old, "a.py"))
check("projeto antigo (sem audit.telemetry): edicao segue no log assinado", tm.read(old) == [] and
      any(e["event_type"] == "tool_used" for e in signed(old)))
check("migrate propoe ligar a telemetria", "0.14-telemetry" in [m_ for m_, _d in mg.plan(old)[1]])
mg.apply(old)
hook(old, "Edit", file_path=os.path.join(old, "b.py"))
check("depois do migrate, a edicao vai para a telemetria", len(tm.read(old)) == 1)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
