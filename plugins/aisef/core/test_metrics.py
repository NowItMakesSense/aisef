#!/usr/bin/env python3
"""Testes das metricas (0.11.0): `aisef_project.py metrics`.

As metricas sao derivadas do log, dos contratos e das aprovacoes, sem modelo e sem escrever nada."""
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
import aisef_metrics as mt  # noqa: E402
import audit_chain  # noqa: E402

fails = total = 0


def check(name, cond, detail=None):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name)
    if not cond and detail is not None:
        print("       ", json.dumps(detail, ensure_ascii=False)[:900])
    fails += not cond


def task(tid, feature):
    return {"task_id": tid, "feature_id": feature, "title": "Tarefa " + tid, "contract_version": 1,
            "assigned_agent": {"agent_id": "backend", "agent_contract_version": 1, "role": "backend"},
            "state": {"status": "ready", "rejection_count": 0}}


def ev(proj, etype, tid=None, feature="FEAT-A", actor=("orchestrator", "orchestrator"), **extra):
    partial = {"event_type": etype, "actor": {"type": actor[0], "id": actor[1]}, "summary": "%s %s" % (etype, tid or "")}
    if tid:
        partial["task_id"] = tid
    if feature:
        partial["feature_id"] = feature
    partial.update(extra)
    return ap.append(proj, partial)


def approval(proj, rid, rtype, feature="FEAT-A", status="approved", created_at=None):
    ap.write_json(os.path.join(ap.aisef_dir(proj), "approvals", rid + ".json"),
                  {"request_id": rid, "request_type": rtype, "status": status, "feature_id": feature,
                   "title": "Pedido " + rid, "created_at": created_at or ap.now_iso()})


AGENT = ("agent", "backend")
VALIDATOR = ("validator", "validator")

p = os.path.join(work, "proj")
os.makedirs(p)
ap.init(p, "PRJ-METRICS", "metrics", "dev")
for t in (task("T-1", "FEAT-A"), task("T-2", "FEAT-A"), task("T-9", "FEAT-B")):
    ap.write_json(os.path.join(ap.aisef_dir(p), "contracts", "tasks", t["task_id"] + ".json"), t)

# T-1: passa de primeira
ev(p, "delegation", "T-1")
ev(p, "task_executed", "T-1", actor=AGENT)
ev(p, "task_validated", "T-1", actor=VALIDATOR)
ev(p, "task_completed", "T-1")
# T-2: reprovada no precheck, depois pelo validador, depois passa
ev(p, "delegation", "T-2")
ev(p, "task_executed", "T-2", actor=AGENT)
ev(p, "task_rejected", "T-2", data={"precheck": ["sem relatorio"]})
ev(p, "delegation", "T-2")
ev(p, "task_executed", "T-2", actor=AGENT)
ev(p, "task_rejected", "T-2", actor=VALIDATOR)
ev(p, "delegation", "T-2")
ev(p, "task_executed", "T-2", actor=AGENT)
ev(p, "task_validated", "T-2", actor=VALIDATOR)
ev(p, "task_completed", "T-2")
# T-9: outra feature, so delegada
ev(p, "delegation", "T-9", feature="FEAT-B")
# ruido: chamadas de ferramenta, uma negada e uma perguntada pelo gateway
ev(p, "tool_used", feature=None, data={"tool": "Bash"})
ev(p, "tool_used", feature=None, data={"tool": "Bash", "gateway": "deny"})
ev(p, "tool_used", feature=None, data={"tool": "Bash", "gateway": "ask"})
ev(p, "scope_discovery", "T-2")
approval(p, "APR-1", "plan_approval")
approval(p, "APR-2", "git_operation")
approval(p, "APR-3", "git_operation")
approval(p, "APR-4", "plan_approval", feature="FEAT-B", created_at="2020-01-01T00:00:00+00:00")

print("--- projeto inteiro")
m = mt.compute_metrics(p, run_check=False)
q, a, n = m["quality"], m["attention"], m["noise"]
check("tarefas vistas e concluidas", q["tasks_seen"] == 3 and q["tasks_completed"] == 2, q)
check("reprovacoes separadas entre precheck e validador",
      q["rejections"] == 2 and q["rejected_by_precheck"] == 1 and q["rejected_by_validator"] == 1, q)
check("1a validacao: T-1 passou, T-2 reprovou -> 50%", q["first_pass_validation_rate"] == 0.5, q)
check("despachos por tarefa: mediana 1 (T-1 e T-9), p90 3 (T-2)",
      q["attempts_per_task"]["median"] == 1 and q["attempts_per_task"]["p90"] == 3, q["attempts_per_task"])
check("scope_discovery contado", q["scope_discoveries"] == 1, q)
check("aprovacoes: 4 pedidos, metade Git, 2 por tarefa concluida",
      a["approval_requests"] == 4 and a["git_share"] == 0.5 and a["per_completed_task"] == 2.0
      and a["by_type"] == {"plan_approval": 2, "git_operation": 2}, a)
