#!/usr/bin/env python3
"""Testes do painel ao vivo (0.8.0): visao "Agora" (agentes em voo, proximo passo, fluxo, ondas no tempo),
hook de eventos dos subagentes, estado efetivo das tarefas e o servidor local que regenera os dados."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(os.path.dirname(HERE), "hooks")
sys.path.insert(0, HERE)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_dispatch as dsp  # noqa: E402
import aisef_new  # noqa: E402
import aisef_project as ap  # noqa: E402
import build_panel  # noqa: E402
import panel_live  # noqa: E402

fails = total = 0


def check(name, cond, detail=None):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond or detail is None else "  " + json.dumps(detail, ensure_ascii=False, default=str)[:400]))
    fails += not cond


proj = os.path.join(work, "p")
os.makedirs(proj)
ap.init(proj, "PRJ-LIVE", "ao vivo", "dev")
ap.activate_agents(proj)
open(os.path.join(proj, ".aisef", "discovery.md"), "w", encoding="utf-8").write("# Discovery\n")
aisef_new.cmd_feature(proj, json.loads(json.dumps(aisef_new.EXAMPLES["feature"])))
ap.decide(proj, "APR-001", "approve")
dsp.dispatch_wave(proj)

# hook SubagentStart/SubagentStop -> .aisef/runtime/agents.jsonl
env = dict(os.environ, CLAUDE_PROJECT_DIR=proj)
for payload in ({"hook_event_name": "SubagentStart", "agent_id": "ag-1", "agent_type": "aisef:implementer"},
                {"hook_event_name": "SubagentStart", "agent_id": "ag-2", "agent_type": "Explore"},
                {"hook_event_name": "SubagentStop", "agent_id": "ag-2", "agent_type": "Explore"}):
    subprocess.run([sys.executable, "-I", os.path.join(HOOKS, "agent_events.py")], input=json.dumps(payload),
                   capture_output=True, text=True, env=env, timeout=30)
subprocess.run([sys.executable, "-I", os.path.join(HOOKS, "audit_hook.py")],
               input=json.dumps({"tool_name": "Edit", "tool_input": {"file_path": os.path.join(proj, "src", "auth", "reset.py")},
                                 "agent_id": "ag-1", "agent_type": "aisef:implementer"}),
               capture_output=True, text=True, env=env, timeout=30)
rt = panel_live.read_runtime(os.path.join(proj, ".aisef"))
check("hook de subagentes grava inicio e fim; a auditoria grava a ultima acao do subagente",
      [r["event"] for r in rt] == ["start", "start", "stop", "tool"], rt)
check("pasta runtime fica fora do Git", open(os.path.join(proj, ".aisef", "runtime", ".gitignore"), encoding="utf-8").read().strip() == "*")

out = os.path.join(work, "panel")
bundle = build_panel.build(os.path.join(proj, ".aisef"), out, HERE)
L = bundle["live"]
fl = L["agents_in_flight"]
check("Agora: so o subagente ainda em execucao aparece, ligado a fatia que ele recebeu e com a ultima acao",
      len(fl) == 1 and fl[0]["agent_type"] == "aisef:implementer" and fl[0]["task_id"] == "T-010"
      and "reset.py" in (fl[0]["last_action"] or ""), fl)
check("Agora: proximo passo vem do next (fase execucao, esperando os agentes)",
      L["next"]["phase"] == "execute" and any(a["kind"] == "wait" for a in L["next"]["actions"]), L["next"])
f = L["flow"][0]
check("Agora: fluxo da feature destaca a etapa atual (execucao)",
      f["stage"] == "execute" and "class execute now" in f["mermaid"] and "class spec done" in f["mermaid"], f)
check("Agora: ondas no tempo em Mermaid gantt com a fatia despachada",
      L["gantt"] and L["gantt"].startswith("gantt") and "T-010" in L["gantt"], L["gantt"])
check("tarefas do painel usam o estado efetivo (delegada = em andamento, mesmo com o contrato em ready)",
      next(t for t in bundle["tasks"] if t["task_id"] == "T-010")["status"] == "in_progress")
check("bundle com a visao 'live' valida no schema do painel",
      not ap.validate(json.load(open(os.path.join(out, "panel-data.json"), encoding="utf-8")), "panel-data.schema.v0.1.json"))

check("etapas: sem plano aprovado = Plano; tudo concluido = Revisao; fechada = Encerrada",
      panel_live.feature_stage({"feature_id": "F", "approval": {"plan": {"status": "pending"}}, "spec": {"solution": "x"}}, []) == "plan"
      and panel_live.feature_stage({"feature_id": "F", "approval": {"plan": {"status": "approved"}}},
                                   [{"feature_id": "F", "state": {"status": "completed"}}]) == "review"
      and panel_live.feature_stage({"feature_id": "F", "state": {"status": "closed"}}, []) == "closed")

# servidor local
build_panel.install_page(out)
httpd, url = panel_live.serve(os.path.join(proj, ".aisef"), out,
                              lambda: build_panel.build(os.path.join(proj, ".aisef"), out, HERE), port=0, port_only=True)
th = threading.Thread(target=httpd.serve_forever, daemon=True)
th.start()
try:
    d1 = json.loads(urllib.request.urlopen(url + "panel-data.json", timeout=20).read().decode("utf-8"))
    ap.append(proj, {"event_type": "task_started", "actor": {"type": "agent", "id": "implementer"}, "feature_id": "FEAT-002",
                     "task_id": "T-010", "summary": "T-010 iniciada"})
    d2 = json.loads(urllib.request.urlopen(url + "panel-data.json", timeout=20).read().decode("utf-8"))
    page = urllib.request.urlopen(url, timeout=20).read().decode("utf-8")
    check("servidor: entrega os dados com a visao ao vivo", "live" in d1 and url.startswith("http://127.0.0.1:"))
    check("servidor: regenera quando .aisef/ muda (novo evento aparece sem rodar nada)",
          d2["manifest"]["source"]["event_count"] == d1["manifest"]["source"]["event_count"] + 1)
    check("pagina: aba Agora e atualizacao automatica quando servida por http",
          'SCREENS.agora' in page and 'ALIAS' in page and 'fetch("panel-data.json"' in page)
    check("Agora: linha do tempo das tarefas (raia de ondas) com onda, inicio, fim e estado",
          L["timeline"] and set(L["timeline"][0]) == {"task_id", "wave", "start", "end", "state"} and L["timeline"][0]["wave"] == 1, L.get("timeline"))
finally:
    httpd.shutdown()

shutil.rmtree(work, ignore_errors=True)
print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
