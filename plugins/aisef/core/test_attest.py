#!/usr/bin/env python3
"""E-05: atestado in-toto (Statement v1 em DSSE) por tarefa no pacote de evidencia, e os controles de IA
(ISO/IEC 42001 Anexo A, EU AI Act art. 12, NIST AI RMF)."""
import base64
import hashlib
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
import aisef_attest as at  # noqa: E402
import aisef_evidence as ev  # noqa: E402
import aisef_keystore as ks  # noqa: E402
import make_demo_project as demo  # noqa: E402
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

fails = total = 0
NOW = "2026-11-05T15:00:00-03:00"


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)[:500]))
    fails += not cond


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


p = os.path.join(work, "demo")
demo.make(os.path.join(p, ".aisef"))
cfg = {"project_id": "PRJ-1", "schema_version": "0.1.0", "audit": {"key_id": "audit-key-att"}}
json.dump(cfg, open(os.path.join(p, ".aisef", "config.json"), "w"))

# sem a chave privada: recusa, nao gera pacote sem assinatura
try:
    ev.build(p, "FEAT-001", os.path.join(work, "sem-chave"), NOW, in_toto=True)
    check("--in-toto sem chave privada: recusa", False)
except SystemExit as exc:
    check("--in-toto sem chave privada: recusa", "chave privada" in str(exc), exc)

key = Ed25519PrivateKey.generate()
ks.write("PRJ-1", "audit-key-att", key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                     serialization.NoEncryption()))
with open(os.path.join(p, ".aisef", "keys", "audit-key-att.pem"), "wb") as fh:
    fh.write(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))

# um arquivo que o relatorio diz ter criado passa a existir: vira subject com sha256
reports = [load(os.path.join(p, ".aisef", "reports", f)) for f in sorted(os.listdir(os.path.join(p, ".aisef", "reports")))]
touched = next(f["path"] for r in reports for f in (r.get("files") or {}).get("created", []) + (r.get("files") or {}).get("modified", []))
os.makedirs(os.path.dirname(os.path.join(p, touched)) or p, exist_ok=True)
open(os.path.join(p, touched), "w", encoding="utf-8").write("conteudo entregue\n")

out = os.path.join(work, "pack")
ev.build(p, "FEAT-001", out, NOW, in_toto=True)
man = load(os.path.join(out, "manifest.json"))
tasks = sorted(f[len("tasks/"):-5] for f in man["files"] if f.startswith("tasks/"))
atts = sorted(f for f in man["files"] if f.startswith("attestations/"))
check("um atestado por tarefa, no manifesto", atts == ["attestations/%s.intoto.json" % t for t in tasks], (atts, tasks))

envl = load(os.path.join(out, atts[0]))
body = base64.b64decode(envl["payload"])
stmt = json.loads(body)
check("envelope DSSE: payloadType in-toto e uma assinatura com o keyid do projeto",
      envl["payloadType"] == "application/vnd.in-toto+json" and envl["signatures"][0]["keyid"] == "audit-key-att")
# PAE montado aqui direto da especificacao DSSE, sem usar o modulo
spec_pae = b"DSSEv1 28 application/vnd.in-toto+json " + str(len(body)).encode() + b" " + body
check("PAE igual ao da especificacao DSSE", at.pae(at.PAYLOAD_TYPE, body) == spec_pae)
try:
    key.public_key().verify(base64.b64decode(envl["signatures"][0]["sig"]), spec_pae)
    check("assinatura confere com a chave publica (cryptography direto)", True)
except Exception as exc:  # noqa: BLE001
    check("assinatura confere com a chave publica (cryptography direto)", False, exc)
check("Statement v1 com predicateType do AISEF", stmt["_type"] == "https://in-toto.io/Statement/v1"
      and stmt["predicateType"] == at.PREDICATE_TYPE)
pred = stmt["predicate"]
t0 = load(os.path.join(out, "tasks", tasks[0] + ".json"))
check("predicate: contrato com sha256 do Task Contract", pred["task"]["task_id"] == tasks[0]
      and pred["task"]["contract_sha256"] == hashlib.sha256(at._canon(t0)).hexdigest())
check("predicate: agente, testes, validacao e log", {"agent", "model", "tools", "tests", "validation", "log"} <= set(pred)
      and pred["log"]["events"] > 0, pred)
all_stmts = [json.loads(base64.b64decode(load(os.path.join(out, a))["payload"])) for a in atts]
subs = [s for st in all_stmts for s in st["subject"]]
want = hashlib.sha256(open(os.path.join(p, touched), "rb").read()).hexdigest()
check("subject: arquivo entregue com o sha256 de hoje", any(s["name"] == touched.replace("\\", "/")
                                                           and s["digest"]["sha256"] == want for s in subs), subs)
check("arquivo que nao existe vai para files_missing, nao para subject",
      all(s["name"] != m for st in all_stmts for m in st["predicate"]["files_missing"] for s in st["subject"]))
check("pacote com atestados verifica sozinho", ev.verify(out) == [], ev.verify(out))