check("ruido: tool_used e decisoes do gateway", n["tool_used"] == 3 and n["gateway_denied"] == 1 and n["gateway_asked"] == 1
      and n["events"] == len(audit_chain.read_log_dir(os.path.join(ap.aisef_dir(p), "audit"))), n)
check("lead time e espera pela validacao medidos",
      m["time_minutes"]["lead_time"]["n"] == 2 and m["time_minutes"]["validation_wait"]["n"] == 2, m["time_minutes"])
check("sem --check nao ha bloco de consistencia", "consistency" not in m)
check("custo de atencao (F-09): pedidos + prompts do gateway, por tarefa concluida",
      a["interruptions"] == 5 and a["gateway_asks"] == 1 and a["interruptions_per_completed_task"] == 2.5, a)
check("custo de atencao aparece no texto", "interrupcoes             5 (2.5 por tarefa concluida)" in mt.format_metrics(m))

check("sem usage.jsonl: custo marcado como nao disponivel", m["cost"]["available"] is False
      and "nao disponivel" in mt.format_metrics(m), m["cost"])

print("--- custo (usage.jsonl gravado pelo hook SubagentStop)")
rdir = os.path.join(ap.aisef_dir(p), "runtime")
os.makedirs(rdir, exist_ok=True)
with open(os.path.join(rdir, "usage.jsonl"), "w", encoding="utf-8") as fh:
    for rec in ({"at": ap.now_iso(), "task_id": "T-1", "duration_ms": 60000,
                 "usage": {"input_tokens": 100, "output_tokens": 50, "cache_creation_input_tokens": 0,
                           "cache_read_input_tokens": 900, "models": ["claude-sonnet-5-5"]}},
                {"at": ap.now_iso(), "task_id": "T-2", "duration_ms": 120000,
                 "usage": {"input_tokens": 300, "output_tokens": 100, "cache_creation_input_tokens": 100,
                           "cache_read_input_tokens": 0, "models": ["claude-opus-5-5"]}},
                {"at": ap.now_iso(), "task_id": "T-2", "duration_ms": 60000,
                 "usage": {"input_tokens": 50, "output_tokens": 50, "models": ["claude-opus-5-5"]}},
                {"at": ap.now_iso(), "task_id": None, "duration_ms": 1000, "usage": None},
                {"at": ap.now_iso(), "task_id": "T-9", "usage": {"input_tokens": 7, "output_tokens": 0}}):
        fh.write(json.dumps(rec) + "\n")
k = mt.compute_metrics(p, run_check=False)["cost"]
check("tokens faturaveis somados (cache de leitura a parte)", k["available"] and k["billable_tokens"] == 757
      and k["cache_read_tokens"] == 900 and k["runs_with_usage"] == 4, k)
check("tokens por tarefa concluida: T-1 150, T-2 600", k["tokens_per_completed_task"]["n"] == 2
      and k["tokens_per_completed_task"]["median"] == 375.0, k["tokens_per_completed_task"])
check("por modelo", k["by_model"]["claude-opus-5-5"] == 600 and k["by_model"]["claude-sonnet-5-5"] == 150, k["by_model"])
kf = mt.compute_metrics(p, feature="FEAT-A", run_check=False)
check("--feature: execucoes de outra feature e sem tarefa ficam de fora",
      kf["cost"]["billable_tokens"] == 750 and kf["tasks"]["T-2"]["tokens"] == 600, kf["cost"])

print("--- filtros")
mf = mt.compute_metrics(p, feature="FEAT-A", run_check=False)
check("--feature: so tarefas e pedidos da feature",
      mf["quality"]["tasks_seen"] == 2 and mf["attention"]["approval_requests"] == 3 and mf["noise"]["tool_used"] == 0, mf)
ms = mt.compute_metrics(p, since="2021-01-01T00:00:00+00:00", run_check=False)
check("--since: pedido antigo fica de fora", ms["attention"]["approval_requests"] == 3, ms["attention"])

print("--- consistencia e CLI")
mc = mt.compute_metrics(p)
check("com check: conta erros e avisos por regra", isinstance(mc["consistency"]["errors"], int)
      and isinstance(mc["consistency"]["errors_by_rule"], dict), mc.get("consistency"))
r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "aisef_project.py"), "metrics", "--project", p, "--json", "--no-check"],
                   capture_output=True, text=True, encoding="utf-8", env=dict(os.environ))
out = json.loads(r.stdout) if r.returncode == 0 else {}
check("CLI metrics --json", r.returncode == 0 and out.get("quality", {}).get("tasks_completed") == 2, r.stderr[-500:])
txt = mt.format_metrics(mc)
check("saida em texto tem as quatro secoes",
      all(s in txt for s in ("Atencao humana", "Qualidade", "Tempo (minutos)", "Ruido do log", "Consistencia")), txt)
empty = os.path.join(work, "vazio")
os.makedirs(empty)
ap.init(empty, "PRJ-VAZIO", "vazio", "dev")
me = mt.compute_metrics(empty, run_check=False)
check("projeto sem tarefas nao quebra (taxas vazias)", me["quality"]["first_pass_validation_rate"] is None
      and me["attention"]["per_completed_task"] is None and "-" in mt.format_metrics(me), me["quality"])

