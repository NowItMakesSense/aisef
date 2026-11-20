#!/usr/bin/env python3
"""T-04/T-05: log por pessoa. Repositorio de verdade com 2 pessoas (AISEF_USER) em branches diferentes: cada uma grava
no proprio stream, com a propria chave; o merge nao conflita no log; os streams verificam; a decisao sai assinada
por quem decidiu; o CI pega o corte de um stream. Sem git no PATH, o teste e pulado."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(os.path.dirname(HERE), "hooks")
sys.path.insert(0, HERE)
sys.path.insert(0, HOOKS)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_ci as ci  # noqa: E402
import aisef_project as ap  # noqa: E402
import aisef_streams as st  # noqa: E402
import audit_chain  # noqa: E402
import check_project as cp  # noqa: E402

fails = total = 0


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)[:600]))
    fails += not cond


if not shutil.which("git"):
    print("(git ausente: teste pulado)\n\n0 testes, 0 falhas")
    sys.exit(0)


def git(cwd, *args):
    return subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True)


def as_user(user):
    os.environ["AISEF_USER"] = user


proj = os.path.join(work, "repo")
os.makedirs(proj)
git(proj, "init", "-q", "-b", "main")
git(proj, "config", "user.email", "ci@aisef")
git(proj, "config", "user.name", "ci")
as_user("alice")
ap.init(proj, "PRJ-ST")
check("sem streams: tudo no log do dono, como sempre", st.context(proj, ap.load_config(proj))["owner"])
check("identidade por AISEF_USER", st.identity(proj) == "alice")
check("ligar streams e decisao do usuario no gateway", __import__("gateway").decide(
    {"tool_name": "Bash", "tool_input": {"command": "python -I core/aisef_streams.py enable --project ."}, "cwd": proj},
    proj, __import__("gateway").load_json(__import__("gateway").POLICY_PATH), __import__("gateway").load_patterns(),
    ap.load_config(proj), __import__("datetime").datetime.now(__import__("datetime").timezone.utc))[0] == "ask")
st.enable(proj)
check("o dono e quem ligou (alice)", ap.load_config(proj)["audit"]["owner"] == "alice")
git(proj, "add", "-A")
git(proj, "commit", "-qm", "base")

# bob numa branch
git(proj, "switch", "-qc", "feat/bob")
as_user("bob")
ctx = st.context(proj, ap.load_config(proj))
check("bob grava no stream dele", not ctx["owner"] and ctx["dir"].replace("\\", "/").endswith("audit/streams/bob"), ctx)
e1 = ap.append(proj, {"event_type": "delegation", "actor": {"type": "orchestrator", "id": "orchestrator"}, "summary": "bob delega"})
check("evento de bob: log_id e id proprios", e1["log_id"] == "PRJ-ST.bob" and e1["event_id"] == "bob.E1" and e1["sequence"] == 1, e1)
bob_stream = audit_chain.read_stream(os.path.join(proj, ".aisef", "audit", "streams", "bob"))
check("stream de bob comeca com genesis e assina com a chave dele", bob_stream[0]["event_type"] == "genesis"
      and bob_stream[1]["signature"]["key_id"] == "bob.audit-key-1", bob_stream[1].get("signature"))
check("chave publica de bob no projeto; a privada fora", os.path.exists(os.path.join(proj, ".aisef", "keys", "bob.audit-key-1.pem"))
      and os.path.exists(ap.private_key_path("PRJ-ST", "bob.audit-key-1")))
ap.append(proj, {"event_type": "approval_granted", "actor": {"type": "user", "id": "user"}, "summary": "bob aprova"})
git(proj, "add", "-A")
git(proj, "commit", "-qm", "trabalho de bob")

# alice na main, ao mesmo tempo
git(proj, "switch", "-q", "main")
as_user("alice")
ap.append(proj, {"event_type": "delegation", "actor": {"type": "orchestrator", "id": "orchestrator"}, "summary": "alice delega"})
git(proj, "add", "-A")
git(proj, "commit", "-qm", "trabalho de alice")
r = git(proj, "merge", "--no-ff", "feat/bob", "-m", "merge bob")
check("merge das duas pessoas sem conflito no log", r.returncode == 0, r.stdout + r.stderr)

errs, warns = st.verify_all(proj)
check("depois do merge, cada stream verifica (cadeia, assinatura, head)", errs == [], errs)
check("verify do projeto usa os streams", ap.verify(proj)[0] == [], ap.verify(proj)[0])
log = audit_chain.read_log_dir(os.path.join(proj, ".aisef", "audit"))
check("leitores recebem os streams juntos, em ordem de tempo", {"alice delega", "bob delega", "bob aprova"}
      <= {e["summary"] for e in log} and [e["timestamp"] for e in log] == sorted(e["timestamp"] for e in log))
aprov = next(e for e in log if e["summary"] == "bob aprova")
check("a decisao de bob sai assinada pela chave de bob", aprov["signature"]["key_id"] == "bob.audit-key-1")
rules = {f["rule"] for f in cp.check(proj, policy_path=os.path.join(HERE, "permission-policy.v0.1.json")).findings
         if f["rule"].startswith("LOG-") or f["rule"] == "ID-DUP"}
check("check sem erros de log nem ids repetidos com dois streams", not rules, rules)
check("CI: streams integros com os head.json versionados", ci.verify_log(proj)[0] == [], ci.verify_log(proj)[0])

# CI: cortar o stream de bob numa PR e pego
git(proj, "add", "-A")
git(proj, "commit", "-qm", "pos-merge")
git(proj, "switch", "-qc", "feat/corte")
shutil.rmtree(os.path.join(proj, ".aisef", "audit", "streams", "bob"))
git(proj, "add", "-A")
git(proj, "commit", "-qm", "apaga o stream de bob")
e, _n = ci.append_only(proj, "main")
check("CI: stream de uma pessoa apagado na PR e pego", any("streams/bob" in x for x in e), e)

# alterar um evento de bob quebra so o stream dele
git(proj, "switch", "-q", "main")
bp = os.path.join(proj, ".aisef", "audit", "streams", "bob", "log.jsonl")
lines = open(bp, encoding="utf-8").read().splitlines()
x = json.loads(lines[1])
x["summary"] = "trocado"
open(bp, "w", encoding="utf-8").write("\n".join([lines[0], json.dumps(x)] + lines[2:]) + "\n")
errs, _w = st.verify_all(proj)
check("evento de bob alterado: erro aponta o stream de bob", errs and all("streams/bob" in y for y in errs), errs)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
