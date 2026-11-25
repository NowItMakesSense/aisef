#!/usr/bin/env python3
"""AISEF Execution Gateway: hook PreToolUse do Claude Code (v0.1). Trata Bash e PowerShell como shell.

Classifica cada chamada de ferramenta em (recurso, acao, ambiente), resolve o nivel pela politica
(permission-policy.v0.1.json + .aisef/policy.local.json, so mais restritivo) e traduz:

    allow              -> sem decisao (o fluxo normal de permissoes do Claude Code segue)
    approve_scope      -> sem decisao se houver autorizacao de escopo ativa que cubra; senao 'ask'
    approve_operation  -> 'ask' (prompt nativo: o modelo nao consegue responder por voce)
    approve_reinforced -> 'ask' so se houver aprovacao reforcada aprovada, valida e nao usada para a
                          operacao EXATA em .aisef/authorizations/; senao 'deny'
    deny               -> 'deny'

So atua em projetos com .aisef/config.json. Falha fechado: erro interno vira 'deny'. Somente stdlib.
"""
import datetime
import fnmatch
import glob
import json
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # python -I nao poe a pasta do script no path
from gateway_rules import *  # noqa: E402,F401,F403  (H-01)
from gateway_rules import _classify_text, _home_secret_dirs  # noqa: E402,F401
import gateway_deps  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.join(os.path.dirname(HERE), "core")
POLICY_PATH = os.path.join(CORE, "permission-policy.v0.1.json")
LEVELS = ["allow", "approve_scope", "approve_operation", "approve_reinforced", "deny"]



def _aisef_root(project):
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core"))
        import aisef_git
        return aisef_git.aisef_root(project)
    except Exception:
        return project

def emit(decision, reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": decision,
        "permissionDecisionReason": reason}}, ensure_ascii=False))
    sys.exit(0)


def record_attempt(project, data, decision, reason):
    """Tentativa negada ou levada a aprovacao vai para o log (o que roda de fato o PostToolUse registra).
    Nunca muda a decisao: se o registro falhar, so avisa."""
    try:
        sys.path.insert(0, CORE)
        import aisef_project
        import audit_chain
        inp = data.get("tool_input") or {}
        what = (inp.get("command") or inp.get("file_path") or inp.get("path") or "")[:300]
        if audit_chain.find_secrets({"x": what}):
            what = "[omitido: possivel segredo]"
        detail = {"tool": data.get("tool_name", ""), "gateway": decision, "reason": reason[:400], "target": what}
        if data.get("agent_type"):
            detail["subagent"] = data["agent_type"]
        if data.get("agent_id"):
            detail["agent_id"] = data["agent_id"]  # o painel prende a negacao a fatia exata desse agente
        aisef_project.append(project, {"event_type": "tool_used", "actor": {"type": "system", "id": "execution-gateway"},
                                       "summary": "Gateway: %s %s" % (decision, detail["tool"]), "data": detail,
                                       "panel_visible": decision == "deny"})
    except Exception as exc:  # o registro e acessorio; a decisao ja foi tomada
        sys.stderr.write("AISEF: tentativa nao registrada no log (%s)\n" % exc)


def stricter(a, b):
    return a if LEVELS.index(a) >= LEVELS.index(b) else b


def merge_policy(base, local):
    """Excecoes locais so podem endurecer a politica (conflict_resolution: most_restrictive_wins)."""
    for res, actions in (local.get("matrix") or {}).items():
        for action, by_env in actions.items():
            if action.startswith("$"):
                continue
            target = base["matrix"].setdefault(res, {}).setdefault(action, {})
            if isinstance(by_env, str):
                base["matrix"][res][action] = stricter(by_env, target) if isinstance(target, str) and target in LEVELS else by_env
                continue
            for env, lvl in by_env.items():
                cur = target.get(env)
                target[env] = stricter(lvl, cur) if cur in LEVELS else lvl
    return base


