#!/usr/bin/env python3
"""AISEF doctor: hook SessionStart. Confere o ambiente uma vez por sessao e so fala quando ha problema
(sem problema, nao gasta nenhum token). Nunca bloqueia nada. Somente stdlib."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "core"))
import userlibs  # noqa: E402,F401  (o diagnostico enxerga o mesmo que os hooks)



def _aisef_root(project):
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core"))
        import aisef_git
        return aisef_git.aisef_root(project)
    except Exception:
        return project

def commit_advice(project, cfg):
    """Repositorio Git sem nenhum commit: o verify pula a varredura de segredos e o diff sem ninguem perceber.
    Le so o .git local. Fora de um repositorio, quem avisa e o remote_advice."""
    import subprocess

    def git(*args):
        try:
            return subprocess.run(["git", "-C", project] + list(args), capture_output=True, text=True,
                                  timeout=5).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return None
    if not git("rev-parse", "--git-dir") or git("rev-parse", "--verify", "--quiet", "HEAD"):
        return None
    return ("o repositorio Git nao tem nenhum commit: o verify pula a varredura de segredos e o diff, e nao ha ponto "
            "fixo para code-review nem PR. Leve ao usuario o commit inicial (pede aprovacao: git_operation commit; "
            "acao first_commit do next)")


def remote_advice(project, cfg):
    """Projeto sem repositorio Git, ou sem o remote: nenhum push vai funcionar. Le so o .git local (sem rede)."""
    import subprocess
    import aisef_project as ap
    gitcfg, _ = ap.git_settings(cfg)
    remote = gitcfg["remote"]

    def git(*args):
        try:
            r = subprocess.run(["git", "-C", project] + list(args), capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return None
        return r.stdout.strip() if r.returncode == 0 else None
    if git("rev-parse", "--git-dir") is None:
        if not (gitcfg["branch_per_feature"] or gitcfg["delete_branch_after_merge"]):
            return None  # projeto sem Git e sem fluxo de branch configurado: nada a avisar
        return ("o projeto nao e um repositorio Git: nenhum commit nem push vai funcionar. Pergunte ao usuario se o "
                "projeto ja existe no GitHub (gh repo view <nome>) e, com o OK dele, rode git init -b %s e ligue "
                "ou crie o repositorio (acao setup_remote do next)" % gitcfg["base_branch"])
    if not git("remote", "get-url", remote):
        return ("o repositorio Git nao tem o remote '%s': nenhum push vai funcionar. Antes do primeiro push, pergunte "
                "ao usuario se o projeto ja tem repositorio no GitHub (gh repo view <nome>) e ligue (git remote add) "
                "ou crie (gh repo create --private --source . --remote %s); as duas sao decisao dele" % (remote, remote))
    return None


def problems(project):
    found = []
    if sys.version_info < (3, 10):
        found.append("Python %d.%d e antigo para o AISEF (precisa de 3.10+)" % sys.version_info[:2])
    import aisef_env
    libs = aisef_env.diagnose()  # so executa outros Pythons quando falta biblioteca (C-02)
    if libs:
        found.append(libs)
    root = os.path.join(project, ".aisef")
    try:
        import aisef_env as _env
        import aisef_project as _ap
        sb = _env.sandbox_advice(project, _ap.load_config(project))  # F-08
        if sb:
            found.append(sb)
    except Exception:
        pass
    try:
        import aisef_migrate
        mig = aisef_migrate.status(project)  # F-06: projeto atras do plugin
        if mig:
            found.append(mig)
    except Exception:
        pass
    try:
        import aisef_project as ap
        cfg = ap.load_config(project)
        key_id = ap.audit_settings(cfg)["key_id"]
        signed = any(n.endswith(".pem") for n in os.listdir(os.path.join(root, "keys")))
        if signed and not os.path.exists(ap.private_key_path(cfg["project_id"], key_id)):
            found.append("o log e assinado, mas a chave privada %s nao existe nesta maquina: nenhum evento sera "
                         "registrado (confira AISEF_HOME)" % ap.private_key_path(cfg["project_id"], key_id))
        head_path = ap.external_head_path(cfg["project_id"])
        last = ap.last_event(os.path.join(root, "audit"))
        if signed and last and os.path.exists(head_path):
            with open(head_path, encoding="utf-8") as fh:
                head = json.load(fh)
            if head.get("sequence") != last["sequence"] or head.get("hash") != last["hash"]:
                found.append("o fim do log nao confere com o head assinado externo: rode aisef-check antes de continuar")
        drafts = []
        agents_dir = os.path.join(root, "contracts", "agents")
        for name in sorted(os.listdir(agents_dir)) if os.path.isdir(agents_dir) else []:
            with open(os.path.join(agents_dir, name), encoding="utf-8") as fh:
                if json.load(fh).get("status") == "draft":
                    drafts.append(name[:-5])
        if os.path.isdir(agents_dir) and not os.path.exists(os.path.join(agents_dir, "implementer.json")):
            found.append("projeto anterior a 0.6.0: falta o agente implementer (fatias verticais com TDD). Proponha ao "
                         "usuario `aisef_project.py agents --project .` e depois `agents --project . --activate --roles implementer`")
        if drafts:
            found.append("agentes ainda em draft (bloqueados pelo gateway): %s. Peca ao usuario para aprova-los "
                         "(aisef-init, passo 4)" % ", ".join(drafts))
        gst = ap.graphify_status(project, cfg)
        if gst["enabled"] and not gst["exists"]:
            found.append("o Graphify esta ligado (padrao do AISEF), mas nao ha grafo em %s. Ofereca ao usuario instalar "
                         "e gerar (aisef-tooling, secao 6; GRAPHIFY_BACKEND=%s) ou desligar com \"graphify\": "
                         "{\"enabled\": false} no .aisef/config.json" % (gst["graph"], gst["backend"]))
        elif gst["stale"]:
            found.append("o grafo do Graphify esta velho (%s mudou depois dele): regenere antes de delegar "
                         "(aisef-tooling, secao 6)" % gst["newer_source"])
        remote_warn = remote_advice(project, cfg)
        if remote_warn:
            found.append(remote_warn)
        commit_warn = commit_advice(project, cfg)
        if commit_warn:
            found.append(commit_warn)
        settings = os.path.join(project, ".claude", "settings.json")
        perms = {}
        if os.path.exists(settings):
            with open(settings, encoding="utf-8") as fh:
                perms = json.load(fh).get("permissions", {})
        if "Bash(git commit:*)" not in perms.get("ask", []) or perms.get("disableBypassPermissionsMode") != "disable":
            found.append("as regras nativas de segunda camada nao estao no .claude/settings.json: proponha ao usuario "
                         "`aisef_project.py settings --project . --apply`")
    except Exception as exc:
        found.append("nao foi possivel conferir o estado do AISEF (%s)" % exc)
    return found


MAX_STATE = 1500


def session_state(project):
    """Resumo curto do estado (fase, em andamento, decisoes pendentes) para reinjetar depois de /compact ou /resume.
    None quando nao ha nada em andamento (zero tokens)."""
    import aisef_next as nx
    res = nx.compute_next(project)
    g = res["guide"]
    if g["phase"] == "done" and not res["stop_reason"]:
        return None
    running = sorted(t for t, s in res["states"].items() if s == "in_progress")
    pending = [a.get("request_id") or a.get("source") for a in res["actions"] if a["kind"] == "await_decision"]
    lines = ["AISEF (estado reconstruido do disco depois de compact/resume; o log e os contratos sao a fonte de verdade):",
             "- fase: %s; proximo passo: %s" % (g["phase"], g["steps"][0] if g["steps"] else "-")]
    if running:
        lines.append("- em andamento (agentes podem ainda notificar): %s" % ", ".join(running))
    if pending:
        lines.append("- decisoes do usuario pendentes: %s" % ", ".join(str(p) for p in pending))
    if res["stop_reason"]:
        lines.append("- parado: %s" % res["stop_reason"])
    lines.append("- retome com: python -I <CORE>/aisef_project.py next --project .")
    return "\n".join(lines)[:MAX_STATE]


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    project = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    project = _aisef_root(project)  # L-02a: worktree grava no .aisef do repositorio principal
    if not os.path.exists(os.path.join(project, ".aisef", "config.json")):
        return
    found = problems(project)
    parts = []
    if found:
        parts.append("AISEF doctor encontrou problemas; avise o usuario:\n- " + "\n- ".join(found))
    if data.get("source") in ("resume", "compact"):
        try:
            st = session_state(project)
        except Exception:
            st = None
        if st:
            parts.append(st)
    if parts:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n\n".join(parts)}},
                         ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # diagnostico nunca atrapalha a sessao
    sys.exit(0)
