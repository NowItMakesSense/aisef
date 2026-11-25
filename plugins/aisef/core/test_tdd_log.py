#!/usr/bin/env python3
"""E-01 (0.17): evidencia de TDD cruzada com o log assinado.

1. O hook de auditoria grava `exit_code` no PostToolUse (0) e no PostToolUseFailure (o N de `Exit code N`).
2. A regra TDD-EVIDENCE-UNBACKED aceita o ciclo honesto e acusa o forjado: comando que nao rodou, resultado trocado,
   verde antes do vermelho no log; vira aviso no perfil solo; nao vale para projeto de antes da 0.17."""
import datetime
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
import aisef_project  # noqa: E402
import audit_chain  # noqa: E402
import check_project  # noqa: E402
import check_rules_4  # noqa: E402

fails = total = 0


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)))
    fails += not cond


# ---------------------------------------------------------------- 1. o hook grava o resultado
proj = os.path.join(work, "proj")
os.makedirs(proj)
aisef_project.init(proj, "PRJ-TDD", "TDD no log", "dev")


def hook(payload):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=proj)
    return subprocess.run([sys.executable, "-I", os.path.join(HOOKS, "audit_hook.py")], input=json.dumps(payload),
                          capture_output=True, text=True, encoding="utf-8", env=env, timeout=60)


def last_shell_event():
    log = audit_chain.read_log_dir(os.path.join(proj, ".aisef", "audit"))
    return [e for e in log if (e.get("data") or {}).get("tool") == "Bash"][-1]["data"]


hook({"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "pytest -q tests/test_a.py"},
      "tool_response": {"stdout": "1 passed", "stderr": "", "interrupted": False}, "cwd": proj})
check("PostToolUse grava exit_code 0", last_shell_event().get("exit_code") == 0, last_shell_event())
hook({"hook_event_name": "PostToolUseFailure", "tool_name": "Bash", "tool_input": {"command": "pytest -q tests/test_a.py"},
      "error": "Exit code 1\nFAILED tests/test_a.py::test_x", "is_interrupt": False, "cwd": proj})
d = last_shell_event()
check("PostToolUseFailure grava o codigo da primeira linha", d.get("exit_code") == 1 and d.get("failed") is True, d)
hook({"hook_event_name": "PostToolUseFailure", "tool_name": "Bash", "tool_input": {"command": "pytest"},
      "error": "spawn failed", "is_interrupt": False, "cwd": proj})
d = last_shell_event()
check("falha sem 'Exit code' fica failed sem codigo", d.get("failed") is True and "exit_code" not in d, d)
hook({"hook_event_name": "PostToolUseFailure", "tool_name": "Bash", "tool_input": {"command": "pytest"},
      "error": "Exit code 130\n", "is_interrupt": True, "cwd": proj})
d = last_shell_event()
check("interrupcao fica marcada, sem codigo", d.get("interrupted") is True and "exit_code" not in d, d)
hooks_cfg = json.load(open(os.path.join(HOOKS, "hooks.json"), encoding="utf-8"))["hooks"]
check("hooks.json registra o PostToolUseFailure de Bash e PowerShell",
      any(x.get("matcher") == "Bash|PowerShell" for x in hooks_cfg.get("PostToolUseFailure", [])))
check("PostToolUseFailure do shell e sincrono (consome a aprovacao reforcada como o PostToolUse)",
      not any(h.get("async") for x in hooks_cfg.get("PostToolUseFailure", []) for h in x["hooks"]))

# ---------------------------------------------------------------- 2. a regra, com log e relatorios sinteticos
T0 = datetime.datetime(2026, 11, 25, 12, 0, tzinfo=datetime.timezone.utc)


def at(minutes):
    return (T0 + datetime.timedelta(minutes=minutes)).isoformat()


def ev(minutes, cmd, code, eid):
    data = {"tool": "Bash", "command": cmd}
    if code is None:
        data["failed"] = True
    else:
        data["exit_code"] = code
        if code:
            data["failed"] = True
    return {"event_id": eid, "event_type": "tool_used", "timestamp": at(minutes), "data": data}