# adulteracoes
copy = os.path.join(work, "pack2")
shutil.copytree(out, copy)
a0 = os.path.join(copy, atts[0])
forged = dict(stmt, predicate=dict(pred, validation={"validated": True, "validator": "eu", "event_hash": None}))
open(a0, "w").write(json.dumps(dict(envl, payload=base64.b64encode(at._canon(forged)).decode())))
problems = at.verify_pack(copy, {"audit-key-att": key.public_key()}, load)
check("payload trocado: assinatura DSSE nao confere", any("assinatura DSSE nao confere" in x for x in problems), problems)
open(a0, "w").write(json.dumps(dict(envl, signatures=[{"keyid": "outra", "sig": envl["signatures"][0]["sig"]}])))
problems = at.verify_pack(copy, {"audit-key-att": key.public_key()}, load)
check("keyid sem chave publica no pacote: erro", any("nenhuma chave publica" in x for x in problems), problems)
other = Ed25519PrivateKey.generate()
open(a0, "w").write(json.dumps(at.sign(stmt, other, "audit-key-att")))
problems = at.verify_pack(copy, {"audit-key-att": key.public_key()}, load)
check("assinado por outra chave com o mesmo keyid: erro", any("nao confere" in x for x in problems), problems)
open(a0, "w").write(json.dumps(envl))
tp = os.path.join(copy, "tasks", tasks[0] + ".json")
tj = load(tp)
tj["title"] = "titulo trocado"
open(tp, "w").write(json.dumps(tj))
problems = at.verify_pack(copy, {"audit-key-att": key.public_key()}, load)
check("Task Contract trocado no pacote: o atestado acusa", any("nao e o atestado" in x for x in problems), problems)
problems = ev.verify(copy)
check("verify do pacote soma manifesto e atestado", any("alterado: tasks/" in x for x in problems)
      and any("nao e o atestado" in x for x in problems), problems)

# controles de IA
ctl = load(os.path.join(out, "controls.json"))
by = {(c["framework"], c["control"]): c for c in ctl}
want_ctl = {("ISO/IEC 42001:2023", "A.6.2.8"), ("ISO/IEC 42001:2023", "A.6.2.4"), ("ISO/IEC 42001:2023", "A.9.2"),
            ("ISO/IEC 42001:2023", "A.4.4"), ("EU AI Act", "art. 12(1)"), ("EU AI Act", "art. 12(2)"),
            ("NIST AI RMF 1.0", "GOVERN"), ("NIST AI RMF 1.0", "MAP"), ("NIST AI RMF 1.0", "MEASURE"),
            ("NIST AI RMF 1.0", "MANAGE")}
check("controles ISO 42001, EU AI Act art. 12 e NIST AI RMF presentes", want_ctl <= set(by), sorted(by))
check("SOC 2 e ISO 27001 continuam", {("SOC 2", "CC8.1"), ("ISO/IEC 27001:2022", "A.8.32")} <= set(by))
check("todo controle tem status valido e evidencia", all(k["status"] in ("met", "partial", "missing") and k["evidence"]
                                                         for c in ctl for k in c["checks"]))
check("A.9.2 (supervisao humana) parcial no demo: plano aprovado, feature ainda nao aceita",
      by[("ISO/IEC 42001:2023", "A.9.2")]["checks"][0]["status"] == "partial", by[("ISO/IEC 42001:2023", "A.9.2")])
check("art. 12(2) usa o verify do log", "log_verify" in by[("EU AI Act", "art. 12(2)")]["checks"][0]["evidence"])
st = lambda ok, part=False: "met" if ok else ("partial" if part else "missing")  # noqa: E731
f = {"fid": "F", "n": 2, "plan_ok": False, "accepted": False, "rtm_ok": False, "n_val": 0, "tested": 0, "tdd": 0,
     "sod_ok": False, "user_ok": True, "profiled": 0, "risked": 0, "signed": False, "events": 0, "tools": 0,
     "log_ok": False}
check("sem evidencia nenhuma: controles de IA faltando, nao atendidos",
      all(c["checks"][0]["status"] != "met" for c in ev.ai_controls(st, f) if c["control"] != "GOVERN"))
readme = open(os.path.join(out, "README.md"), encoding="utf-8").read()
check("README lista os controles novos", "EU AI Act" in readme and "ISO/IEC 42001" in readme and "NIST AI RMF" in readme)

# CLI
out3 = os.path.join(work, "pack3")
cli = subprocess.run([sys.executable, "-I", os.path.join(HERE, "aisef_evidence.py"), "build", "--project", p,
                      "--feature", "FEAT-001", "--out", out3, "--now", NOW, "--in-toto"],
                     capture_output=True, text=True, env=dict(os.environ))
vcli = subprocess.run([sys.executable, "-I", os.path.join(HERE, "aisef_evidence.py"), "verify", "--pack", out3],
                      capture_output=True, text=True)
check("CLI build --in-toto e verify", cli.returncode == 0 and os.path.isdir(os.path.join(out3, "attestations"))
      and vcli.returncode == 0, cli.stdout + cli.stderr + vcli.stdout)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
