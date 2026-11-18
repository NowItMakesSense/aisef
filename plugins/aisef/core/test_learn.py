#!/usr/bin/env python3
"""Testes do aprendizado continuo revisado (0.8.1) e do estado reinjetado depois de compact/resume."""
import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(os.path.dirname(HERE), "hooks")
sys.path.insert(0, HERE)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_context as ctx  # noqa: E402
import aisef_dispatch as dsp  # noqa: E402
import aisef_learn as lrn  # noqa: E402
import aisef_new  # noqa: E402
import aisef_next as nx  # noqa: E402
import aisef_project as ap  # noqa: E402
import check_knowledge  # noqa: E402

fails = total = 0


def check(name, cond, detail=None):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond or detail is None else "  " + json.dumps(detail, ensure_ascii=False, default=str)[:400]))
    fails += not cond


proj = os.path.join(work, "p")
os.makedirs(proj)
ap.init(proj, "PRJ-LRN", "aprendizado", "dev")
ap.activate_agents(proj)
open(os.path.join(proj, ".aisef", "discovery.md"), "w", encoding="utf-8").write("# Discovery\n")
aisef_new.cmd_feature(proj, json.loads(json.dumps(aisef_new.EXAMPLES["feature"])))
ap.decide(proj, "APR-001", "approve")
dsp.dispatch_wave(proj)

orch = {"type": "orchestrator", "id": "orchestrator"}
for _ in range(2):
    ap.append(proj, {"event_type": "task_rejected", "actor": orch, "feature_id": "FEAT-002", "task_id": "T-010",
                     "summary": "T-010 reprovada no precheck", "data": {"precheck": ["TDD obrigatorio e o relatorio nao traz tdd_evidence"]}})
ap.append(proj, {"event_type": "tool_used", "actor": {"type": "system", "id": "execution-gateway"},
                 "summary": "Gateway: deny Bash", "data": {"tool": "Bash", "gateway": "deny", "reason": "cliente de banco de dados psql",
                                                            "target": "psql", "subagent": "aisef:implementer"}})

doc = lrn.propose(proj)
props = doc["proposals"]
tdd = next((p for p in props if p["kind"] == "rejeicao"), None)
check("propose: agrupa os erros rotulados (2 reprovacoes iguais viram um grupo; o bloqueio do gateway, outro)",
      tdd and tdd["count"] == 2 and tdd["role"] == "implementer" and any(p["kind"] == "gateway" for p in props), props)
check("propose: guarda o ponto do log ate onde ja olhou (a proxima rodada so ve o que e novo)",
      lrn.propose(proj)["proposals"] == [] and os.path.exists(lrn.proposals_path(proj)))
json.dump(doc, open(lrn.proposals_path(proj), "w", encoding="utf-8"))

e = lrn.accept(proj, tdd["id"], "a fatia exige TDD", "registrar cada ciclo vermelho/verde em tdd_evidence antes de encerrar",
               tags=["tdd"])
check("accept: vira licao ativa, revisada pelo usuario, com evidencia do log e confianca inicial pelo tamanho do grupo",
      e["status"] == "active" and e["lesson"]["review"]["approved_by"] == "user" and e["lesson"]["confidence"] == 0.55
      and all(x.startswith("E") for x in e["lesson"]["evidence_events"]), e)
check("check_knowledge: licao valida nao gera achado", not [x for x in check_knowledge.validate(os.path.join(proj, ".aisef"))
                                                              if x[0].startswith("KNW-LESSON") or x[0] == "KNW-SCHEMA"])
kpath = os.path.join(proj, ".aisef", "knowledge", e["id"] + ".json")
bad = json.load(open(kpath, encoding="utf-8"))
bad["lesson"]["evidence_events"] = ["E9999"]
ap.write_json(kpath, bad)
check("check_knowledge: evidencia que nao esta no log vira aviso",
      any(x[0] == "KNW-LESSON-EVIDENCE" for x in check_knowledge.validate(os.path.join(proj, ".aisef"))))
