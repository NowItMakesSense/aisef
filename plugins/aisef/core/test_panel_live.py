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
                {"hook_event_name": "PreToolUse", "tool_name": "Agent", "agent_id": "ag-1", "agent_type": "aisef:implementer",
                 "tool_input": {"subagent_type": "Explore", "description": "achar o middleware de sessao", "model": "haiku"}},
                {"hook_event_name": "PreToolUse", "tool_name": "Bash", "agent_id": "ag-1", "tool_input": {"command": "ls"}},
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
      [r["event"] for r in rt] == ["start", "spawn", "start", "stop", "tool"], rt)
check("hook PreToolUse Agent grava o disparo (pai, tipo, pedido, modelo); outras ferramentas sao ignoradas",
      rt[1]["parent_id"] == "ag-1" and rt[1]["subagent_type"] == "Explore" and rt[1]["model"] == "haiku"
      and "middleware" in rt[1]["description"], rt[1])
ap.append(proj, {"event_type": "tool_used", "actor": {"type": "system", "id": "execution-gateway"}, "summary": "Gateway: deny Read",
                 "data": {"tool": "Read", "gateway": "deny", "target": ".env", "subagent": "aisef:implementer", "agent_id": "ag-1"}})
check("pasta runtime fica fora do Git", open(os.path.join(proj, ".aisef", "runtime", ".gitignore"), encoding="utf-8").read().strip() == "*")

out = os.path.join(work, "panel")
bundle = build_panel.build(os.path.join(proj, ".aisef"), out, HERE)
L = bundle["live"]
fl = L["agents_in_flight"]
check("Agora: so o subagente ainda em execucao aparece, ligado a fatia que ele recebeu e com a ultima acao",
      len(fl) == 1 and fl[0]["agent_type"] == "aisef:implementer" and fl[0]["task_id"] == "T-010"
      and "reset.py" in (fl[0]["last_action"] or ""), fl)
BD = L["board"]
ag = {a["agent_id"]: a for a in BD["agents"]}
check("mapa: o subagente fica ligado ao agente que o disparou (sem inferencia), herda a fatia e guarda o pedido e o modelo",
      ag["ag-2"]["parent_id"] == "ag-1" and ag["ag-2"]["parent_inferred"] is False and ag["ag-2"]["task_id"] == "T-010"
      and ag["ag-2"]["model"] == "haiku" and "middleware" in (ag["ag-2"]["description"] or ""), ag.get("ag-2"))
check("mapa: o executor guarda as ultimas acoes e a contagem, e herda o modelo da delegacao",
      ag["ag-1"]["tool_count"] == 1 and "reset.py" in ag["ag-1"]["actions"][-1]["text"] and ag["ag-1"]["model"], ag.get("ag-1"))
t10 = next(t for t in BD["tasks"] if t["task_id"] == "T-010")
check("mapa: a fatia aparece rodando, na onda 1, com a negacao do gateway presa pelo id do agente",
      t10["st"] == "run" and t10["wave"] == 1 and t10["denied"] and t10["denied"]["text"] == ".env", t10)
check("raias: uma raia da fatia e uma raia recuada do subagente",
      [(r["key"], r["child"]) for r in BD["lanes"]][:2] == [("T-010", False), ("ag-2", True)], BD["lanes"])
check("frase do topo resume o que roda", BD["headline"].startswith("1 rodando"), BD["headline"])
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

# ligacao disparo -> start (mapa de agentes: subagente novo caia na onda de uma fatia antiga)
import aisef_runtime as art  # noqa: E402


def sp(at, task, pid="orq"):
    return {"event": "spawn", "at": at, "parent_id": pid, "subagent_type": "aisef:implementer",
            "description": "%s: x" % task, "task_id": task}


def st(at, aid):
    return {"event": "start", "at": at, "agent_id": aid, "agent_type": "aisef:implementer"}


m = art.match_parents([sp("2026-11-21T10:00:00-03:00", "T-010"),  # disparo orfao: nunca virou start (negado)
                       sp("2026-11-21T12:00:00-03:00", "T-030"), st("2026-11-21T12:00:02-03:00", "ag-a"),
                       sp("2026-11-21T12:30:00-03:00", "T-040"), st("2026-11-21T12:30:01-03:00", "ag-b")])
check("disparo orfao antigo nao e herdado: cada start fica com o disparo da sua hora (sem escorregar uma fatia)",
      m["ag-a"][4] == "T-030" and m["ag-b"][4] == "T-040", m)
m = art.match_parents([st("2026-11-21T12:00:02-03:00", "ag-a"), sp("2026-11-21T12:00:03-03:00", "T-030"),
                       sp("2026-11-21T12:30:00-03:00", "T-040"), st("2026-11-21T12:30:01-03:00", "ag-b")])
