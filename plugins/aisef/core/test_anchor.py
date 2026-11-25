#!/usr/bin/env python3
"""Carimbo RFC 3161 nos marcos (0.17, E-03): TSA falsa local, token conferido contra o log, sem rede e aviso."""
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_anchor as an  # noqa: E402
import aisef_project as ap  # noqa: E402
from aisef_anchor import der_int, der_oid, seq, tlv  # noqa: E402

fails = total = 0


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)[:600]))
    fails += not cond


def token(digest, nonce, status=0, gen="20261125120000Z", hash_oid=an.SHA256_OID):
    """TimeStampResp com a estrutura da RFC 3161 (assinatura vazia: a TSA falsa nao tem chave)."""
    if status not in (0, 1):
        return seq(seq(der_int(status), seq(tlv(0x0C, b"pedido recusado"))))
    tst = seq(der_int(1), der_oid("1.2.3.4"), seq(seq(der_oid(hash_oid), b"\x05\x00"), tlv(0x04, digest)),
              der_int(4242), tlv(0x18, gen.encode()), *([der_int(nonce)] if nonce is not None else []))
    encap = seq(der_oid(an.TSTINFO_OID), tlv(0xA0, tlv(0x04, tst)))
    signed = seq(der_int(3), tlv(0x31, seq(der_oid(an.SHA256_OID))), encap, tlv(0x31, b""))
    return seq(seq(der_int(status)), seq(der_oid(an.SIGNED_DATA_OID), tlv(0xA0, signed)))


MODE = {"v": "ok"}


class FakeTSA(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        digest, nonce = an.parse_request(body)
        MODE["ctype"] = self.headers.get("Content-Type")
        mode = MODE["v"]
        der = token(b"\x00" * 32 if mode == "hash" else digest, nonce + 1 if mode == "nonce" else
                    (None if mode == "nononce" else nonce), status=2 if mode == "reject" else 0)
        self.send_response(200)
        self.send_header("Content-Type", "application/timestamp-reply")
        self.end_headers()
        self.wfile.write(der)

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), FakeTSA)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = "http://127.0.0.1:%d/tsr" % srv.server_address[1]

# DER: pedido de ida e volta
req = an.request(b"\xab" * 32, 123456789)
check("TimeStampReq em DER: hash e nonce voltam iguais", an.parse_request(req) == (b"\xab" * 32, 123456789))
check("TimeStampReq pede o certificado (certReq TRUE)", req.endswith(b"\x01\x01\xff"))
check("OID do SHA-256 codificado como na RFC", der_oid(an.SHA256_OID).hex() == "0609608648016503040201")
info = an.parse_response(token(b"\x01" * 32, 77))
check("resposta lida: hash, nonce e hora", info["digest"] == b"\x01" * 32 and info["nonce"] == 77
      and info["gen_time"].startswith("2026-11-25T12:00:00"), info)
check("token com outro hash nao confere", an.check_token(info, b"\x02" * 32, 77))
check("token com outro nonce nao confere", an.check_token(info, b"\x01" * 32, 78))
check("token sem SHA-256 nao confere", an.check_token(an.parse_response(token(b"\x01" * 32, 77, hash_oid="1.3.14.3.2.26")),
                                                       b"\x01" * 32, 77))
try:
    an.parse_response(b"\x30\x05\x02\x01")
    check("DER truncado levanta erro", False)
except ValueError:
    check("DER truncado levanta erro", True)

# projeto de verdade
proj = os.path.join(work, "proj")
os.makedirs(proj)
ap.init(proj, "PRJ-TSA")
ap.append(proj, {"event_type": "decision_recorded", "actor": {"type": "user", "id": "user"}, "summary": "x"})

res = an.milestone(proj, "aceite FEAT-001")
check("sem audit.tsa_url o marco nao carimba (nem tenta a rede)", res is None)

cfg_path = os.path.join(proj, ".aisef", "config.json")
cfg = json.load(open(cfg_path, encoding="utf-8"))
cfg.setdefault("audit", {})["tsa_url"] = URL
ap.write_json(cfg_path, cfg)

res = an.milestone(proj, "aceite FEAT-001")
tdir = os.path.join(proj, ".aisef", "audit", "timestamps")
head = ap.last_event(os.path.join(proj, ".aisef", "audit"))
check("aceite com TSA: carimba o ultimo evento", res and res["ok"] and res["sequence"] == head["sequence"], res)
check("pedido vai como application/timestamp-query", MODE.get("ctype") == "application/timestamp-query")
check("token e metadados em .aisef/audit/timestamps/", os.path.exists(res["file"]) and
      json.load(open(res["file"][:-4] + ".json", encoding="utf-8"))["event_hash"] == head["hash"])