def level_for(policy, resource, action, env):
    """Passos 1-3 e 6 do resolution_algorithm. Nao classificado ou nao aplicavel -> o mais restritivo cabivel."""
    entry = policy["matrix"].get(resource, {}).get(action)
    if isinstance(entry, str):
        lvl = entry
    elif isinstance(entry, dict):
        lvl = entry.get(env if env in ("dev", "staging", "prod") else "prod")
    else:
        lvl = None
    if lvl not in LEVELS:
        # recurso/acao nao classificados ou 'not_applicable_via_git': tratar como sensivel
        lvl = "approve_operation" if env == "dev" else "approve_reinforced"
    return lvl


def apply_t1(policy, lvl, env):
    """Regra transversal T1: destrutivo sobe um nivel."""
    for rule in policy.get("transversal_rules", []):
        if rule.get("id") == "T1":
            floor = rule["minimum_level"].get(env, "approve_reinforced")
            return stricter(lvl, floor)
    return stricter(lvl, "approve_reinforced")


MOVE_RE = re.compile(r"(?:^|[;&|(]\s*)(?:cd|pushd|Set-Location|sl|chdir)\s")
GIT_C_RE = re.compile(r"""\bgit\s+-C\s+("[^"]+"|'[^']+'|[^\s;&|]+)""")


def git_context(cmd, cwd, config, project=None):
    """F-03: branch atual e se ela e de feature. L-02: um unico `cd <pasta> &&` no inicio ou um unico `git -C <pasta>`
    apontando para dentro do projeto (ex.: o worktree da fatia) usa a branch dessa pasta. Qualquer outra mudanca de
    pasta (varios cd, --git-dir, --work-tree, pasta fora do projeto) deixa a branch desconhecida: vale a regra antiga."""
    if "git" not in cmd:
        return None
    sys.path.insert(0, CORE) if CORE not in sys.path else None
    import aisef_git
    g = config.get("git") if isinstance(config.get("git"), dict) else {}
    prefix, base = g.get("branch_prefix") or "feat/", g.get("base_branch") or "main"
    m = CD_PREFIX_RE.match(cmd)
    target = next((x for x in m.groups() if x), None) if m else None
    rest = cmd[m.end():] if m else cmd
    dash_c = {x.strip("\"'") for x in GIT_C_RE.findall(rest)}
    moved = bool(MOVE_RE.search(rest) or re.search(r"--git-dir|--work-tree", cmd) or len(dash_c) > 1 or (target and dash_c))
    target = target or (dash_c.pop() if len(dash_c) == 1 else None)
    branch = None
    if not moved:
        where = cwd
        if target:
            where = os.path.realpath(os.path.join(cwd, target))
            root = os.path.realpath(project or cwd)
            if os.path.normcase(where) != os.path.normcase(root) and \
                    not os.path.normcase(where).startswith(os.path.normcase(root) + os.sep):
                where = None  # pasta fora do projeto: branch desconhecida
        branch = aisef_git.current_branch(where) if where else None
    feature = aisef_git.is_feature_branch(branch, prefix, base) or bool(branch and branch.startswith("slice/"))
    return {"branch": branch, "feature": feature, "prefix": prefix, "base": base, "push_targets": [], "aisef_git": aisef_git}


def is_pending_request(tool, path, inp):
    """Propor um pedido ao Approval Center (Write de um pedido novo e pendente) nao e decidir."""
    if tool != "Write" or not re.search(r"(?:^|/)\.aisef/approvals/[^/]+\.json$", path) or os.path.exists(path):
        return False
    try:
        doc = json.loads(inp.get("content") or "")
    except ValueError:
        return False
    return isinstance(doc, dict) and doc.get("status") == "pending" and "decision" not in doc and "resulting_ref" not in doc


