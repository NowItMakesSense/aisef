#!/usr/bin/env python3
"""Testes do despacho em lote (0.7.0): `dispatch` monta a onda numa chamada (prompts + delegation), `precheck`
reprova sem modelo e `validate-wave` junta a onda num validador so."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_dispatch as dsp  # noqa: E402
import aisef_new  # noqa: E402
import aisef_project as ap  # noqa: E402
import aisef_next as nx  # noqa: E402

fails = total = 0


def check(name, cond, detail=None):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond or detail is None else "  " + json.dumps(detail, ensure_ascii=False)[:400]))
    fails += not cond


proj = os.path.join(work, "p")
os.makedirs(proj)
ap.init(proj, "PRJ-DSP", "despacho", "dev")
ap.activate_agents(proj)
open(os.path.join(proj, ".aisef", "discovery.md"), "w", encoding="utf-8").write("# Discovery\n")
brief = json.loads(json.dumps(aisef_new.EXAMPLES["feature"]))
brief["tasks"].append({"id": "T-012", "kind": "slice", "title": "Auditar pedidos de redefinicao", "reqs": ["REQ-010"],
                       "touches": ["domain", "data"], "seams": ["POST /auth/reset"], "parallelizable": True,
                       "criteria": {"AC-12": "Cada pedido gera um registro de auditoria (teste de integracao)"},
                       "paths": ["src/audit/*", "tests/audit/*"]})
brief["tasks"][0]["parallelizable"] = True
aisef_new.cmd_feature(proj, brief)
ap.decide(proj, "APR-001", "approve")

dry = dsp.dispatch_wave(proj, dry_run=True)
log_before = len(open(os.path.join(proj, ".aisef", "audit", "log.jsonl"), encoding="utf-8").read().splitlines())
check("dispatch --dry-run: onda com as fatias independentes, sem gravar no log",
      sorted(a["task_id"] for a in dry["agents"]) == ["T-010", "T-012"] and nx.compute_next(proj)["states"]["T-010"] == "ready",
      dry)
res = dsp.dispatch_wave(proj)
a10 = next(a for a in res["agents"] if a["task_id"] == "T-010")
check("dispatch: um prompt por fatia, com agente, modelo e effort roteados",
      a10["subagent_type"] == "aisef:implementer" and a10["model"] == "sonnet" and a10["effort"] in ("medium", "high"), a10)
check("dispatch: o prompt traz o pacote de contexto, o TDD e os comandos de registro do proprio agente",
      "Pacote de contexto" in a10["prompt"] and "tdd_evidence" in a10["prompt"] and "--actor agent --actor-id implementer" in a10["prompt"]
      and "RPT-T-010-1.json" in a10["prompt"])
log = [json.loads(x) for x in open(os.path.join(proj, ".aisef", "audit", "log.jsonl"), encoding="utf-8")]
dele = [e for e in log if e["event_type"] == "delegation"]
check("dispatch: registra um 'delegation' por fatia, com modelo e tentativa", len(dele) == 2 and dele[0]["data"]["attempt"] == 1, dele)
check("dispatch: depois do despacho, o next manda esperar (nada despachado de novo)",
      dsp.dispatch_wave(proj)["agents"] == [] and nx.compute_next(proj)["states"]["T-010"] == "in_progress")

# ---- executor termina T-010 com relatorio incompleto e T-012 com relatorio bom
NOW = "2026-11-18T10:00:00-03:00"


def report(tid, crit, tdd=True, met=True, files=None):
    r = {"schema_version": "0.1.0", "report_id": "RPT-%s-1" % tid, "task_id": tid, "contract_version": 1, "feature_id": "FEAT-002",
         "agent": {"agent_id": "implementer", "agent_contract_version": 1, "role": "implementer"},
         "execution_profile": {"model": "sonnet", "effort": "medium", "level": 3, "attempt": 1},
         "status": "executed", "timing": {"started_at": NOW, "finished_at": NOW},
         "attempts": {"fix_attempts_used": 0, "specialist_consultations_used": 0},
         "files": {"created": [{"path": p} for p in (files or [])], "modified": [], "deleted": []},
         "changes": [{"summary": "fatia", "reason": "REQ-010"}],
         "tests": {"executed": 1, "passed": 1, "failed": 0, "skipped": 0},
         "evidence": [{"id": "EV-1", "type": "test_output", "ref": "evidence/EV-1.txt", "secrets_redacted": True}],
         "criteria_results": [{"criterion_id": crit, "required": True, "result": "met" if met else "not_met", "evidence_ids": ["EV-1"]}],
         "problems": [], "risks": [], "pending": [], "limitations": [], "intervention": {"needed": False},
         "technical_report": {"ref": "reports/RPT-%s-1.md" % tid, "sha256": "a" * 64},
         "integrity": {"created_at": NOW, "event_log_ref": "events/" + tid}}
    if tdd:
        run_ = lambda code, at: {"command": "pytest -q", "exit_code": code, "at": at}
        r["tdd_evidence"] = {"cycles": [{"behavior": "comportamento x", "test": "tests/x.py::t",
                                         "red": run_(1, "2026-11-18T09:00:00-03:00"), "green": run_(0, "2026-11-18T09:05:00-03:00")}]}
    ap.write_json(os.path.join(proj, ".aisef", "reports", r["report_id"] + ".json"), r)


report("T-010", "AC-10", tdd=False, files=["src/auth/reset.py"])
report("T-012", "AC-12", files=["src/audit/log.py", "tests/audit/test_log.py"])
for tid in ("T-010", "T-012"):
    ap.append(proj, {"event_type": "task_executed", "actor": {"type": "agent", "id": "implementer"}, "feature_id": "FEAT-002",
                     "task_id": tid, "summary": tid + " executada"})

p10 = dsp.precheck(proj, "T-010")
check("precheck: TDD obrigatorio sem tdd_evidence reprova sem gastar modelo", any("tdd_evidence" in p for p in p10), p10)
check("precheck: relatorio bom passa", dsp.precheck(proj, "T-012") == [], dsp.precheck(proj, "T-012"))
vw = dsp.validation_wave(proj)
check("validate-wave: quem falha no precheck volta ao executor (task_rejected do orquestrador)",
      [x["task_id"] for x in vw["rejected_by_precheck"]] == ["T-010"] and nx.compute_next(proj)["states"]["T-010"] == "rejected", vw)
check("validate-wave: um validador so para o resto da onda, em nivel >= executor e outro modelo",
      vw["validator"]["task_ids"] == ["T-012"] and vw["validator"]["subagent_type"] == "aisef:validator"
      and vw["validator"]["level"] >= 3 and vw["validator"]["model"] != "sonnet", vw["validator"])
check("validate-wave: o prompt manda registrar o veredito como validador, por tarefa",
      "--actor validator --actor-id validator" in vw["validator"]["prompt"] and "AC-12" in vw["validator"]["prompt"])
redo = dsp.dispatch_wave(proj, dry_run=True)
check("fatia reprovada no precheck volta no proximo dispatch como tentativa 2 (sobe um nivel)",
      any(a["task_id"] == "T-010" and a["attempt"] == 2 for a in redo["agents"]), redo["agents"])
report("T-010", "AC-10", files=["fora/do/escopo.py"])
check("precheck: arquivo fora de paths_allowed reprova", any("fora de paths_allowed" in p for p in dsp.precheck(proj, "T-010")))

cli = os.path.join(HERE, "aisef_project.py")
r = subprocess.run([sys.executable, "-I", cli, "precheck", "--project", proj, "--task", "T-012", "--json"],
                   capture_output=True, text=True, env=dict(os.environ))
check("CLI precheck --json", r.returncode == 0 and json.loads(r.stdout)["problems"] == [], r.stdout + r.stderr)
r = subprocess.run([sys.executable, "-I", cli, "dispatch", "--project", proj, "--dry-run"], capture_output=True, text=True,
                   env=dict(os.environ))
check("CLI dispatch --dry-run devolve JSON com os agentes", r.returncode == 0 and "agents" in json.loads(r.stdout), r.stdout[-300:] + r.stderr)

shutil.rmtree(work, ignore_errors=True)
print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