check("mesmo evento nao e carimbado duas vezes", an.stamp(proj, "de novo")["already"])
e, w = ap.verify(proj)
check("verify do log: carimbo confere", not e, e)
check("verify avisa que a cadeia da TSA nao foi conferida", any("cadeia de certificados da TSA" in x for x in w), w)

# TSA que responde errado: nada e guardado, fica pendente
for mode, why in (("hash", "hash do token"), ("nonce", "nonce do token"), ("nononce", "nonce do token"),
                  ("reject", "recusou")):
    MODE["v"] = mode
    ap.append(proj, {"event_type": "decision_recorded", "actor": {"type": "user", "id": "user"}, "summary": mode})
    r = an.stamp(proj, "teste " + mode)
    check("TSA %s: recusado, sem token guardado" % mode, not r["ok"] and why in r["warning"]
          and not os.path.exists(os.path.join(tdir, "%06d.tsr" % r["sequence"])), r)
MODE["v"] = "ok"

# sem rede: aceite segue, com aviso e pendencia
cfg["audit"]["tsa_url"] = "http://127.0.0.1:9/tsr"
ap.write_json(cfg_path, cfg)
ap.append(proj, {"event_type": "decision_recorded", "actor": {"type": "user", "id": "user"}, "summary": "y"})
r = an.milestone(proj, "aceite FEAT-002")
check("sem rede: nao levanta, devolve aviso", r and not r["ok"] and "pendente" in r["warning"], r)
check("sem rede: pending.json gravado", os.path.exists(os.path.join(tdir, "pending.json")))
e, w = ap.verify(proj)
check("verify mostra o carimbo pendente como aviso (nao erro)", not e and any("pendente" in x for x in w), (e, w))
cfg["audit"]["tsa_url"] = URL
ap.write_json(cfg_path, cfg)
r = an.milestone(proj, "aceite FEAT-003")
check("proximo marco com rede carimba e limpa a pendencia", r["ok"] and not os.path.exists(os.path.join(tdir, "pending.json")))

# o CLI do aceite de feature carimba
cli = subprocess.run([sys.executable, "-I", os.path.join(HERE, "aisef_project.py"), "append", "--project", proj,
                      "--type", "feature_accepted", "--actor", "user", "--actor-id", "user", "--feature", "FEAT-001",
                      "--summary", "aceite"], capture_output=True, text=True, env=dict(os.environ))
check("append feature_accepted pelo CLI carimba", cli.returncode == 0 and "carimbo de tempo:" in cli.stdout,
      cli.stdout + cli.stderr)

# adulteracao depois do carimbo
first = sorted(f for f in os.listdir(tdir) if f.endswith(".tsr"))[0]
meta_path = os.path.join(tdir, first[:-4] + ".json")
meta = json.load(open(meta_path, encoding="utf-8"))
forged = dict(meta, event_hash="ff" * 32)
ap.write_json(meta_path, forged)
e, _ = ap.verify(proj)
check("metadado do carimbo trocado: erro (hash do token nao e o do evento)", any("hash do token" in x for x in e), e)
ap.write_json(meta_path, dict(meta, sequence=99999))
e, _ = ap.verify(proj)
check("carimbo de evento que sumiu do log: erro (truncado)", any("nao existe mais no log" in x for x in e), e)
ap.write_json(meta_path, meta)
log_path = os.path.join(proj, ".aisef", "audit", "log.jsonl")
lines = open(log_path, encoding="utf-8").read().splitlines()
ev = json.loads(lines[meta["sequence"]])
ev["hash"] = "ee" * 32
lines[meta["sequence"]] = json.dumps(ev)
open(log_path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
import aisef_anchor  # noqa: E402,F811
import audit_chain  # noqa: E402
e, _ = aisef_anchor.verify_tokens(proj, audit_chain.read_stream(os.path.join(proj, ".aisef", "audit")))
check("evento carimbado reescrito no log: erro com a data do carimbo", any("reescrito depois do carimbo" in x for x in e), e)
cli = subprocess.run([sys.executable, "-I", os.path.join(HERE, "aisef_anchor.py"), "verify", "--project", proj],
                     capture_output=True, text=True)
check("aisef_anchor.py verify sai 1 com evento reescrito", cli.returncode == 1 and "ERRO" in cli.stdout, cli.stdout)

srv.shutdown()
print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