check("disparo gravado depois do start (hook assincrono): liga ao seu start e nao sobra para o proximo",
      m["ag-a"][4] == "T-030" and m["ag-b"][4] == "T-040", m)
m = art.match_parents([sp("2026-11-21T12:00:00-03:00", "T-030"), sp("2026-11-21T12:00:00-03:00", "T-031"),
                       st("2026-11-21T12:00:01-03:00", "ag-a"), st("2026-11-21T12:00:02-03:00", "ag-b")])
check("onda com disparos em paralelo do mesmo papel: ordem de disparo mantida",
      m["ag-a"][4] == "T-030" and m["ag-b"][4] == "T-031", m)
m = art.match_parents([sp("2026-11-21T10:00:00-03:00", "T-010"), st("2026-11-21T12:00:02-03:00", "ag-a")])
check("start sem disparo por perto: sem pai nem fatia (nao chuta um disparo velho)", m["ag-a"][4] is None and m["ag-a"][0] is None, m)
hk = json.load(open(os.path.join(HOOKS, "hooks.json"), encoding="utf-8"))
agent_hook = [h for g in hk["hooks"]["PreToolUse"] if g["matcher"] == "Agent|Task" for h in g["hooks"]]
check("hook do disparo (PreToolUse Agent|Task) e sincrono: o disparo fica gravado antes do SubagentStart",
      agent_hook and not any(h.get("async") for h in agent_hook), agent_hook)

check("etapas: sem plano aprovado = Plano; tudo concluido = Revisao; fechada = Encerrada",
      panel_live.feature_stage({"feature_id": "F", "approval": {"plan": {"status": "pending"}}, "spec": {"solution": "x"}}, []) == "plan"
      and panel_live.feature_stage({"feature_id": "F", "approval": {"plan": {"status": "approved"}}},
                                   [{"feature_id": "F", "state": {"status": "completed"}}]) == "review"
      and panel_live.feature_stage({"feature_id": "F", "state": {"status": "closed"}}, []) == "closed")

# ---------------------------------------------------------------- 0.16: regras derivadas novas do painel
F1 = {"feature_id": "F1", "state": {"status": "approved_for_execution"}, "approval": {"plan": {"status": "approved"}}}


def acc_req(rid, fid, status, created):
    return {"request_id": rid, "request_type": "feature_acceptance", "feature_id": fid, "status": status, "created_at": created,
            "decision": {"decided_at": created} if status != "pending" else None}


acc = panel_live.feature_acceptance([acc_req("APR-1", "F1", "changes_requested", "2026-11-20T10:00:00-03:00"),
                                     acc_req("APR-2", "F1", "approved", "2026-11-21T10:00:00-03:00"),
                                     acc_req("APR-3", "F2", "expired", "2026-11-21T10:00:00-03:00"),
                                     {"request_id": "APR-4", "request_type": "plan_approval", "feature_id": "F3", "status": "approved", "created_at": "x"}])
check("aceite: vale o pedido feature_acceptance mais recente; expirado e outros tipos nao contam",
      acc["F1"]["status"] == "approved" and acc["F1"]["request_id"] == "APR-2" and "F2" not in acc and "F3" not in acc, acc)
fs = panel_live.feature_status
check("feature aceita: contrato em approved_for_execution + aceite aprovado + fatias concluidas = accepted",
      fs(F1, ["completed", "cancelled"], {"status": "approved"}) == "accepted")
check("aceite recusado / alteracoes pedidas / sem decisao com as fatias concluidas",
      fs(F1, ["completed"], {"status": "rejected"}) == "acceptance_rejected"
      and fs(F1, ["completed"], {"status": "changes_requested"}) == "acceptance_changes_requested"
      and fs(F1, ["completed"], {"status": "pending"}) == "awaiting_acceptance" and fs(F1, ["completed"], None) == "awaiting_acceptance")
check("aceite antigo nao fecha feature com fatia aberta (novo ciclo); fatia saiu = em execucao",
      fs(F1, ["completed", "in_progress"], {"status": "approved"}) == "in_execution" and fs(F1, ["ready"], None) == "approved_for_execution")
check("etapa: feature aceita fica em Encerrada (nao para em Revisao e aceite)",
      panel_live.feature_stage(F1, [{"feature_id": "F1", "state": {"status": "completed"}}], {"status": "approved"}) == "closed"
      and panel_live.feature_stage(F1, [{"feature_id": "F1", "state": {"status": "completed"}}], {"status": "rejected"}) == "review")

