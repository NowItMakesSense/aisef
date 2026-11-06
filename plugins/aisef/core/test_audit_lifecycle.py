#!/usr/bin/env python3
"""Testes do ciclo de vida do log: checkpoints, rotacao de segmentos, rotacao de chave e ancoras externas."""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_project as ap  # noqa: E402
import audit_chain  # noqa: E402
import build_panel  # noqa: E402
import check_project as cp  # noqa: E402

fails = total = 0


def check(name, cond):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name)
    fails += not cond


def ev(i):
    return {"event_type": "tool_used", "actor": {"type": "orchestrator", "id": "t"}, "summary": "evento %d" % i}


proj = os.path.join(work, "p")
os.makedirs(proj)
ap.init(proj, "PRJ-L", "log", "dev")
cfg_path = os.path.join(proj, ".aisef", "config.json")
cfg = json.load(open(cfg_path, encoding="utf-8"))
cfg["audit"] = {"checkpoint_every": 10, "rotate_bytes": 6000}  # pequenos de proposito
ap.write_json(cfg_path, cfg)
audit = os.path.join(proj, ".aisef", "audit")

for i in range(45):
    ap.append(proj, ev(i))
log = audit_chain.read_log_dir(audit)
cps = [e for e in log if e["event_type"] == "checkpoint"]
check("checkpoint assinado a cada 10 eventos", len(cps) >= 4 and all(e.get("signature") for e in cps))
check("segmentos arquivados ao passar do limite", len(audit_chain.log_segments(audit)) > 1)
check("cadeia continua entre segmentos (sequencia sem lacuna)", [e["sequence"] for e in log] == list(range(len(log))))
check("ancoras externas gravadas nos checkpoints", os.path.exists(ap.anchors_path("PRJ-L"))
      and len(open(ap.anchors_path("PRJ-L"), encoding="utf-8").read().splitlines()) == len(cps))
errors, _ = ap.verify(proj)
check("verify integro com varios segmentos", errors == [])
r = cp.check(os.path.join(proj, ".aisef"), HERE, os.path.join(HERE, "permission-policy.v0.1.json"),
             os.path.join(HERE, "orchestration-defaults.v0.1.json"))
check("check_project le todos os segmentos e fica limpo", r.findings == [])
_, integ = build_panel.check_integrity(os.path.join(proj, ".aisef"))
check("painel le todos os segmentos e verifica a integridade", integ["status"] == "ok")

old_key_copy = open(ap.private_key_path("PRJ-L"), "rb").read()
new_id = ap.rotate_key(proj)
ap.append(proj, ev(100))
last = ap.last_event(audit)
check("rotacao: eventos seguintes assinados pela nova chave", new_id == "audit-key-2" and last["signature"]["key_id"] == "audit-key-2")
check("rotacao: chave privada antiga apagada", not os.path.exists(ap.private_key_path("PRJ-L", "audit-key-1")))
check("rotacao: verify integro com as duas chaves publicas", ap.verify(proj)[0] == [])

# atacante que guardou a chave antiga tenta assinar um evento novo com ela
with open(ap.private_key_path("PRJ-L", "audit-key-1"), "wb") as fh:
    fh.write(old_key_copy)
cfg = json.load(open(cfg_path, encoding="utf-8"))
cfg["audit"]["key_id"] = "audit-key-1"
ap.write_json(cfg_path, cfg)
ap.append(proj, ev(101))
errors = ap.verify(proj)[0]
check("rotacao: evento assinado pela chave aposentada e erro", any("aposentada" in e for e in errors))

# reescrita completa com chaves validas nao engana a ancora externa
proj2 = os.path.join(work, "p2")
os.makedirs(proj2)
ap.init(proj2, "PRJ-A", "ancora", "dev")
for i in range(5):
    ap.append(proj2, ev(i))
ap.anchor(proj2)
seg = os.path.join(proj2, ".aisef", "audit", "log.jsonl")
lines = open(seg, encoding="utf-8").read().splitlines()
open(seg, "w", encoding="utf-8").write("\n".join(lines[:3]) + "\n")
check("ancora detecta truncamento", any("truncado" in e for e in ap.verify(proj2)[0]))

shutil.rmtree(work, ignore_errors=True)
print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