def scope_covers(project, resource, env, now, max_days=None, branches=None):
    """Autorizacao de escopo ativa que cobre o recurso. Para git_feature_branch (F-03), as branches do push precisam
    casar com resource_filters.branches; sem o filtro, nao cobre."""
    if resource == "git_feature_branch" and not branches:
        return None
    for path in glob.glob(os.path.join(project, ".aisef", "authorizations", "*.json")):
        try:
            a = load_json(path)
        except (OSError, ValueError):
            continue
        if a.get("kind") != "scope" or a.get("status") != "active" or a.get("environment") != env:
            continue
        if resource not in a.get("resources", []):
            continue
        if resource == "git_feature_branch":
            pats = (a.get("resource_filters") or {}).get("branches") or []
            if not pats or not all(any(fnmatch.fnmatchcase(b, p) for p in pats) for b in branches):
                continue
        v = a.get("validity", {})
        try:
            start = datetime.datetime.fromisoformat(v["valid_from"])
            end = datetime.datetime.fromisoformat(v["valid_until"])
        except (KeyError, ValueError):
            continue
        if max_days is not None and (end - start).total_seconds() > max_days * 86400:
            continue  # escopo acima do teto da politica (7 dias) nao vale
        if start <= now <= end:
            return a.get("authorization_id", os.path.basename(path))
    return None


CD_PREFIX_RE = re.compile(r"""^\s*cd\s+(?:"([^"]*)"|'([^']*)'|([^\s;&|]+))\s*(?:&&|;)\s*""")


def _same_dir(path, project, cwd=None):
    """`path` (de um `cd`) aponta para a raiz do projeto? Aceita caminho relativo ao cwd e o estilo Git Bash (/c/...)."""
    m = re.match(r"^/([a-zA-Z])(/.*)?$", path)
    if os.name == "nt" and m:
        path = m.group(1) + ":" + (m.group(2) or "/")
    if not os.path.isabs(path):
        path = os.path.join(cwd or project, path)

    def canon(p):
        return os.path.normcase(os.path.normpath(os.path.abspath(p)))
    return canon(path) == canon(project)


def strip_project_cd(cmd, project, cwd=None):
    """Remove prefixos `cd <raiz do projeto> &&` e `cd <raiz do projeto>;` antes de comparar com a operacao exata
    aprovada. Um `cd` para outro diretorio fica no comando: ali a operacao seria outra."""
    while True:
        m = CD_PREFIX_RE.match(cmd)
        if not m:
            break
        target = next(g for g in m.groups() if g is not None)
        if not _same_dir(target, project, cwd):
            break
        cmd = cmd[m.end():]
    return cmd.strip()


def reinforced_for(project, operation, now, cwd=None):
    operation = strip_project_cd(operation, project, cwd)
    for path in glob.glob(os.path.join(project, ".aisef", "authorizations", "*.json")):
        try:
            a = load_json(path)
        except (OSError, ValueError):
            continue
        if a.get("kind") != "reinforced" or a.get("status") != "approved" or a.get("consumed"):
            continue
        if strip_project_cd(a.get("operation") or "", project, cwd) != operation:
            continue
        try:
            if now <= datetime.datetime.fromisoformat(a["expires_at"]):
                return a.get("approval_id", os.path.basename(path))
        except (KeyError, ValueError):
            continue
    return None


ENV_ORDER = ["dev", "staging", "prod"]


def agent_contract(project, data):
    """Agent Contract do subagente que fez a chamada (aisef:backend -> contracts/agents/backend.json), se houver."""
    name = data.get("agent_type") or ""
    if not name:
        return None
    path = os.path.join(project, ".aisef", "contracts", "agents", name.split(":")[-1] + ".json")
    return load_json(path) if os.path.exists(path) else None


def catalog_agent_without_contract(data):
    """Subagente do plugin (aisef:<papel do catalogo>) chamado sem Agent Contract no projeto: sem teto, ele nao age.
    Le o catalogo so neste caminho raro, para nao pesar no hook."""
    name = data.get("agent_type") or ""
    if not name.startswith("aisef:"):
        return False
    try:
        with open(os.path.join(CORE, "agents", "catalog.v0.1.json"), encoding="utf-8") as fh:
            ids = {r["id"] for r in json.load(fh)["roles"] if r.get("generate_agent", True)}
    except (OSError, ValueError, KeyError):
        return False
    return name.split(":")[-1] in ids


