#!/usr/bin/env python3
"""Mede a latencia dos hooks do AISEF como o Claude Code os chama (sh run.sh -> python -I <hook>).

Uso: python tools/bench_hooks.py [--runs 15] [--json]

Cria um projeto AISEF temporario (chaves em um AISEF_HOME temporario), dispara cada cenario N vezes e mostra
mediana e p90 em ms. O numero inclui a abertura do processo, que e quase todo o custo no Windows.
Somente stdlib + as dependencias do proprio AISEF (jsonschema, cryptography).
"""
import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, "plugins", "aisef", "hooks")
CORE = os.path.join(ROOT, "plugins", "aisef", "core")

SCENARIOS = [
    ("gateway: Read de codigo (allow)", "gateway.py", "pre", {"tool_name": "Read", "tool_input": {"file_path": "src/app.py"}}),
    ("gateway: Grep (allow + nudge)", "gateway.py", "pre", {"tool_name": "Grep", "tool_input": {"pattern": "x"}}),
    ("gateway: Bash npm test (allow)", "gateway.py", "pre", {"tool_name": "Bash", "tool_input": {"command": "npm test"}}),
    ("gateway: PowerShell git push (ask + log)", "gateway.py", "pre",
     {"tool_name": "PowerShell", "tool_input": {"command": "git push origin main"}}),
    ("auditoria: Edit (grava evento assinado)", "audit_hook.py", "post",
     {"tool_name": "Edit", "tool_input": {"file_path": "src/app.py"}}),
]


def find_sh():
    for cand in (shutil.which("sh"), r"C:\Program Files\Git\bin\sh.exe", r"C:\Program Files\Git\usr\bin\sh.exe"):
        if cand and os.path.exists(cand):
            return cand
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", type=int, default=15)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    work = tempfile.mkdtemp()
    os.environ["AISEF_HOME"] = os.path.join(work, "home")
    sys.path.insert(0, CORE)
    import aisef_project
    proj = os.path.join(work, "proj")
    os.makedirs(proj)
    aisef_project.init(proj, "PRJ-BENCH", "bench", "dev")
    sh = find_sh()
    env = dict(os.environ, CLAUDE_PROJECT_DIR=proj, AISEF_PYTHON=sys.executable, PYTHONIOENCODING="utf-8")
    results = []
    for name, script, phase, payload in SCENARIOS:
        payload = dict(payload, cwd=proj, session_id="bench")
        if sh:
            cmd = [sh, os.path.join(HOOKS, "run.sh"), script, phase]
        else:
            cmd = [sys.executable, "-I", os.path.join(HOOKS, script)]
        times = []
        for _ in range(a.runs):
            t0 = time.perf_counter()
            subprocess.run(cmd, input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8", env=env)
            times.append((time.perf_counter() - t0) * 1000)
        times.sort()
        results.append({"scenario": name, "median_ms": round(statistics.median(times)),
                        "p90_ms": round(times[min(len(times) - 1, int(len(times) * 0.9))]), "runs": a.runs})
    shutil.rmtree(work, ignore_errors=True)
    if a.json:
        print(json.dumps({"via": "run.sh" if sh else "python direto", "platform": sys.platform, "results": results}, indent=2))
        return 0
    print("via %s em %s (%d execucoes por cenario)" % ("run.sh" if sh else "python direto", sys.platform, a.runs))
    for r in results:
        print("%-45s mediana %4d ms   p90 %4d ms" % (r["scenario"], r["median_ms"], r["p90_ms"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
