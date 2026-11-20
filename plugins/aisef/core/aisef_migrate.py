#!/usr/bin/env python3
"""AISEF migrate (0.13, F-06): leva um projeto .aisef/ para a versao atual do plugin, sem perder nada.

Migracoes ordenadas e idempotentes (rodar duas vezes nao muda nada na segunda). Por padrao so mostra o plano
(dry-run). `--apply` grava e registra no log um evento `decision_recorded` do usuario; o gateway trata o comando
como decisao do usuario e abre o prompt nativo.

    python -I aisef_migrate.py --project .            (plano: o que mudaria)
    python -I aisef_migrate.py --project . --apply    (aplica; decisao do usuario)

Cada migracao preserva o comportamento que o projeto ja tinha. Exemplo: projeto anterior a 0.13 sem `profile`
ganha `profile: team` (o ciclo completo continua o padrao), nao o `solo` dos projetos novos.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_project as ap  # noqa: E402

PLUGIN_JSON = os.path.join(os.path.dirname(HERE), ".claude-plugin", "plugin.json")


def plugin_version():
    with open(PLUGIN_JSON, encoding="utf-8") as fh:
        return json.load(fh)["version"]


def parse_version(v):
    try:
        return tuple(int(x) for x in str(v).split("-")[0].split("."))
    except ValueError:
        return (0,)


def _profile(cfg, project):
    if "profile" in cfg:
        return None
    cfg["profile"] = "team"
    return "profile: team (perfil novo da 0.13; team mantem o ciclo completo como padrao, como antes)"


def _plugin_version(cfg, project):
    current = plugin_version()
    if cfg.get("plugin_version") == current:
        return None
    before = cfg.get("plugin_version") or "anterior a 0.13"
    cfg["plugin_version"] = current
    return "plugin_version: %s -> %s" % (before, current)


def _telemetry(cfg, project):
    a = cfg.setdefault("audit", {})
    if a.get("telemetry") in ("split", "signed"):
        return None
    a["telemetry"] = "split"
    return ("audit.telemetry: split (0.14: edicoes de arquivo e MCP liberados vao para a telemetria; o log assinado "
            "fica com ciclo de vida, decisoes, shell e o que o gateway negou ou perguntou)")


def _worktrees_ignore(cfg, project):
    """L-02: os worktrees das fatias ficam em .aisef/worktrees/, fora do Git."""
    path = os.path.join(ap.aisef_dir(project), ".gitignore")
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        text = ""
    if "worktrees/" in text.split():
        return None
    return ".aisef/.gitignore: worktrees/ (L-02: worktrees das fatias fora do Git)"  # grava so no apply


def _write_worktrees_ignore(project):
    path = os.path.join(ap.aisef_dir(project), ".gitignore")
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        text = ""
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(("" if not text or text.endswith("\n") else "\n") + "worktrees/\n")


# (id, funcao). Ordem importa; plugin_version sempre por ultimo.
MIGRATIONS = [("0.13-profile", _profile), ("0.14-telemetry", _telemetry), ("0.14-worktrees-ignore", _worktrees_ignore),
              ("plugin-version", _plugin_version)]


def plan(project):
    """(config migrado, [(id, descricao)]) sem gravar nada."""
    cfg = ap.load_config(project)
    changes = []
    for mid, fn in MIGRATIONS:
        desc = fn(cfg, project)
        if desc:
            changes.append((mid, desc))
    return cfg, changes


def status(project):
    """Para o doctor: None se o projeto esta em dia; senao o texto do aviso."""
    cfg = ap.load_config(project)
    have, want = cfg.get("plugin_version"), plugin_version()
    if have and parse_version(have) >= parse_version(want):
        return None
    return ("projeto AISEF em %s e o plugin em %s: veja o que muda com `python -I <CORE>/aisef_migrate.py --project .` "
            "e aplique com --apply (decisao do usuario)" % (have or "versao anterior a 0.13", want))


def apply(project):
    cfg, changes = plan(project)
    if not changes:
        return []
    ap.write_json(os.path.join(ap.aisef_dir(project), "config.json"), cfg)
    if any(m == "0.14-worktrees-ignore" for m, _d in changes):
        _write_worktrees_ignore(project)
    ap.append(project, {"event_type": "decision_recorded", "actor": {"type": "user", "id": "user"},
                        "summary": "migrate para %s: %s" % (cfg["plugin_version"], "; ".join(d for _m, d in changes)),
                        "data": {"migrations": [m for m, _d in changes]}})
    return changes


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project", default=".")
    p.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)
    project = os.path.abspath(a.project)
    if not os.path.isfile(os.path.join(project, ".aisef", "config.json")):
        print("sem .aisef/config.json em %s" % project)
        return 2
    changes = apply(project) if a.apply else plan(project)[1]
    if not changes:
        print("projeto em dia com o plugin %s; nada a migrar" % plugin_version())
        return 0
    print(("aplicado:" if a.apply else "plano (nada gravado; use --apply):"))
    for mid, desc in changes:
        print("  - [%s] %s" % (mid, desc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