def enforce_ceiling(contract, tool, items, env):
    """O Agent Contract e um TETO: nunca concede nada, so restringe (o resto segue a politica)."""
    aid = contract.get("agent_id", "?")
    if contract.get("status") != "active":
        raise Decision("deny", "agente %s nao esta ativo: o usuario ainda nao aprovou o Agent Contract dele" % aid)
    ceiling = contract.get("permission_ceiling", {})
    allowed = set(ceiling.get("resources", []))
    max_env = ceiling.get("max_environment", "dev")
    if env in ENV_ORDER and max_env in ENV_ORDER and ENV_ORDER.index(env) > ENV_ORDER.index(max_env):
        raise Decision("deny", "agente %s so pode atuar ate '%s' (ambiente atual: %s)" % (aid, max_env, env))
    if tool in EDIT_TOOLS and "repo_code" not in allowed:
        raise Decision("deny", "agente %s nao tem repo_code no teto de permissao: nao pode editar arquivos" % aid)
    for resource, action, _env, _destr, label in items:
        if resource == "aisef_decision":
            raise Decision("deny", "agente %s nao registra decisoes do usuario" % aid)
        if resource == "git":
            ops = ceiling.get("git_operations", ["status_log_diff"])
            # F-03: quem pode commitar pode preparar o commit e commitar na branch de feature (contratos antigos valem)
            ok = action in ops or (action in ("commit_feature", "local_staging", "worktree_local") and "commit" in ops)
            if not ok:
                raise Decision("deny", "agente %s nao pode solicitar %s (teto Git: %s)" % (aid, label, ", ".join(ops)))
        elif resource == "git_feature_branch":
            if "push" not in ceiling.get("git_operations", []):
                raise Decision("deny", "agente %s nao faz push (teto Git: %s); o orquestrador faz"
                               % (aid, ", ".join(ceiling.get("git_operations", []))))
        elif resource not in allowed:
            raise Decision("deny", "agente %s nao tem %s no teto de permissao (%s)" % (aid, resource, label))


def session_mode(project):
    try:
        with open(os.path.join(project, ".aisef", "session", "mode.json"), encoding="utf-8") as fh:
            return json.load(fh).get("mode", "exec")
    except (OSError, ValueError):
        return "exec"


def ask_mode_block(tool, inp, config):
    """Motivo do bloqueio no modo Ask, ou None se a chamada so le."""
    if tool in EDIT_TOOLS:
        return "modo Ask: nada e editado; responda a pergunta (para executar, o usuario troca com /aisef:modo exec)"
    if tool in SHELL_TOOLS:
        cmd = inp.get("command", "") or ""
        if re.search(r"aisef_project\.py\s+mode\b", cmd):
            return None  # sair do modo: segue para o prompt nativo
        if not read_only_command(cmd):
            return "modo Ask: so comandos de leitura (git status/log/diff, ls, cat, grep...); nada e executado"
    if tool.startswith("mcp__") and not mcp_allowed(tool, config, load_patterns()):
        return "modo Ask: ferramenta MCP fora de mcp_allow"
    return None