def cycle(red_min, green_min, cmd="pytest -q tests/test_reset.py", red_code=1, green_code=0):
    return {"behavior": "link expira em 30 min", "test": "tests/test_reset.py::test_expira",
            "red": {"command": cmd, "exit_code": red_code, "at": at(red_min)},
            "green": {"command": cmd, "exit_code": green_code, "at": at(green_min)}}


def run_rule(log, cycles, profile="team"):
    aisef = os.path.join(work, "cx-%d" % run_rule.n)
    run_rule.n += 1
    os.makedirs(aisef)
    with open(os.path.join(aisef, "config.json"), "w", encoding="utf-8") as fh:
        json.dump({"profile": profile}, fh)
    rep = check_project.Report()
    reports = [{"report_id": "RPT-1", "tdd_evidence": {"cycles": cycles}}]
    check_rules_4.rules_tdd_no_log({"project": aisef, "rep": rep, "reports": reports, "log": log})
    return [(f["severity"], f["message"]) for f in rep.findings if f["rule"] == "TDD-EVIDENCE-UNBACKED"]


run_rule.n = 0
honest = [ev(1, "cd /repo && pytest -q tests/test_reset.py", 1, "E1"), ev(9, "pytest -q tests/test_reset.py", 0, "E2")]
check("ciclo honesto (com cd na frente) passa", run_rule(honest, [cycle(1, 9)]) == [], run_rule(honest, [cycle(1, 9)]))
check("declarado com 5 min de diferenca ainda casa", run_rule(honest, [cycle(5, 13)]) == [])

got = run_rule([ev(9, "pytest -q tests/test_reset.py", 0, "E2")], [cycle(1, 9)])
check("vermelho que nao rodou e erro", len(got) == 1 and got[0][0] == "error" and "vermelho" in got[0][1], got)

got = run_rule([ev(1, "pytest -q tests/test_reset.py", 0, "E1"), ev(9, "pytest -q tests/test_reset.py", 0, "E2")], [cycle(1, 9)])
check("vermelho que no log passou e erro", len(got) == 1 and "passando" in got[0][1], got)

got = run_rule([ev(1, "pytest -q tests/test_reset.py", 1, "E1"), ev(9, "pytest -q tests/test_reset.py", 2, "E2")], [cycle(1, 9)])
check("verde que no log falhou e erro", len(got) == 1 and "falhando" in got[0][1], got)

got = run_rule([ev(1, "pytest -q tests/outro.py", 1, "E1"), ev(9, "pytest -q tests/test_reset.py", 0, "E2")], [cycle(1, 9)])
check("comando diferente no vermelho e erro", len(got) == 1 and got[0][0] == "error" and "vermelho" in got[0][1], got)

got = run_rule([ev(60, "pytest -q tests/test_reset.py", 1, "E1"), ev(9, "pytest -q tests/test_reset.py", 0, "E2")], [cycle(1, 9)])
check("vermelho fora da janela de 15 min e erro", len(got) == 1, got)

got = run_rule([ev(10, "pytest -q tests/test_reset.py", 1, "E1"), ev(4, "pytest -q tests/test_reset.py", 0, "E2")], [cycle(8, 6)])
check("no log o verde veio antes do vermelho e erro", any("veio antes" in m for _s, m in got), got)

got = run_rule([ev(1, "pytest -q tests/test_reset.py", None, "E1"), ev(9, "pytest -q tests/test_reset.py", 0, "E2")], [cycle(1, 9)])
check("falha sem codigo (shell nao abriu) conta como vermelho", got == [], got)

got = run_rule([ev(9, "pytest -q tests/test_reset.py", 0, "E2")], [cycle(1, 9)], profile="solo")
check("perfil solo: aviso, nao erro", got and all(s == "warning" for s, _m in got), got)

old_log = [{"event_id": "E1", "event_type": "tool_used", "timestamp": at(1), "data": {"tool": "Bash", "command": "pytest"}}]
check("log de antes da 0.17 (sem exit_code): regra nao se aplica", run_rule(old_log, [cycle(1, 9)]) == [])
check("ciclo anterior ao primeiro evento com resultado nao e cobrado",
      run_rule([ev(100, "ls", 0, "E9")], [cycle(1, 9)]) == [])

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
