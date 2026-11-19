#!/usr/bin/env python3
"""Testes do hook de subagentes (0.11.0): tarefa ligada pelo disparo, tokens somados do transcript e duracao.

Simula a sequencia que o Claude Code entrega: PreToolUse Agent (disparo) -> SubagentStart -> SubagentStop, com os
campos documentados (agent_id, agent_type, agent_transcript_path)."""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.join(os.path.dirname(HERE), "core")
sys.path.insert(0, CORE)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_project as ap  # noqa: E402
import aisef_runtime as rt  # noqa: E402

fails = total = 0


def check(name, cond, detail=None):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name)
    if not cond and detail is not None:
        print("       ", json.dumps(detail, ensure_ascii=False)[:900])
    fails += not cond


def hook(proj, payload):
    payload = dict(payload, cwd=proj, session_id="S1")
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "agent_events.py")], input=json.dumps(payload),
                       capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, CLAUDE_PROJECT_DIR=proj))
    return r.returncode


def spawn(proj, desc, stype="aisef:implementer", parent=None):
    return hook(proj, {"hook_event_name": "PreToolUse", "tool_name": "Agent", "agent_id": parent,
                       "tool_input": {"description": desc, "subagent_type": stype, "prompt": "x", "run_in_background": True}})


def transcript(path, messages):
    with open(path, "w", encoding="utf-8") as fh:
        for m in messages:
            fh.write(json.dumps(m) + "\n")
    return path


def amsg(mid, inp, out, model="claude-sonnet-5-5", cw=0, cr=0):
    return {"type": "assistant", "message": {"id": mid, "role": "assistant", "model": model,
                                             "usage": {"input_tokens": inp, "output_tokens": out,
                                                       "cache_creation_input_tokens": cw, "cache_read_input_tokens": cr}}}


def starts_of(aisef_dir):
    with open(os.path.join(aisef_dir, "runtime", "agents.jsonl"), encoding="utf-8") as fh:
        return [e for e in (json.loads(line) for line in fh) if e["event"] == "start"]


p = os.path.join(work, "proj")
os.makedirs(p)
ap.init(p, "PRJ-AE", "ae", "dev")
aisef = ap.aisef_dir(p)

print("--- extracao da tarefa")
check("descricao do dispatch -> T-001", rt.task_from_description("T-001: Login por email") == "T-001")
check("ids com sufixo e pontos", rt.task_from_description("  T-L01B: x") == "T-L01B")
check("sem prefixo -> nada", rt.task_from_description("Explorar o repo") is None and rt.task_from_description(None) is None)

print("--- uso do transcript")
tp = transcript(os.path.join(work, "t1.jsonl"), [
    {"type": "user", "message": {"role": "user", "content": "oi"}},
    amsg("m1", 100, 10, cw=50, cr=1000),
    amsg("m1", 100, 40, cw=50, cr=1000),       # mesma mensagem (streaming): conta a ultima
    amsg("m2", 20, 5, model="claude-haiku-5-5"),
    "linha invalida",
])
u = rt.transcript_usage(tp)
check("soma por mensagem, sem duplicar o streaming",
      u and u["input_tokens"] == 120 and u["output_tokens"] == 45 and u["cache_creation_input_tokens"] == 50
      and u["cache_read_input_tokens"] == 1000 and u["messages"] == 2, u)
check("tokens faturaveis = entrada + saida + escrita de cache", rt.billable_tokens(u) == 215, u)
check("transcript ausente -> None", rt.transcript_usage(os.path.join(work, "nao-existe.jsonl")) is None
      and rt.transcript_usage(None) is None)

print("--- ciclo disparo -> start -> stop")
check("disparo registrado", spawn(p, "T-001: Login por email") == 0)
hook(p, {"hook_event_name": "SubagentStart", "agent_id": "a1", "agent_type": "aisef:implementer"})
starts = starts_of(aisef)
check("start herda a tarefa do disparo, sem inferencia", starts and starts[-1].get("task_id") == "T-001"
      and starts[-1].get("spawn_inferred") is False, starts)
hook(p, {"hook_event_name": "SubagentStop", "agent_id": "a1", "agent_type": "aisef:implementer",
         "agent_transcript_path": tp, "stop_hook_active": False})
usage = rt.read_usage(aisef)
check("stop grava uso com tarefa, tokens e duracao",
      len(usage) == 1 and usage[0]["task_id"] == "T-001" and rt.billable_tokens(usage[0]["usage"]) == 215
      and isinstance(usage[0]["duration_ms"], int) and usage[0]["usage"]["models"][0] == "claude-sonnet-5-5", usage)

print("--- casos de borda")
spawn(p, "Explorar o repositorio", stype="Explore")
hook(p, {"hook_event_name": "SubagentStart", "agent_id": "a2", "agent_type": "Explore"})
hook(p, {"hook_event_name": "SubagentStop", "agent_id": "a2", "agent_type": "Explore"})
usage = rt.read_usage(aisef)
check("subagente fora do AISEF: sem tarefa e sem transcript -> uso None", usage[-1]["task_id"] is None
      and usage[-1]["usage"] is None, usage[-1])
spawn(p, "T-999: nao e do aisef", stype="general-purpose")
hook(p, {"hook_event_name": "SubagentStart", "agent_id": "a3", "agent_type": "general-purpose"})
starts = starts_of(aisef)
check("prefixo T- so vale para agentes aisef:*", starts[-1].get("task_id") is None, starts[-1])
spawn(p, "T-002: A", parent="p1")
spawn(p, "T-003: B", parent="p2")
hook(p, {"hook_event_name": "SubagentStart", "agent_id": "a4", "agent_type": "aisef:implementer"})
starts = starts_of(aisef)
check("dois disparos de pais diferentes: liga ao mais antigo e marca inferido",
      starts[-1].get("task_id") == "T-002" and starts[-1].get("spawn_inferred") is True, starts[-1])
other = os.path.join(work, "sem-aisef")
os.makedirs(other)
hook(other, {"hook_event_name": "SubagentStart", "agent_id": "z", "agent_type": "Explore"})
check("projeto sem .aisef: nada gravado", not os.path.exists(os.path.join(other, ".aisef")))
check("payload invalido nunca falha o hook", subprocess.run([sys.executable, "-I", os.path.join(HERE, "agent_events.py")],
      input="nao e json", capture_output=True, text=True).returncode == 0)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
