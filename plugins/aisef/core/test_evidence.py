#!/usr/bin/env python3
"""T-02: pacote de evidencia por feature, com tabela de controles (SOC 2 CC8.1, ISO 27001 A.8.32 e A.5.3), que se
verifica sozinho (manifesto de hashes, hash e assinatura Ed25519 de cada evento com a chave publica do pacote)."""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_evidence as ev  # noqa: E402
import make_demo_project as demo  # noqa: E402

fails = total = 0
NOW = "2026-11-05T15:00:00-03:00"


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)[:500]))
    fails += not cond


work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
p = os.path.join(work, "demo")
demo.make(os.path.join(p, ".aisef"))
json.dump({"project_id": "PRJ-1", "schema_version": "0.1.0"}, open(os.path.join(p, ".aisef", "config.json"), "w"))
out = os.path.join(work, "pack")
ev.build(p, "FEAT-001", out, NOW)
man = json.load(open(os.path.join(out, "manifest.json"), encoding="utf-8"))
check("pacote tem contrato, tarefas, relatorios, aprovacoes, eventos, chave, controles e README",
      {"feature/FEAT-001.json", "audit/events.jsonl", "keys/audit-key-1.pem", "controls.json", "README.md", "checks.json"}
      <= set(man["files"]) and any(f.startswith("tasks/") for f in man["files"]) and any(f.startswith("reports/") for f in man["files"]),
      sorted(man["files"]))
checks = json.load(open(os.path.join(out, "checks.json"), encoding="utf-8"))
check("verify do log e aisef-check (com o relogio do demo) registrados no pacote",
      checks["log_verify"]["errors"] == [] and checks["aisef_check"]["errors"] == 0, checks)
ctl = {c["control"]: c for c in json.load(open(os.path.join(out, "controls.json"), encoding="utf-8"))}
check("controles SOC 2 CC8.1, ISO A.8.32 e A.5.3 presentes", {"CC8.1", "A.8.32", "A.5.3"} <= set(ctl), list(ctl))
check("status calculado: plano aprovado atendido; testes parciais no demo",
      ctl["CC8.1"]["checks"][0]["status"] == "met" and ctl["CC8.1"]["checks"][2]["status"] == "partial", ctl["CC8.1"])
check("pacote integro e autentico", ev.verify(out) == [], ev.verify(out))
check("README cita o comando de verificacao", "aisef_evidence.py verify" in open(os.path.join(out, "README.md"), encoding="utf-8").read())

# adulteracoes
fp = os.path.join(out, "feature", "FEAT-001.json")
orig = open(fp, encoding="utf-8").read()
open(fp, "w", encoding="utf-8").write(orig.replace("Autenticacao", "Autorizacao"))
check("arquivo alterado e detectado", any("alterado: feature/FEAT-001.json" in x for x in ev.verify(out)))
open(fp, "w", encoding="utf-8").write(orig)
extra = os.path.join(out, "reports", "falso.json")
open(extra, "w").write("{}")
check("arquivo fora do manifesto e detectado", any("fora do manifesto" in x for x in ev.verify(out)))
os.remove(extra)
evp = os.path.join(out, "audit", "events.jsonl")
lines = open(evp, encoding="utf-8").read().splitlines()
e0 = json.loads(lines[0])
e0["summary"] = "resumo trocado"
open(evp, "w", encoding="utf-8").write("\n".join([json.dumps(e0)] + lines[1:]) + "\n")
man["files"]["audit/events.jsonl"] = ev._sha(evp)  # quem adultera refaz o manifesto: a assinatura pega mesmo assim
json.dump(man, open(os.path.join(out, "manifest.json"), "w", encoding="utf-8"))
check("evento adulterado com manifesto refeito: o hash do evento pega", any("nao confere com o hash" in x for x in ev.verify(out)))
try:
    ev.build(p, "FEAT-001", out)
    ok = False
except SystemExit as e:
    ok = "nao esta vazia" in str(e)
check("build recusa pasta de destino com conteudo", ok)

# segregacao de funcoes
f = {"feature_id": "F", "rtm": [], "approval": {"plan": {"status": "approved"}}}
evs = [{"event_type": "task_executed", "task_id": "T-1", "actor": {"type": "agent", "id": "backend"}},
       {"event_type": "task_validated", "task_id": "T-1", "actor": {"type": "validator", "id": "backend"}}]
c = {x["control"]: x for x in ev.controls(f, [{"task_id": "T-1", "state": {"status": "validated"}}], [], [], evs)}
check("A.5.3: quem executou e validou a mesma tarefa aparece como violacao",
      c["A.5.3"]["checks"][0]["status"] == "missing" and "violado em T-1" in c["A.5.3"]["checks"][0]["evidence"], c["A.5.3"])
check("CLI verify sai 1 com pacote adulterado", ev.main(["verify", "--pack", out]) == 1)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