def decide(data, project, policy, patterns, config, now):
    tool = data.get("tool_name", "")
    inp = data.get("tool_input") or {}
    if session_mode(project) == "ask":
        why = ask_mode_block(tool, inp, config)
        if why:
            raise Decision("deny", why)
    cwd = data.get("cwd") or project
    if tool in SHELL_TOOLS:
        secret = home_secret_ref(inp.get("command", "") or "", cwd)
    else:
        secret = any(home_secret_ref(inp.get(k), cwd, is_path=True)
                     for k in ("file_path", "path", "notebook_path", "pattern", "glob") if isinstance(inp.get(k), str))
    if secret:
        raise Decision("deny", "a chave privada de assinatura e as ancoras do AISEF (~/.aisef/keys e anchors) ficam fora do "
                               "alcance dos agentes; os scripts do AISEF as usam por dentro")
    env = config.get("environment", "dev")
    if env not in ("dev", "staging", "prod"):
        env = "prod"  # defaults.unknown_environment

    items = []
    operation = ""
    if tool in SHELL_TOOLS:
        operation = inp.get("command", "") or ""
        if GIT_SKIP_HOOKS_RE.search(operation):
            raise Decision("deny", "pular hooks ou assinatura do Git (--no-verify, --no-gpg-sign) esconde problemas: "
                                   "corrija o que o hook acusa")
        gctx = git_context(operation, cwd, config, project)
        items = classify_bash(operation, patterns, env, "ps" if tool == "PowerShell" else "sh", gctx)
        hint = home_secret_hint(operation, cwd)
        if hint:
            items.append(("unclassified", "execute", env, False, hint))
        if config.get("dependency_check") == "online":  # S-05: so com rede quando o usuario liga
            sys.path.insert(0, CORE) if CORE not in sys.path else None
            items = gateway_deps.enrich(items)
        if inp.get("dangerouslyDisableSandbox") is True:  # F-08: sair do sandbox e decisao do usuario
            items.append(("unclassified", "execute", env, False, "comando pedindo para rodar fora do sandbox"))
    else:
        paths = [norm(inp.get(k)) for k in ("file_path", "path", "notebook_path", "pattern", "glob") if isinstance(inp.get(k), str)]
        operation = tool + " " + " ".join(paths)
        for p in paths:
            if tool in EDIT_TOOLS:
                resource, label = write_resource(p, patterns)
                if resource == "aisef_audit":
                    raise Decision("deny", "o log de auditoria e as chaves do AISEF so podem ser alterados pelo hook de auditoria")
                if resource == "aisef_decision" and is_pending_request(tool, p, inp):
                    continue  # propor pedido pendente nao e decidir
                if resource != "repo_code":
                    items.append((resource, "write", env, False, label))
                written = [inp.get("content"), inp.get("new_string"), inp.get("new_source")] + \
                          [e.get("new_string") for e in inp.get("edits") or [] if isinstance(e, dict)]
                if any(isinstance(w, str) and code_secret_ref(w) for w in written):
                    items.append(("unclassified", "execute", env, False, "arquivo com codigo que monta o caminho da "
                                  "chave ou das ancoras do AISEF na home (rodaria depois, fora do gateway)"))
            elif tool in READ_TOOLS and is_sensitive_path(p, patterns):
                items.append(("sensitive_files", "read_content", env, False, "arquivo sensivel"))

    if tool.startswith("mcp__"):
        # Servidor MCP pode escrever arquivos, acessar banco ou fazer deploy sem passar pelo Bash:
        # so as ferramentas que o usuario liberou em config.json -> mcp_allow (globs) ou numa confianca com prazo
        # (authorizations, kind mcp_tool) passam direto. Ferramenta que executa codigo nao entra por glob (F-01).
        max_days = policy.get("scope_authorization_schema_ref", {}).get("validity_max_days") or 7
        if not mcp_allowed(tool, config, patterns) and not mcp_trust(project, tool, now, patterns, max_days):
            hint = " (executa codigo: so por nome exato ou confianca com --allow-code-execution)" if mcp_runs_code(tool, patterns) else ""
            items.append(("unclassified", "execute", env, False,
                          "ferramenta MCP %s sem confianca do usuario%s; para confiar por ate %d dias: "
                          "aisef_mcp.py trust --tool %s" % (tool, hint, max_days, tool)))
    elif tool == "WebFetch" and WEBFETCH_SECRET_RE.search(inp.get("url") or ""):
        raise Decision("deny", "a URL parece carregar um segredo (token/chave na query): possivel vazamento de dados")

    contract = agent_contract(project, data)
    if contract is not None:
        enforce_ceiling(contract, tool, items, env)
    elif (tool in EDIT_TOOLS or items) and catalog_agent_without_contract(data):
        raise Decision("deny", "agente %s sem Agent Contract neste projeto: o orquestrador cria o draft "
                               "(`aisef_project.py agents --roles %s`) e o usuario o ativa antes de delegar"
                       % (data.get("agent_type"), data.get("agent_type", "").split(":")[-1]))

    worst, why, scoped = "allow", [], []
    for resource, action, item_env, destructive, label in items:
        if resource == "aisef_decision":
            lvl = "approve_operation"  # so o usuario decide aprovacoes (schema approval-request)
        else:
            eff_env = item_env if item_env in ("dev", "staging", "prod") else "prod"
            lvl = level_for(policy, resource, action, eff_env)
            if destructive:
                lvl = apply_t1(policy, lvl, eff_env)
            if lvl == "approve_scope":
                branches = (gctx or {}).get("push_targets") if tool in SHELL_TOOLS and resource == "git_feature_branch" else None
                auth = scope_covers(project, resource, eff_env, now,
                                    policy.get("scope_authorization_schema_ref", {}).get("validity_max_days"), branches)
                if auth:
                    scoped.append(auth)
                    lvl = "allow"
        if LEVELS.index(lvl) > LEVELS.index(worst):
            worst = lvl
        if lvl != "allow":
            why.append("%s (%s/%s) -> %s" % (label, resource, action or "nao classificado", lvl))

    conc = concurrency(data, project, tool, inp, items, now)
    if conc:
        worst = stricter(worst, "approve_operation")
        why.append(conc)

    if worst == "allow":
        return None, None
    reason = "AISEF: " + "; ".join(why)
    if data.get("permission_mode") == "bypassPermissions":
        # no modo que pula permissoes um 'ask' poderia passar sem ninguem ver: o que exige aprovacao e negado
        return "deny", reason + ". A sessao esta em modo bypassPermissions: operacoes que exigem aprovacao ficam bloqueadas."
    if worst in ("approve_scope", "approve_operation"):
        return "ask", reason + ". Aprove so se isso estiver dentro do que voce autorizou."
    if worst == "approve_reinforced":
        appr = reinforced_for(project, operation, now, data.get("cwd"))
        if appr:
            return "ask", reason + ". Aprovacao reforcada %s encontrada para esta operacao exata: confirme para consumi-la." % appr
        return "deny", (reason + ". Exige aprovacao reforcada de uso unico (diff, impacto, rollback, justificativa). "
                        "Peca ao usuario com /aisef:approve e repita a operacao exata depois de aprovada.")
    return "deny", reason


