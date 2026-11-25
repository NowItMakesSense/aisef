#!/usr/bin/env python3
"""Chave privada no cofre do sistema (0.17, E-02, ADR 0031): ida e volta real, move, migrate e log assinado.

Sem cofre utilizavel os testes do cofre sao pulados, salvo com AISEF_REQUIRE_KEYSTORE=1 (CI), que os torna falha.
"""
import json
import os
import subprocess
import sys
import tempfile
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_keystore as ks  # noqa: E402
import aisef_migrate  # noqa: E402
import aisef_project as ap  # noqa: E402

fails = total = 0


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)[:600]))
    fails += not cond


PEM = b"-----BEGIN PRIVATE KEY-----\nTUVVLVNFR1JFRE8tREUtVEVTVEU=\n-----END PRIVATE KEY-----\n"
RUN = uuid.uuid4().hex[:8]  # o cofre e real e compartilhado: ids unicos por execucao

# arquivo (padrao)
check("store_of: sem config e 'file'", ks.store_of({}) == "file" and ks.store_of({"audit": {"key_store": "os"}}) == "os")
pid = "PRJ-KS-F-" + RUN
check("chave inexistente: locate None, read None", ks.locate(pid, "k") is None and ks.read(pid, "k") is None)
check("write file: volta igual", ks.write(pid, "k", PEM) == "file" and ks.read(pid, "k") == PEM)
check("locate: file", ks.locate(pid, "k") == "file")
check("local_keys lista a chave", ks.local_keys(pid) == ["k"])
ks.remove(pid, "k")
check("remove apaga o arquivo", ks.locate(pid, "k") is None)

# sem cofre: recusa alto, nao cai para arquivo em silencio
real_backend = ks.backend
ks.backend = lambda: None
try:
    ks.write(pid, "k", PEM, "os")
    check("key_store os sem cofre: VaultError", False)
except ks.VaultError as exc:
    check("key_store os sem cofre: VaultError", "cofre" in str(exc), exc)
check("... e nada foi gravado", ks.locate(pid, "k") is None)
ks.backend = real_backend

ok, why = ks.available()
required = os.environ.get("AISEF_REQUIRE_KEYSTORE") == "1"
if not ok:
    check("cofre do sistema disponivel (AISEF_REQUIRE_KEYSTORE=1)", not required, why)
    print("cofre indisponivel aqui (%s): testes do cofre pulados" % why)
    print("\n%d testes, %d falhas" % (total, fails))
    sys.exit(1 if fails else 0)
print("cofre deste sistema: %s" % why)