del bad["lesson"]["review"]
ap.write_json(kpath, bad)
check("schema: licao sem revisao do usuario e invalida",
      any(x[0] == "KNW-SCHEMA" for x in check_knowledge.validate(os.path.join(proj, ".aisef"))))
ap.write_json(kpath, e)

pack = ctx.build_pack(proj, "T-011")
les = [k for k in pack["on_demand"]["knowledge"] if k.get("lesson")]
check("pacote: licao aprovada e relevante entra, com a confianca e marcada como referencia",
      les and les[0]["id"] == e["id"] and "licao aprovada, confianca 0.55" in ctx.render_pack(pack), pack["on_demand"]["knowledge"])
low = json.loads(json.dumps(e))
low["lesson"]["confidence"] = 0.3
ap.write_json(kpath, low)
check("pacote: licao com confianca baixa nao entra", not [k for k in ctx.build_pack(proj, "T-011")["on_demand"]["knowledge"] if k.get("lesson")])
ap.write_json(kpath, e)

# T-011 recebe a licao no despacho e conclui sem reprovacao -> confianca sobe
ap.append(proj, {"event_type": "task_completed", "actor": orch, "feature_id": "FEAT-002", "task_id": "T-010", "summary": "T-010 concluida"})
res = dsp.dispatch_wave(proj)
log = [json.loads(l) for l in open(os.path.join(proj, ".aisef", "audit", "log.jsonl"), encoding="utf-8")]
dele = [x for x in log if x["event_type"] == "delegation" and x.get("task_id") == "T-011"]
check("dispatch: o delegation registra quais licoes a tarefa recebeu", dele and e["id"] in dele[-1]["data"]["lessons"], dele)
ap.append(proj, {"event_type": "task_completed", "actor": orch, "feature_id": "FEAT-002", "task_id": "T-011", "summary": "T-011 concluida"})
ch = lrn.update(proj)
check("update: tarefa que recebeu a licao e concluiu sem reprovacao sobe a confianca (+0.05)",
      ch and ch[0]["to"] == 0.6, ch)
check("update: rodar de novo sem fato novo nao conta duas vezes", lrn.update(proj, now=datetime.datetime.now(datetime.timezone.utc)) == [] or
      lrn.lessons(proj)[0]["lesson"]["confidence"] >= 0.59)
later = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(weeks=30)
lrn.update(proj, now=later)
check("update: sem uso por muitas semanas a confianca decai e a licao e aposentada (nao entra mais no pacote)",
      lrn.lessons(proj)[0]["status"] == "retired" and not [k for k in ctx.build_pack(proj, "T-011")["on_demand"]["knowledge"] if k.get("lesson")])

# estado reinjetado depois de compact/resume
p2 = os.path.join(work, "p2")
os.makedirs(p2)
ap.init(p2, "PRJ-LRN2", "estado", "dev")
ap.activate_agents(p2)
open(os.path.join(p2, ".aisef", "discovery.md"), "w", encoding="utf-8").write("# Discovery\n")
aisef_new.cmd_feature(p2, json.loads(json.dumps(aisef_new.EXAMPLES["feature"])))
env = dict(os.environ, CLAUDE_PROJECT_DIR=p2)


def doctor(source):
    r = subprocess.run([sys.executable, "-I", os.path.join(HOOKS, "doctor.py")], input=json.dumps({"source": source, "cwd": p2}),
                       capture_output=True, text=True, env=env, timeout=60)
    return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""


ctxc = doctor("compact")
check("doctor depois de /compact reinjeta o estado (fase e decisao pendente)", "fase: approve_plan" in ctxc and "APR-001" in ctxc, ctxc)
check("doctor no startup nao reinjeta estado (so fala de problemas)", "fase:" not in doctor("startup"))
check("next: marco sem agente em voo traz a dica de /compact", nx.compute_next(p2)["guide"]["compact_hint"])
check("hooks.json: SessionStart inclui compact", "compact" in json.load(open(os.path.join(HOOKS, "hooks.json"), encoding="utf-8"))["hooks"]["SessionStart"][0]["matcher"])

shutil.rmtree(work, ignore_errors=True)
print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