PUBLISH_OPS = ("commit", "commit_feature", "push", "pull_request", "merge", "release_publish")


def concurrency(data, project, tool, inp, items, now):
    """Outra sessao no mesmo projeto: editar o arquivo que ela tem alterado sem commit, ou commitar/publicar sem ver as
    mudancas dela, gera retrabalho ou leva o trabalho dela junto. Devolve o motivo (vira pergunta ao usuario) ou None.
    Falha no registro nunca bloqueia: o gateway segue com o resto das regras."""
    sid = data.get("session_id")
    try:
        sys.path.insert(0, CORE) if CORE not in sys.path else None
        import aisef_sessions as ses
        if tool in EDIT_TOOLS:
            hits = []
            paths = [inp[k] for k in ("file_path", "notebook_path") if isinstance(inp.get(k), str) and inp[k]]
            for p in paths:
                hits += ses.overlap(project, sid, p, now)
            if not hits:
                c = next((x for x in (ses.claimed_by_other(project, sid, p, now) for p in paths) if x), None)
                if not c:
                    return None
                return ("%s esta na area reservada pela %s. Para uma sessao nao afetar o trabalho da outra, trabalhe "
                        "numa parte separada; se o pedido exige mesmo esse arquivo, mostre ao usuario e combine a "
                        "divisao com ele antes (ver: python3 -I %s status --project . --session %s)"
                        % (c["file"], ses._label(c), os.path.join(CORE, "aisef_sessions.py").replace("\\", "/"), sid or "<id>"))
            h = hits[0]
            where = "nesta mesma pasta" if h["same_dir"] else "em %s (branch %s)" % (h["worktree"], h["branch"] or "?")
            return ("outra sessao (%s, %s%s) tem %s alterado sem commit %s: editar aqui duplica o trabalho ou conflita. "
                    "Mostre ao usuario e combine quem segue com esse arquivo (ver: python3 -I %s status --project . "
                    "--session %s --diff)" % (h["session"], "ativa, " if h["active"] else "", h["ago"], h["file"], where,
                                              os.path.join(CORE, "aisef_sessions.py").replace("\\", "/"), sid or "<id>"))
        if tool in SHELL_TOOLS and any(a in PUBLISH_OPS for _r, a, _e, _d, _l in items):
            found = ses.concurrent(project, sid, data.get("cwd") or project, now)
            if not found:
                return None
            return ("antes de commit, push, PR ou merge, mostre ao usuario as mudancas sem commit de outra sessao neste "
                    "projeto (retrabalho ou trabalho dela indo junto no commit):\n%s" % ses.render(found))
    except Exception as exc:
        sys.stderr.write("AISEF: checagem de outras sessoes falhou (%s)\n" % exc)
    return None