pid = "PRJ-KS-O-" + RUN
cleanup = []
try:
    # ida e volta real
    cleanup.append((pid, "k"))
    check("write os: devolve 'os'", ks.write(pid, "k", PEM, "os") == "os")
    pem_path, mark = ks._paths(pid, "k")
    check("no disco so o marcador, sem PEM", os.path.exists(mark) and not os.path.exists(pem_path))
    raw = open(mark, "rb").read()
    check("marcador nao contem a chave legivel", b"PRIVATE KEY" not in raw and b"TUVVLVNFR1JF" not in raw, raw[:200])
    check("marcador diz o cofre", json.loads(raw)["backend"] == why)
    check("read do cofre: mesma chave", ks.read(pid, "k") == PEM)
    check("locate: os", ks.locate(pid, "k") == "os")
    check("write os de novo (rotacao do mesmo id) sobrescreve", ks.write(pid, "k", PEM + b"#", "os") == "os"
          and ks.read(pid, "k") == PEM + b"#")
    if why == "dpapi":
        marker = json.loads(raw)
        try:
            ks._get(marker, "OUTRO/k")
            check("DPAPI: blob de uma chave nao abre como outra (entropia)", False)
        except ks.VaultError:
            check("DPAPI: blob de uma chave nao abre como outra (entropia)", True)
    ks.remove(pid, "k")
    check("remove: marcador some", ks.locate(pid, "k") is None)
    if why != "dpapi":
        try:
            ks._get({"backend": why}, ks._account(pid, "k"))
            check("remove: o cofre nao tem mais a chave", False)
        except ks.VaultError:
            check("remove: o cofre nao tem mais a chave", True)

    # move nos dois sentidos
    ks.write(pid, "m", PEM)
    cleanup.append((pid, "m"))
    check("move file -> os", ks.move(pid, "m", "os") and ks.locate(pid, "m") == "os")
    pem_path, mark = ks._paths(pid, "m")
    check("depois do move o PEM sumiu do disco (nem .bak)", not os.path.exists(pem_path)
          and not os.path.exists(pem_path + ".bak"))
    check("move para onde ja esta: False", ks.move(pid, "m", "os") is False)
    check("move os -> file: volta igual", ks.move(pid, "m", "file") and ks.read(pid, "m") == PEM
          and not os.path.exists(mark))
    try:
        ks.move(pid, "nao-existe", "os")
        check("move de chave inexistente: VaultError", False)
    except ks.VaultError:
        check("move de chave inexistente: VaultError", True)
    ks.remove(pid, "m")

    # projeto de verdade: migrate, log assinado pelo cofre, rotacao
    proj = os.path.join(work, "proj")
    os.makedirs(proj)
    ap.init(proj, "PRJ-KS-P-" + RUN, "ks", "dev")
    ppid = ap.load_config(proj)["project_id"]
    cleanup += [(ppid, k) for k in ("audit-key-1", "audit-key-2")]
    before = ks.local_keys(ppid)
    plan = aisef_migrate.key_store(proj, "os", False)
    check("migrate --key-store os sem --apply: so plano", plan and all(s == "file" for _k, s, _d in plan)
          and ks.store_of(ap.load_config(proj)) == "file", plan)
    cli = subprocess.run([sys.executable, "-I", os.path.join(HERE, "aisef_migrate.py"), "--project", proj,
                          "--key-store", "os", "--apply"], capture_output=True, text=True, env=dict(os.environ))
    check("migrate --key-store os --apply pelo CLI", cli.returncode == 0 and "file -> os" in cli.stdout,
          cli.stdout + cli.stderr)
    check("config: audit.key_store = os", ks.store_of(ap.load_config(proj)) == "os")
    check("todas as chaves do projeto no cofre", all(ks.locate(ppid, k) == "os" for k in before), before)
    ev = ap.append(proj, {"event_type": "decision_recorded", "actor": {"type": "user", "id": "user"},
                          "summary": "assinado com a chave do cofre"})
    e, _w = ap.verify(proj)
    check("evento assinado com a chave do cofre; verify limpo", ev.get("signature") and not e, e)
    new_id = ap.rotate_key(proj)
    check("rotacao com key_store os: chave nova no cofre", ks.locate(ppid, new_id) == "os")
    ap.append(proj, {"event_type": "decision_recorded", "actor": {"type": "user", "id": "user"}, "summary": "pos"})
    e, _w = ap.verify(proj)
    check("log depois da rotacao confere", not e, e)
    back = aisef_migrate.key_store(proj, "file", True)
    check("migrate de volta para arquivo", back and ks.store_of(ap.load_config(proj)) == "file"
          and ks.locate(ppid, new_id) == "file", back)
    ap.append(proj, {"event_type": "decision_recorded", "actor": {"type": "user", "id": "user"}, "summary": "file"})
    e, _w = ap.verify(proj)
    check("log segue assinando do arquivo", not e, e)
    st = subprocess.run([sys.executable, "-I", os.path.join(HERE, "aisef_keystore.py"), "status", "--project-id",
                         ppid], capture_output=True, text=True, env=dict(os.environ))
    check("status mostra cofre e chaves", st.returncode == 0 and why in st.stdout and new_id in st.stdout, st.stdout)
finally:
    for p, k in cleanup:
        try:
            ks.remove(p, k)
        except Exception:  # limpeza do cofre real: melhor esforco
            pass

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
