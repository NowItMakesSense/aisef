#!/usr/bin/env python3
"""Testes do append: ator dos eventos de tarefa e eventos de correcao (0.4.0).
O log e imutavel, entao o append recusa antes de gravar o que o check_project acusaria para sempre."""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_project as ap  # noqa: E402

fails = total = 0


def check(name, cond):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name)
    fails += not cond


proj = os.path.join(work, "p")
os.makedirs(proj)
ap.init(proj, "PRJ-A", "append", "dev")
task = {"task_id": "T-1", "assigned_agent": {"agent_id": "backend", "agent_contract_version": 1, "role": "backend"}}
os.makedirs(os.path.join(proj, ".aisef", "contracts", "tasks"), exist_ok=True)
ap.write_json(os.path.join(proj, ".aisef", "contracts", "tasks", "T-1.json"), task)

cases = [
    ("task_started pelo orquestrador e recusado", ("task_started", "orchestrator", "aisef", "T-1", None), "delegation"),
    ("task_executed por outro agente e recusado", ("task_executed", "agent", "frontend", "T-1", None), "--actor-id backend"),
    ("task_started pelo agente da tarefa passa", ("task_started", "agent", "backend", "T-1", None), None),
    ("validador sem --actor-id e recusado", ("task_validated", "validator", "aisef", "T-1", None), "exige --actor-id"),
    ("validador com id passa", ("task_validated", "validator", "validator", "T-1", None), None),
    ("correction sem --corrects e recusado", ("correction", "orchestrator", "aisef", None, None), "--corrects"),
    ("--corrects fora de correction e recusado", ("delegation", "orchestrator", "aisef", "T-1", "E1"), "--corrects"),
    ("correction com --corrects passa", ("correction", "orchestrator", "aisef", None, "E1"), None),
    ("delegation pelo orquestrador passa", ("delegation", "orchestrator", "aisef", "T-1", None), None),
    ("tarefa sem contrato nao bloqueia", ("task_started", "orchestrator", "aisef", "T-9", None), None),
]
for name, args, expected in cases:
    problem = ap.check_append_actor(proj, *args)
    check(name, (problem is None) if expected is None else (problem is not None and expected in problem))

# CLI: recusa nao grava nada; correcao grava corrects_event_id
log = os.path.join(proj, ".aisef", "audit", "log.jsonl")
before = open(log, encoding="utf-8").read()
cli = os.path.join(HERE, "aisef_project.py")
env = dict(os.environ)
r = subprocess.run([sys.executable, "-I", cli, "append", "--project", proj, "--type", "task_started", "--task", "T-1",
                    "--summary", "x"], capture_output=True, text=True, env=env)
check("CLI recusa task_started errado com codigo != 0", r.returncode != 0)
check("CLI recusado nao grava evento", open(log, encoding="utf-8").read() == before)
r = subprocess.run([sys.executable, "-I", cli, "append", "--project", proj, "--type", "correction", "--corrects", "E0",
                    "--summary", "corrige o ator do E0"], capture_output=True, text=True, env=env)
last = json.loads(open(log, encoding="utf-8").read().strip().splitlines()[-1])
check("CLI grava correction com corrects_event_id", r.returncode == 0 and last.get("corrects_event_id") == "E0")

print("%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