print("--- contexto do agente: com e sem grafo (G-05)")
check("delegacao antiga, sem context_mode, cai em 'unknown'", set(m["context_modes"]) == {"unknown"}, m["context_modes"])
cx = os.path.join(work, "contexto")
os.makedirs(cx)
ap.init(cx, "PRJ-CTX", "ctx", "dev")
for tid in ("T-1", "T-2", "T-3"):
    ap.write_json(os.path.join(ap.aisef_dir(cx), "contracts", "tasks", tid + ".json"), task(tid, "FEAT-A"))
ev(cx, "delegation", "T-1", data={"context_mode": "graphify"})
ev(cx, "task_executed", "T-1", actor=AGENT)
ev(cx, "task_validated", "T-1", actor=VALIDATOR)
ev(cx, "delegation", "T-2", data={"context_mode": "graphify"})
ev(cx, "task_executed", "T-2", actor=AGENT)
ev(cx, "task_rejected", "T-2", actor=VALIDATOR)
ev(cx, "delegation", "T-2", data={"context_mode": "none"})  # o modo que conta e o da 1a delegacao
ev(cx, "delegation", "T-3", data={"context_mode": "none"})
ev(cx, "task_executed", "T-3", actor=AGENT)
ev(cx, "task_validated", "T-3", actor=VALIDATOR)
mc2 = mt.compute_metrics(cx, run_check=False)
cm = mc2["context_modes"]
check("agrupa pelo modo da 1a delegacao", cm["graphify"]["tasks"] == 2 and cm["none"]["tasks"] == 1, cm)
check("1a validacao por modo: graphify 50%, none 100%", cm["graphify"]["first_pass_validation_rate"] == 0.5
      and cm["none"]["first_pass_validation_rate"] == 1.0, cm)
txt = mt.format_metrics(mc2)
check("texto mostra a comparacao e avisa amostra pequena", "Contexto do agente" in txt and "amostra pequena" in txt, txt[-600:])

print("--- uso por agente (C-04)")
with open(os.path.join(rdir, "usage.jsonl"), "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"at": ap.now_iso(), "agent_type": "aisef:code-reviewer", "task_id": "T-2",
                         "usage": {"input_tokens": 40, "output_tokens": 10}}) + "\n")
rep = {"report_id": "RPT-T-2-REV-code-reviewer", "task_id": "T-2", "feature_id": "FEAT-A",
       "agent": {"agent_id": "code-reviewer", "role": "code-reviewer"}, "timing": {"finished_at": ap.now_iso()},
       "review": {"verdict": "APPROVE"}}
ap.write_json(os.path.join(ap.aisef_dir(p), "reports", rep["report_id"] + ".json"), rep)
rep2 = dict(rep, report_id="RPT-T-2-REV-code-reviewer-2", review={"verdict": "WARNING"})
ap.write_json(os.path.join(ap.aisef_dir(p), "reports", rep2["report_id"] + ".json"), rep2)
ap.write_agent_drafts(p, ["qa"])
ap.activate_agents(p)
ag = mt.compute_metrics(p, run_check=False)["agents"]
b = ag["by_role"]
check("executor: tarefas, despachos e 1a validacao pelo assigned_agent",
      b["backend"]["tasks"] == 3 and b["backend"]["dispatches"] == 5 and b["backend"]["first_pass_validation_rate"] == 0.5, b)
check("revisor: vereditos dos relatorios de avaliacao", b["code-reviewer"]["reviews"] == {"APPROVE": 1, "WARNING": 1}, b)
check("execucoes e tokens pelo agent_type do usage.jsonl", b["code-reviewer"]["runs"] == 1
      and b["code-reviewer"]["billable_tokens"] == 50, b["code-reviewer"])
check("contrato ativo sem uso aparece (insumo da revisao do catalogo)", "qa" in ag["active_unused"]
      and "backend" not in ag["active_unused"] and "code-reviewer" not in ag["active_unused"], ag["active_unused"])
txt = mt.format_metrics(mt.compute_metrics(p, run_check=False))
check("texto mostra a secao Agentes", "Agentes (C-04" in txt and "ativos sem uso" in txt, txt[-700:])
au = subprocess.run([sys.executable, "-I", os.path.join(HERE, "..", "..", "..", "tools", "agent_usage.py"), p, cx, "--json"],
                    capture_output=True, text=True, encoding="utf-8")
try:
    aj = json.loads(au.stdout)
except ValueError:
    aj = {}
check("tools/agent_usage.py: soma os projetos e lista quem nunca trabalhou",
      au.returncode == 0 and aj.get("projects") == 2 and aj["by_role"]["backend"]["tasks"] == 6
      and "code-reviewer" not in aj["never_used"] and "swift-reviewer" in aj["never_used"], au.stdout[-500:] + au.stderr[-300:])

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
