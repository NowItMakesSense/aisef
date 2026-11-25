#!/usr/bin/env python3
"""AISEF setup (0.13, C-03): o que o init aplica no projeto, numa decisao so do usuario.

Antes cada passo do init era um pedido separado (ativar agentes, regras nativas, boas praticas, AGENTS.md/CLAUDE.md).
Agora a skill mostra o plano, o usuario desmarca o que nao quer (AskUserQuestion multiSelect) e um unico `--apply`
grava tudo; o gateway trata o comando como decisao do usuario e abre UM prompt nativo. Instalacoes de fora (Graphify,
skills, plugins) continuam separadas: baixam codigo de terceiros e cada uma tem o proprio prompt.

Itens:
    agents     ativa os Agent Contracts em draft (nucleo + stack; --roles limita)
    settings   regras nativas de segunda camada em .claude/settings.json (mescla, nunca apaga)
    practices  boas praticas em .claude/rules/aisef/ (nao sobrescreve arquivo mudado no projeto)
    docs       secao AISEF no AGENTS.md e uma linha no CLAUDE.md (acrescenta, nunca sobrescreve)
    sandbox    sandbox.enabled no .claude/settings.json (so em Linux, macOS e WSL2; F-08). Perfis team e regulated:
               tambem allowUnsandboxedCommands=false e denyRead ~/.aisef, em qualquer sistema (S-04)

    python -I aisef_setup.py --project .                               (plano: o que cada item faria)
    python -I aisef_setup.py --project . --apply [--only agents,docs] [--roles backend,qa]
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_practices  # noqa: E402
import aisef_project as ap  # noqa: E402

ITEMS = ("agents", "settings", "practices", "docs", "sandbox")
TEMPLATE = os.path.join(HERE, "templates", "AGENTS.aisef.md")
CLAUDE_LINE = "Este projeto usa o AISEF (plugin aisef): estado em .aisef/, regras em AGENTS.md (secao AISEF)."


def _drafts(project):
    d = os.path.join(ap.aisef_dir(project), "contracts", "agents")
    out = []
    for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if name.endswith(".json"):
            with open(os.path.join(d, name), encoding="utf-8") as fh:
                if json.load(fh).get("status") == "draft":
                    out.append(name[:-5])
    return out


def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def _docs_plan(project):
    out = []
    agents_md = _read(os.path.join(project, "AGENTS.md"))
    if agents_md is None:
        out.append("criar AGENTS.md com a secao AISEF")
    elif "## AISEF" not in agents_md:
        out.append("acrescentar a secao AISEF ao fim do AGENTS.md")
    claude_md = _read(os.path.join(project, "CLAUDE.md"))
    if claude_md is None or CLAUDE_LINE not in claude_md:
        out.append(("acrescentar" if claude_md is not None else "criar CLAUDE.md com") + " a linha do AISEF no CLAUDE.md")
    return out


def plan(project, roles=None):
    """{item: [o que faria]} so com o que ainda falta. Item vazio fica de fora."""
    drafts = _drafts(project)
    if roles:
        drafts = [r for r in drafts if r in roles]
    _path, added = ap.native_settings(project, apply=False)
    settings = ["ask: %s" % r for r in added["ask"]] + ["deny: %s" % r for r in added["deny"]] + added["settings"]
    practices = ["%s (%s)" % (r["target"], r["state"]) for r in aisef_practices.plan(project)
                 if r["state"] not in ("igual", "modificado no projeto")]
    import aisef_env
    profile = ap.load_config(project).get("profile")
    sb = aisef_env.sandbox_status(project)
    if profile in aisef_env.STRICT_PROFILES:  # S-04: politica do projeto, gravada em qualquer sistema
        sandbox = ["%s em .claude/settings.json" % m for m in
                   aisef_env.sandbox_missing(profile, aisef_env.sandbox_effective(project))]
    else:
        sandbox = ["sandbox.enabled = true em .claude/settings.json"] if sb["supported"] and not sb["enabled"] else []
    out = {"agents": drafts, "settings": settings, "practices": practices, "docs": _docs_plan(project), "sandbox": sandbox}
    return {k: v for k, v in out.items() if v}


def _apply_docs(project):
    done = []
    path = os.path.join(project, "AGENTS.md")
    current = _read(path)
    section = _read(TEMPLATE).rstrip("\n") + "\n"
    if current is None:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(section)
        done.append("AGENTS.md criado")
    elif "## AISEF" not in current:
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(("\n" if current.endswith("\n") else "\n\n") + section)
        done.append("secao AISEF no AGENTS.md")
    path = os.path.join(project, "CLAUDE.md")
    current = _read(path)
    if current is None or CLAUDE_LINE not in current:
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(("" if not current or current.endswith("\n") else "\n") + CLAUDE_LINE + "\n")
        done.append("linha do AISEF no CLAUDE.md")
    return done


def apply(project, only=ITEMS, roles=None):
    """Aplica os itens escolhidos que ainda faltam. Devolve {item: [feito]}; registra uma decisao do usuario."""
    todo = plan(project, roles)
    done = {}
    if "agents" in only and "agents" in todo:
        done["agents"] = ap.activate_agents(project, todo["agents"])
    if "settings" in only and "settings" in todo:
        ap.native_settings(project, apply=True)
        done["settings"] = todo["settings"]
    if "practices" in only and "practices" in todo:
        done["practices"] = aisef_practices.apply(project)[0]
    if "docs" in only and "docs" in todo:
        done["docs"] = _apply_docs(project)
    if "sandbox" in only and "sandbox" in todo:
        path = os.path.join(project, ".claude", "settings.json")
        cur = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
        import aisef_env
        ap.write_json(path, aisef_env.sandbox_merge(cur, ap.load_config(project).get("profile")))
        done["sandbox"] = todo["sandbox"]
    done = {k: v for k, v in done.items() if v}
    if done:
        ap.append(project, {"event_type": "decision_recorded", "actor": {"type": "user", "id": "user"},
                            "summary": "setup do AISEF aplicado: " + "; ".join(
                                "%s (%d)" % (k, len(v)) for k, v in done.items()),
                            "data": {"setup": {k: len(v) for k, v in done.items()}}})
    return done


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project", default=".")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--only", default=",".join(ITEMS), help="itens separados por virgula: " + ", ".join(ITEMS))
    p.add_argument("--roles", help="agentes a ativar (padrao: todos os drafts)")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    project = os.path.abspath(a.project)
    if not os.path.isfile(os.path.join(project, ".aisef", "config.json")):
        print("sem .aisef/config.json em %s: rode o init antes" % project)
        return 2
    only = [x for x in a.only.split(",") if x]
    bad = [x for x in only if x not in ITEMS]
    if bad:
        print("item desconhecido: %s (use %s)" % (", ".join(bad), ", ".join(ITEMS)))
        return 2
    roles = [r for r in (a.roles or "").split(",") if r] or None
    res = apply(project, only, roles) if a.apply else {k: v for k, v in plan(project, roles).items() if k in only}
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    if not res:
        print("nada a fazer: o setup ja esta aplicado")
        return 0
    print("aplicado:" if a.apply else "plano (nada gravado; desmarque o que nao quiser e rode com --apply --only ...):")
    for item, lines in res.items():
        print("  %s (%d)" % (item, len(lines)))
        for x in lines[:12]:
            print("    - %s" % x)
        if len(lines) > 12:
            print("    - ... mais %d" % (len(lines) - 12))
    return 0


if __name__ == "__main__":
    sys.exit(main())