def heartbeat(data, project):
    """Batimento desta sessao em .aisef/runtime/sessions/ (fora do Git), para as outras sessoes a enxergarem.
    Devolve o aviso de coordenacao (uma vez por mudanca nas areas das outras sessoes) ou None."""
    if not data.get("session_id"):
        return None
    try:
        sys.path.insert(0, CORE) if CORE not in sys.path else None
        import aisef_sessions as ses
        ses.touch(project, data["session_id"], data.get("cwd"))
        return ses.coordination_notice(project, data["session_id"])
    except Exception:
        return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        emit("deny", "AISEF: entrada do hook ilegivel (falha fechada)")
    project = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    project = _aisef_root(project)  # L-02a: worktree grava no .aisef do repositorio principal
    config_path = os.path.join(project, ".aisef", "config.json")
    if not os.path.exists(config_path):
        sys.exit(0)  # projeto sem AISEF: o gateway nao interfere
    notice = None
    try:
        config = load_json(config_path)
        policy = load_json(POLICY_PATH)
        local = os.path.join(project, ".aisef", "policy.local.json")
        if os.path.exists(local):
            policy = merge_policy(policy, load_json(local))
        patterns = load_patterns()
        now = datetime.datetime.now(datetime.timezone.utc)
        notice = heartbeat(data, project)
        decision, reason = decide(data, project, policy, patterns, config, now)
    except Decision as d:
        decision, reason = d.level, "AISEF: " + d.reason
    except Exception as exc:
        emit("deny", "AISEF: erro no Execution Gateway (%s); falha fechada" % exc)
    if decision:
        record_attempt(project, data, decision, reason)
        emit(decision, reason + ("\n\n" + notice if notice else ""))
    extra = [t for t in (notice, nudge(data, project) if data.get("tool_name") in ("Grep", "Glob") else None) if t]
    if extra:  # um JSON so: o aviso de coordenacao e o lembrete do grafo juntos
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "\n\n".join(extra)}},
                         ensure_ascii=False))
    sys.exit(0)


def nudge(data, project):
    """Lembrete consultivo do grafo (graph_nudge) no mesmo processo: antes era um segundo Python por Grep/Glob."""
    try:
        sys.path.insert(0, CORE)
        sys.path.insert(1, HERE)
        import graph_nudge
        return graph_nudge.nudge_context(data, project)
    except Exception:
        return None


if __name__ == "__main__":
    main()
