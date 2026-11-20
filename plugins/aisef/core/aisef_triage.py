#!/usr/bin/env python3
"""AISEF triage (0.13, C-01, ADR 0023): escolhe em codigo o caminho de uma mudanca - quick, lean ou full.

O orquestrador estrutura o pedido (caminhos provaveis, tipos de mudanca, tamanho estimado, fatias, risco) e este
script decide, com os motivos. Antes a escolha entre caminho rapido e ciclo completo ficava com o modelo.

    quick  caminho rapido de manutencao (FEAT-MAINT): sem mudanca de comportamento, ate ~50 linhas e ~5 arquivos
    lean   caminho enxuto: Feature Contract curto, UMA fatia com TDD, sem blueprint, so o code-reviewer, validador
           independente e RTM completa
    full   ciclo completo: Grill, Spec, fatias, blueprint, revisores pelo roteamento, validador

Sinais que forcam full (todos em codigo, nunca opiniao do modelo):
- caminho que exige recurso alem de repo_code (mesma classificacao do gateway: segredo, config/CI/IaC, AISEF),
  migracao ou schema de banco, autenticacao/autorizacao/criptografia;
- tipo de mudanca: api, schema, security, ci, infra, dependency_breaking, public_contract, cross_module;
- risco high ou critical;
- mais de 1 fatia ou mais de MAX_FILES arquivos;
- tamanho desconhecido (sem --files).

Perfil (config.json -> profile, L-04): solo usa a triagem; team (padrao de projetos antigos) mantem o comportamento
anterior, quick ou full, e so sugere o lean; regulated desliga o quick (vira lean). O usuario sempre pode subir o
caminho (--force full); descer abaixo do calculado e erro do check (TRIAGE-OVERRIDDEN-DOWN).

Uso:
    python -I aisef_triage.py --project . --paths "src/x/*" --changes behavior --files 2 --lines 40 [--slices 1]
                              [--risk low] [--force full] [--json]
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "hooks"))

PATHS = ("quick", "lean", "full")
PROFILES = ("solo", "team", "regulated")
DEFAULT_PROFILE = "team"  # projeto sem profile no config: comportamento anterior a 0.13
FULL_CHANGES = {"api": "muda API publica", "schema": "muda schema de banco ou migracao",
                "security": "toca autenticacao, autorizacao, criptografia ou segredo", "ci": "muda CI/CD",
                "infra": "muda infraestrutura ou configuracao de producao",
                "dependency_breaking": "atualiza dependencia com quebra", "public_contract": "muda contrato publico (evento, SDK, CLI)",
                "cross_module": "muda o contrato entre modulos"}
QUICK_CHANGES = {"docs", "text", "typo", "rename_local", "lint", "dependency_patch", "config_local", "test_only"}
OTHER_CHANGES = {"behavior", "refactor", "ui", "bugfix"}
CHANGE_KINDS = set(FULL_CHANGES) | QUICK_CHANGES | OTHER_CHANGES
MAX_FILES = 5
MAX_QUICK_LINES = 50
DB_PATH_RE = re.compile(r"(^|/)(migrations?|alembic|db/migrate|schema\.prisma|flyway)(/|$)|\.sql$", re.I)
AUTH_PATH_RE = re.compile(r"(^|/)(auth|authn|authz|security|permissions?|crypto|oauth|sso|iam)(/|\.|_|$)", re.I)


def _gateway():
    import gateway
    return gateway, gateway.load_patterns()


def path_signals(paths):
    """Motivos de full vindos dos caminhos. Usa a mesma classificacao de escrita do gateway."""
    reasons = []
    try:
        gw, patterns = _gateway()
    except Exception:
        gw = patterns = None
    for p in paths:
        q = p.replace("\\", "/")
        if gw is not None:
            resource, label = gw.write_resource(q.rstrip("*/") or q, patterns)
            if resource != "repo_code":
                reasons.append("%s exige %s (%s)" % (p, resource, label))
                continue
        if DB_PATH_RE.search(q):
            reasons.append("%s e migracao ou schema de banco" % p)
        elif AUTH_PATH_RE.search(q):
            reasons.append("%s toca autenticacao, autorizacao ou criptografia" % p)
    return reasons


def compute(paths=(), changes=(), files=None, lines=None, slices=1, risk="low"):
    """Caminho calculado e motivos, sem perfil."""
    unknown = sorted(set(changes) - CHANGE_KINDS)
    if unknown:
        raise ValueError("tipo de mudanca desconhecido: %s (validos: %s)" % (", ".join(unknown), ", ".join(sorted(CHANGE_KINDS))))
    full = path_signals(paths)
    full += [FULL_CHANGES[c] for c in changes if c in FULL_CHANGES]
    if risk in ("high", "critical"):
        full.append("risco %s" % risk)
    if (slices or 1) > 1:
        full.append("%d fatias (o enxuto tem uma)" % slices)
    if files is None:
        full.append("tamanho desconhecido: estime os arquivos (--files)")
    elif files > MAX_FILES:
        full.append("%d arquivos (mais de %d)" % (files, MAX_FILES))
    if full:
        return "full", full
    changes = set(changes)
    if changes and changes <= QUICK_CHANGES and lines is not None and lines <= MAX_QUICK_LINES:
        return "quick", ["sem mudanca de comportamento (%s), ~%d linha(s) em %d arquivo(s)" % (
            ", ".join(sorted(changes)), lines, files)]
    why = "muda comportamento" if changes & {"behavior", "bugfix", "ui"} or not changes else "refatoracao"
    if lines is not None and lines > MAX_QUICK_LINES and changes <= QUICK_CHANGES and changes:
        why = "mais de %d linhas" % MAX_QUICK_LINES
    return "lean", ["%s, sem recurso sensivel, %d arquivo(s), uma fatia, risco %s" % (why, files, risk)]


def apply_profile(computed, profile):
    """Caminho efetivo pelo perfil. Devolve (caminho, nota)."""
    import aisef_workflow  # L-03: a sobreposicao do perfil vem do workflow.v0.1.json
    ov = aisef_workflow.profile(profile)
    if computed == "lean" and ov["lean"] == "suggest":
        return "full", ov["note"]
    if computed == "quick" and not ov["quick"]:
        return "lean", ov["note"]
    return computed, None


def triage(project=None, paths=(), changes=(), files=None, lines=None, slices=1, risk="low", force=None, profile=None):
    if profile is None:
        profile = DEFAULT_PROFILE
        if project:
            try:
                import aisef_project as ap
                profile = ap.load_config(project).get("profile") or DEFAULT_PROFILE
            except Exception:
                pass
    if profile not in PROFILES:
        raise ValueError("perfil invalido: %s (use %s)" % (profile, ", ".join(PROFILES)))
    computed, reasons = compute(paths, changes, files, lines, slices, risk)
    path, note = apply_profile(computed, profile)
    out = {"computed": computed, "path": path, "profile": profile, "reasons": reasons}
    if note:
        out["note"] = note
    if force:
        if force not in PATHS:
            raise ValueError("--force invalido: %s" % force)
        if PATHS.index(force) < PATHS.index(path):
            raise ValueError("nao da para descer de %s para %s: o calculo pediu %s por: %s"
                             % (path, force, path, "; ".join(reasons)))
        if force != path:
            out["forced_by_user"] = True
            out["path"] = force
    return out


def line(res):
    s = "Caminho: %s, porque %s" % (res["path"], "; ".join(res["reasons"]))
    if res.get("forced_by_user"):
        s += " (o calculo deu %s; o usuario pediu %s)" % (res["computed"], res["path"])
    if res.get("note"):
        s += ". " + res["note"]
    return s


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project", default=".")
    p.add_argument("--paths", nargs="*", default=[])
    p.add_argument("--changes", default="", help="lista separada por virgula: " + ", ".join(sorted(CHANGE_KINDS)))
    p.add_argument("--files", type=int)
    p.add_argument("--lines", type=int)
    p.add_argument("--slices", type=int, default=1)
    p.add_argument("--risk", default="low", choices=["low", "medium", "high", "critical"])
    p.add_argument("--force", choices=PATHS)
    p.add_argument("--profile", choices=PROFILES)
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    try:
        res = triage(os.path.abspath(a.project), a.paths, [c for c in a.changes.split(",") if c], a.files, a.lines,
                     a.slices, a.risk, a.force, a.profile)
    except ValueError as e:
        print("erro: %s" % e)
        return 2
    print(json.dumps(res, ensure_ascii=False, indent=2) if a.json else line(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