H = [{"at": "2026-11-21T10:00:00-03:00", "text": "cd x", "reason": "r1"}, {"at": "2026-11-21T10:05:00-03:00", "text": "cd y", "reason": "r2"}]
EV = [{"timestamp": "2026-11-21T09:00:00-03:00"}]
den, hist = panel_live.deny_state(H, EV + [{"timestamp": "2026-11-21T11:00:00-03:00"}], "done", None)
check("negacao em fatia concluida: sem alarme, so o historico (contagem e a ultima)",
      den is None and hist["count"] == 2 and hist["last_text"] == "cd y" and hist["last_reason"] == "r2", (den, hist))
den, _ = panel_live.deny_state(H, EV, "run", None)
check("negacao em fatia rodando e ultima coisa que aconteceu: alarme", den and den["text"] == "cd y", den)
den, _ = panel_live.deny_state(H, EV, "run", "2026-11-21T13:06:00+00:00")
check("negacao em fatia rodando, mas o agente seguiu adiante depois: sem alarme", den is None, den)

rows = [{"task_id": "T-1", "feature_id": "FA", "wave": 1, "st": "done", "started_at": "2026-11-20T20:01:00-03:00", "ended_at": "2026-11-20T20:30:00-03:00"},
        {"task_id": "T-5", "feature_id": "FB", "wave": 1, "st": "run", "started_at": "2026-11-21T18:00:00-03:00", "ended_at": None},
        {"task_id": "T-6", "feature_id": "FB", "wave": 3, "st": "dep", "started_at": None, "ended_at": None}]
fw = panel_live.feature_waves({"features": [dict(F1, feature_id="FA", title="A"), dict(F1, feature_id="FB", title="B")],
                               "approvals": [acc_req("APR-9", "FA", "approved", "2026-11-20T21:00:00-03:00")]},
                              rows, {"T-1": "completed", "T-5": "in_progress", "T-6": "ready"})
check("ondas agrupadas por feature: ativa primeiro, aceita depois; ondas numeradas dentro da feature, com o despacho",
      [g["feature_id"] for g in fw] == ["FB", "FA"] and [w["wave"] for w in fw[0]["waves"]] == [1, 2]
      and fw[0]["waves"][1]["tasks"] == ["T-6"] and fw[0]["waves"][0]["dispatched_at"].startswith("2026-11-21T18")
      and fw[1]["status"] == "accepted" and fw[1]["active"] is False and rows[2]["feature_wave"] == 2, fw)
check("mapa: o board traz as ondas por feature", BD["feature_waves"] and BD["feature_waves"][0]["feature_id"] == "FEAT-002"
      and BD["feature_waves"][0]["waves"][0]["wave"] == 1, BD.get("feature_waves"))

rtp = panel_live.runtime_path(os.path.join(proj, ".aisef"))
with open(rtp, "a", encoding="utf-8") as fh:
    for ev in ({"event": "start", "at": "2026-01-01T10:00:00+00:00", "agent_id": "ag-old", "agent_type": "aisef:code-reviewer"},
               {"event": "start", "at": "2026-01-01T10:00:00+00:00", "agent_id": "ag-old", "agent_type": "aisef:code-reviewer"}):
        fh.write(json.dumps(ev) + "\n")
b2 = build_panel.build(os.path.join(proj, ".aisef"), os.path.join(work, "panel2"), HERE)
old = [a for a in b2["live"]["board"]["agents"] if a["agent_id"] == "ag-old"]
check("agente sem SubagentStop e parado ha horas nao conta como rodando; start repetido vira um agente so",
      len(old) == 1 and old[0]["running"] is False and old[0]["end_missing"] is True
      and not any(a["agent_id"] == "ag-old" for a in b2["live"]["agents_in_flight"]), old)

ciclo = {"red": {"exit_code": 1}, "green": {"exit_code": 0}}
check("TDD: relatorio de revisor ou validador (sem ciclos) nao zera a contagem do executor; tentativas somam",
      panel_live.tdd_counts([{"task_id": "T-9", "tdd_evidence": {"cycles": [ciclo, ciclo]}},
                             {"task_id": "T-9", "verdict": "APPROVE"},
                             {"task_id": "T-9", "tdd_evidence": {"cycles": [ciclo]}},
                             {"task_id": "T-9", "status": "validated"}]) == {"T-9": [3, 3]})

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
          'var SCREENS = {' in page and 'agora: function' in page and 'ALIAS' in page and 'fetch("panel-data.json"' in page)
    check("Agora: linha do tempo das tarefas (raia de ondas) com onda, inicio, fim e estado",
          L["timeline"] and set(L["timeline"][0]) == {"task_id", "wave", "start", "end", "state"} and L["timeline"][0]["wave"] == 1, L.get("timeline"))
finally:
    httpd.shutdown()

shutil.rmtree(work, ignore_errors=True)
print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
