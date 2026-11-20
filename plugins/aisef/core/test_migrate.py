#!/usr/bin/env python3
"""Testes do migrate (F-06): projeto anterior a 0.13 vai para a versao atual sem perder nada, dry-run nao grava,
segunda execucao nao muda nada e o doctor avisa so quando ha o que migrar."""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_migrate as mg  # noqa: E402
import aisef_project as ap  # noqa: E402
import audit_chain  # noqa: E402

fails = total = 0


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)))
    fails += not cond


proj = os.path.join(work, "proj")
os.makedirs(proj)
ap.init(proj, "PRJ-MIG")
cfg_path = os.path.join(proj, ".aisef", "config.json")
cfg = ap.load_config(proj)
check("init grava plugin_version e profile solo", cfg.get("plugin_version") == mg.plugin_version() and cfg["profile"] == "solo", cfg)
check("projeto novo: nada a migrar e o doctor fica quieto", mg.plan(proj)[1] == [] and mg.status(proj) is None)

# simula um projeto da 0.12: sem profile nem plugin_version, com uma chave propria do usuario
old = {k: v for k, v in cfg.items() if k not in ("profile", "plugin_version")}
old["git"] = {"branch_per_feature": True}
ap.write_json(cfg_path, old)
before_txt = open(cfg_path, encoding="utf-8").read()
events_before = len(audit_chain.read_log_dir(os.path.join(proj, ".aisef", "audit")))
st = mg.status(proj)
check("doctor avisa projeto atras do plugin, com o comando", st and "aisef_migrate.py" in st and "--apply" in st, st)
_, changes = mg.plan(proj)
check("plano: profile team (preserva o comportamento) e plugin_version", [m for m, _d in changes] == ["0.13-profile", "plugin-version"]
      and "team" in changes[0][1], changes)
check("dry-run (main sem --apply) nao grava nada", mg.main(["--project", proj]) == 0
      and open(cfg_path, encoding="utf-8").read() == before_txt)
check("--apply aplica", [m for m, _d in mg.apply(proj)] == ["0.13-profile", "plugin-version"])
new = ap.load_config(proj)
check("depois: team, versao atual e nada perdido", new["profile"] == "team" and new["plugin_version"] == mg.plugin_version()
      and new["git"] == {"branch_per_feature": True} and new["project_id"] == "PRJ-MIG", new)
log = audit_chain.read_log_dir(os.path.join(proj, ".aisef", "audit"))
last = log[-1]
check("registra decision_recorded do usuario com as migracoes", len(log) == events_before + 1
      and last["event_type"] == "decision_recorded" and last["actor"]["type"] == "user"
      and last["data"]["migrations"] == ["0.13-profile", "plugin-version"], last)
check("segunda execucao: nada a migrar, nenhum evento novo", mg.apply(proj) == []
      and len(audit_chain.read_log_dir(os.path.join(proj, ".aisef", "audit"))) == len(log))
check("doctor quieto depois do migrate", mg.status(proj) is None)
check("perfil ja definido pelo usuario nunca e trocado", (lambda c: (c.update(profile="regulated", plugin_version="0.12.0"),
      ap.write_json(cfg_path, c), mg.apply(proj), ap.load_config(proj)["profile"])[-1])(ap.load_config(proj)) == "regulated")
check("versao mais nova que o plugin nao pede migrate", (lambda c: (c.update(plugin_version="99.0.0"), ap.write_json(cfg_path, c),
      mg.status(proj))[-1])(ap.load_config(proj)) is None)
check("sem .aisef/config.json sai 2", mg.main(["--project", work]) == 2)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
