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

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.join(os.path.dirname(HERE), "core")
POLICY_PATH = os.path.join(CORE, "permission-policy.v0.1.json")
PATTERNS_PATH = os.path.join(HERE, "sensitive_patterns.json")
LEVELS = ["allow", "approve_scope", "approve_operation", "approve_reinforced", "deny"]

# opcoes globais antes do subcomando (-C dir, -c chave=valor, --no-pager, --git-dir=x, -p...) sao puladas (F-02):
# sem isso, `git -c a=b push --force` virava "subcomando nao classificado" e so perguntava
GIT_RE = re.compile(r"(?:^|[;&|(]\s*|\s)git(?:\s+(?:-[Cc]\s+\S+|--[a-z][a-z-]*(?:=\S+)?|-[a-zA-Z]))*\s+([a-z][a-z-]*)([^;&|]*)", re.I)
DEPLOY_RE = re.compile(
    r"\b(?:terraform\s+(?:apply|destroy)|tofu\s+apply|pulumi\s+up|kubectl\s+(?:apply|delete|rollout)|"
    r"helm\s+(?:install|upgrade|uninstall)|serverless\s+deploy|sls\s+deploy|fly\s+deploy|vercel\s+.*--prod|"
    r"netlify\s+deploy\s+.*--prod|gcloud\s+\S+\s+deploy|aws\s+cloudformation\s+deploy|cdk\s+deploy)\b", re.I)
DEPLOY_DESTRUCTIVE_RE = re.compile(
    r"\b(?:terraform\s+destroy|tofu\s+destroy|pulumi\s+destroy|kubectl\s+delete|helm\s+uninstall)\b", re.I)
# Remocao recursiva no sh, no PowerShell (Remove-Item e os aliases ri/rm/del/rd aceitam -r, -Rec, -Recurse) e no cmd.
RM_RECURSIVE_RE = re.compile(
    r"(?<!git\s)\brm\s+(?:-[a-z]*r[a-z]*|--recursive)\b|"  # git rm -r e Git (tirar do indice), nao rm -r
    r"(?<!git\s)\b(?:Remove-Item|ri|rm|del|erase|rmdir|rd)\b[^;&|]*\s-r(?:e(?:c(?:u(?:r(?:s(?:e)?)?)?)?)?)?\b|"
    r"\b(?:rmdir|rd|del|erase)\s+(?:[^;&|]*\s)?/s\b", re.I)
CONTAINER_DESTRUCTIVE_RE = re.compile(
    r"\b(?:docker|podman)\s+(?:volume\s+(?:rm|prune)|system\s+prune|compose\s+down\s+[^;&|]*(?:-v\b|--volumes))", re.I)
# T1 (decisao do usuario, 2026-11-05): DROP, TRUNCATE, DELETE sem WHERE, ALTER ... DROP e rollback de migration
SQL_DESTRUCTIVE_RE = re.compile(
    r"\b(?:DROP\s+(?:TABLE|DATABASE|SCHEMA|INDEX|VIEW|COLUMN)|TRUNCATE\s+TABLE?|DELETE\s+FROM\s+\w+\s*(?:;|$|\"|')|"
    r"ALTER\s+TABLE\s+\S+\s+DROP\b|migrate\s+(?:down|rollback|reset)\b|db:rollback\b|downgrade\b|migrate\s+reset\b)", re.I)
# Codigo que o gateway nao consegue ler antes de rodar (ofuscado ou baixado): ninguem aprova o que nao viu.
OBFUSCATED_RE = re.compile(
    r"base64\s+(?:-d|--decode)|FromBase64String|\|\s*(?:ba|z|da)?sh\b|\|\s*(?:python3?|node|perl|ruby)\b|"
    r"(?:^|[;&|]\s*)eval\s|\bInvoke-Expression\b|\biex\b|\bsource\s+<\(", re.I)
# URL que leva um segredo para fora: parametro de credencial com valor longo, ou token com formato conhecido.
WEBFETCH_SECRET_RE = re.compile(
    r"[?&](?:token|access_token|api_?key|apikey|key|secret|password|passwd|auth|session|sig|signature)=[^&\s]{12,}|"
    r"\bgh[pousr]_[A-Za-z0-9]{30,}|\bAKIA[0-9A-Z]{16}\b|\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.", re.I)
# Instalar, atualizar, desativar ou remover skill, plugin ou servidor MCP muda o que o agente consegue fazer:
# o usuario decide cada um.
# Buscar (npx skills find, claude plugin list) segue livre.
TOOLING_INSTALL_RE = re.compile(
    r"\b(?:npx|bunx|pnpm\s+dlx|yarn\s+dlx)\s+(?:(?:-y|--yes)\s+)?skills(?:@\S+)?\s+(?:add|install|update|remove|rm)\b|"
    r"\bclaude\s+(?:plugins?\s+(?:install|i|enable|disable|update|uninstall|remove|marketplace\s+(?:add|remove|rm))|"
    r"mcp\s+(?:add(?:-json|-from-claude-desktop)?|remove))\b",
    re.I)
# Um agente abrir outra sessao do Claude Code sem permissoes (ex.: o modo live/Apply do Impeccable faz isso)
# escaparia do prompt nativo: negado. Ferramentas que fazem esse tipo de coisa por baixo pedem aprovacao.
BYPASS_SPAWN_RE = re.compile(r"\bclaude(?:\.exe)?\b[^;&|]*(?:--dangerously-skip-permissions|--permission-mode[= ]+bypassPermissions)", re.I)
DESIGN_LIVE_RE = re.compile(r"\bimpeccable\s+live\b", re.I)
CONFIG_PATH_RE = re.compile(
    r"(?:^|/)(?:\.github/workflows/|\.gitlab-ci\.yml$|Jenkinsfile$|azure-pipelines\.yml$|\.circleci/|"
    r"Dockerfile[^/]*$|docker-compose[^/]*\.ya?ml$|compose\.ya?ml$|[^/]+\.tf$|[^/]+\.tfvars$|helm/|charts/|k8s/|"
    r"kubernetes/|\.claude/settings[^/]*\.json$|\.claude/(?:skills|agents|commands)/|\.mcp\.json$)", re.I)
# Configuracao de qualidade (lint, formatacao, tipos): o agente conserta o codigo, nao afrouxa a regra (ideia do
# config-protection do ECC). Escrever nela exige config_ci_iac, que os executores nao tem no teto.
QUALITY_CONFIG_RE = re.compile(
    r"(?:^|/)(?:\.eslintrc[^/]*|eslint\.config\.[cm]?[jt]s|\.prettierrc[^/]*|prettier\.config\.[cm]?js|biome\.jsonc?|"
    r"tsconfig[^/]*\.json|jsconfig\.json|\.stylelintrc[^/]*|ruff\.toml|\.ruff\.toml|\.flake8|mypy\.ini|\.mypy\.ini|"
    r"\.pylintrc|pyrightconfig\.json|\.rubocop[^/]*\.ya?ml|\.golangci\.ya?ml|clippy\.toml|rustfmt\.toml|"
    r"\.swiftlint\.ya?ml|detekt[^/]*\.ya?ml|\.editorconfig|phpstan[^/]*\.neon(?:\.dist)?|psalm\.xml|\.clang-tidy|"
    r"\.clang-format|\.pre-commit-config\.ya?ml|\.husky/[^/]+|lefthook\.ya?ml|\.lintstagedrc[^/]*)$", re.I)
# Pular hooks ou assinatura do Git esconde problema (block-no-verify do ECC): sempre negado.
GIT_SKIP_HOOKS_RE = re.compile(r"\bgit\b[^;&|]*\s(?:--no-verify|--no-gpg-sign)\b|\bgit\b[^;&|]*\s-c\s+commit\.gpgsign=false\b", re.I)
AISEF_PROTECTED_RE = re.compile(r"(?:^|[/\s\"'=>])\.aisef/(?:approvals|authorizations|contracts/agents|session)/|(?:^|[/\s\"'=>])\.aisef/(?:config|policy\.local)\.json\b")
# Escrita por shell (redirecionamento ou comando que grava, move ou apaga) cujo alvo e um arquivo de decisao do AISEF.
SHELL_PROTECTED_WRITE_RE = re.compile(
    r"(?:>>?|\b(?:tee|Set-Content|Add-Content|Out-File|New-Item|ni|sc|ac|Copy-Item|cpi|copy|Move-Item|mi|move|"
    r"Rename-Item|rni|ren|Remove-Item|ri|cp|mv|rm|del|erase|truncate|touch|sed\s+-i|perl\s+-[a-z]*i)\b)"
    r"[^;&|]*?(?:^|[/\s\"'=>])\.aisef/(?:(?:approvals|authorizations|contracts/agents|session)/|(?:config|policy\.local)\.json\b)",
    re.I)
AISEF_AUDIT_RE = re.compile(r"(?:^|[/\s\"'=>])\.aisef/(?:audit|keys)/")
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
READ_TOOLS = {"Read", "Grep", "Glob"}
# Ferramentas que executam comandos: o Bash (Git Bash no Windows) e a ferramenta PowerShell do Claude Code no Windows.
SHELL_TOOLS = {"Bash", "PowerShell"}


class Decision(Exception):
    def __init__(self, level, reason):
        super().__init__(reason)
        self.level, self.reason = level, reason


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


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


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


def norm(path):
    return (path or "").replace("\\", "/")


# S-02 (0.13): a chave privada de assinatura e as ancoras do head ficam em ~/.aisef (ou AISEF_HOME), fora do repo.
# Nenhum agente le, copia ou escreve ali; os scripts do AISEF leem a chave por dentro, sem o caminho no comando.
HOME_SECRET_VAR_RE = re.compile(
    r"(?:~|\$\{?HOME\}?|\$env:(?:HOME|USERPROFILE)|%USERPROFILE%|%HOMEPATH%)[/\\]+\.aisef[/\\]+(?:keys|anchors)\b|"
    r"(?:\$\{?AISEF_HOME\}?|\$env:AISEF_HOME|%AISEF_HOME%)[/\\]+(?:keys|anchors)\b", re.I)


def _home_secret_dirs():
    base = os.environ.get("AISEF_HOME") or os.path.join(os.path.expanduser("~"), ".aisef")
    out = []
    for sub in ("keys", "anchors"):
        for p in {os.path.join(base, sub), os.path.realpath(os.path.join(base, sub))}:
            out.append(norm(p).rstrip("/").lower() + "/")
    return out


def home_secret_ref(text, cwd=None, is_path=False):
    """O texto (comando ou caminho) aponta para a chave privada ou as ancoras do AISEF?"""
    if not text:
        return False
    if HOME_SECRET_VAR_RE.search(text):
        return True
    dirs = _home_secret_dirs()
    low = norm(text).lower()
    if any(d in low + "/" for d in dirs):
        return True
    cands = [text] if is_path else [t.strip("\"'") for t in text.split() if "/" in t or "\\" in t]
    for c in cands[:20]:
        try:
            real = norm(os.path.realpath(os.path.join(cwd or os.getcwd(), os.path.expanduser(c)))).lower() + "/"
        except (OSError, ValueError):
            continue
        if any(real.startswith(d) for d in dirs):  # inclui link simbolico para dentro dessas pastas
            return True
    return False


def load_patterns(path=PATTERNS_PATH):
    raw = load_json(path)
    return {
        "cmd": [(re.compile(r["regex"], re.I), r["label"], r["category"]) for r in raw["commands"]],
        "path": re.compile(raw["paths"]["regex"], re.I),
        "safe": re.compile(raw["paths"]["allow"], re.I),
    }


def is_sensitive_path(path, patterns):
    return bool(patterns["path"].search(path) and not patterns["safe"].search(path))


def write_resource(path, patterns):
    """Recurso que uma ESCRITA no caminho exige (o mesmo criterio do gateway para Edit/Write):
    aisef_audit (sempre negado), aisef_decision, sensitive_files, config_ci_iac ou repo_code."""
    p = norm(path)
    if AISEF_AUDIT_RE.search(p):
        return "aisef_audit", "log de auditoria/chaves do AISEF"
    if AISEF_PROTECTED_RE.search(p):
        return "aisef_decision", "aprovacoes/autorizacoes/config do AISEF"
    if is_sensitive_path(p, patterns):
        return "sensitive_files", "arquivo sensivel"
    if CONFIG_PATH_RE.search(p):
        return "config_ci_iac", "config/CI/IaC"
    if QUALITY_CONFIG_RE.search(p):
        return "config_ci_iac", "configuracao de lint/formatacao/tipos (conserte o codigo, nao afrouxe a regra)"
    return "repo_code", "codigo"


def classify_bash(cmd, patterns, env, shell="sh"):
    """Retorna lista de (recurso, acao, ambiente, destrutivo, rotulo). Vazia = repo_code em dev.

    S-01 (0.13): alem da linha original, classifica os textos que o shell_parse tira dela (segmentos sem aspas,
    conteudo de bash -c, eval, $(...), crases, heredoc que alimenta um shell). O pior nivel vence, entao nada
    afrouxa. Comando que vem de variavel ou que nao fecha aspas vira pergunta."""
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import shell_parse
    an = shell_parse.analyze(cmd, shell)
    found = _classify_text(cmd, patterns, env)
    for text in an["texts"]:
        found += _classify_text(text, patterns, env)
    for why in an["dynamic"]:
        found.append(("unclassified", "execute", env, False, why + ": o gateway nao sabe o que vai rodar"))
    if an["unparsed"]:
        found.append(("unclassified", "execute", env, False, "aspas ou parenteses sem fechar: o gateway nao consegue ler o comando"))
    return list(dict.fromkeys(found))


def _classify_text(cmd, patterns, env):
    found = []
    for rx, label, category in patterns["cmd"]:
        if rx.search(cmd):
            if category == "secret":
                found.append(("sensitive_files", "read_content", env, False, label))
            else:
                # banco ou conexao: o ambiente alvo e desconhecido -> tratado como producao
                found.append(("db_data", "write", "unknown", bool(SQL_DESTRUCTIVE_RE.search(cmd)), label))
    # um comando que cita arquivo sensivel (cat .env, cp id_rsa ...) e leitura do conteudo dele
    if any(patterns["path"].search(tok) and not patterns["safe"].search(tok) for tok in cmd.split()):
        found.append(("sensitive_files", "read_content", env, False, "comando que cita arquivo sensivel"))
    for m in GIT_RE.finditer(cmd):
        sub, rest = m.group(1).lower(), m.group(2)
        if sub in ("status", "log", "diff", "show", "blame", "fetch", "remote", "rev-parse", "ls-files", "describe",
                   "shortlog", "grep", "check-ignore", "check-attr", "ls-tree", "rev-list", "for-each-ref", "cat-file",
                   "merge-base", "name-rev") or (sub in GIT_DRY_RUN_OK and GIT_DRY_RUN_RE.search(rest)) or (sub == "branch" and not re.search(r"\s-(?:d|D|-delete)\b", rest)):
            op = "status_log_diff"
        elif sub == "commit":
            op = "history_rewrite" if "--amend" in rest else "commit"
        elif sub == "push":
            if re.search(r"\s(?:-f|--force(?:-with-lease)?)\b|\s\+\S", rest):
                op = "force_push"
            elif re.search(r"\s(?:--delete|-d)\b|\s:\S", rest):
                op = "branch_delete"
            elif "--tags" in rest:
                op = "release_publish"
            else:
                op = "push"
        elif sub in ("merge", "pull", "cherry-pick"):
            op = "merge"
        elif sub in ("rebase", "filter-branch", "filter-repo", "replace") or (sub == "reset" and "--hard" in rest):
            op = "history_rewrite"
        elif sub == "branch":
            op = "branch_delete"
        elif sub == "tag":
            op = "release_publish"
        else:
            op = None  # subcomando nao classificado
        # T1: descartar trabalho local tambem e destrutivo (git clean, checkout/restore de arquivos, stash drop)
        discards = ((sub == "clean" and re.search(r"\s-[a-z]*f", rest) and not GIT_DRY_RUN_RE.search(rest)) or
                    (sub == "checkout" and re.search(r"\s(?:--\s|\.(?:\s|$))", rest + " ")) or
                    (sub == "restore" and "--staged" not in rest) or
                    (sub == "stash" and re.search(r"\s(?:drop|clear)\b", rest)))
        found.append(("git", op, env, op in ("force_push", "branch_delete") or bool(discards), "git " + sub))
    if re.search(r"\bgh\s+pr\s+create\b", cmd):
        found.append(("git", "pull_request", env, False, "abertura de pull request"))
    if re.search(r"\bgh\s+(?:release\s+create|pr\s+merge)\b|\bnpm\s+publish\b|\btwine\s+upload\b|\bcargo\s+publish\b", cmd):
        found.append(("git", "release_publish", env, False, "release/publicacao"))
    if DEPLOY_RE.search(cmd) or DEPLOY_DESTRUCTIVE_RE.search(cmd):
        found.append(("deploy_infra", "execute", "unknown", bool(DEPLOY_DESTRUCTIVE_RE.search(cmd)), "deploy/infra"))
    if RM_RECURSIVE_RE.search(cmd):
        found.append(("repo_code", "write", env, True, "remocao recursiva"))
    if CONTAINER_DESTRUCTIVE_RE.search(cmd):
        found.append(("repo_code", "write", env, True, "remocao de volumes/containers"))
    if OBFUSCATED_RE.search(cmd):
        found.append(("unclassified", "execute", env, False, "codigo ofuscado, baixado ou passado por pipe para um interpretador"))
    if TOOLING_INSTALL_RE.search(cmd):
        found.append(("unclassified", "execute", env, False, "instalacao de skill, plugin ou servidor MCP"))
    if (AISEF_AUDIT_RE.search(norm(cmd)) and not re.search(r"audit_chain\.py\s+verify|aisef_project\.py\s+(?:verify|status)", cmd)
            and not read_only_command(cmd)):  # ler o log (grep, cat, wc, jq...) e permitido; escrever nunca
        raise Decision("deny", "o log de auditoria e as chaves do AISEF so podem ser alterados pelo hook de auditoria")
    if BYPASS_SPAWN_RE.search(cmd):
        raise Decision("deny", "abrir outra sessao do Claude Code sem permissoes (bypass) escaparia do gateway e do prompt nativo")
    if DESIGN_LIVE_RE.search(cmd):
        found.append(("unclassified", "execute", env, False, "modo live do Impeccable (pode abrir o claude sem permissoes)"))
    if SHELL_PROTECTED_WRITE_RE.search(norm(cmd)):
        found.append(("aisef_decision", "write", env, False, "escrita por shell em arquivo de decisao do AISEF"))
    if re.search(r"aisef_project\.py\s+mode\b[^;&|]*--set\s+(?!ask\b)", cmd):
        # entrar no Ask so restringe (livre); sair dele devolve poder de execucao: decisao do usuario
        found.append(("aisef_decision", "write", env, False, "sair do modo Ask (decisao do usuario)"))
    if re.search(r"aisef_setup\.py\b[^;&|]*--apply\b", cmd):
        found.append(("aisef_decision", "write", env, False, "setup do AISEF: agentes, regras e docs (decisao do usuario)"))
    if re.search(r"aisef_practices\.py\s+apply\b|aisef_project\.py\s+practices\b[^;&|]*--apply\b", cmd):
        found.append(("aisef_decision", "write", env, False, "instalar boas praticas em .claude/rules (decisao do usuario)"))
    if re.search(r"aisef_migrate\.py\b[^;&|]*--apply\b", cmd):
        found.append(("aisef_decision", "write", env, False, "migrate do projeto AISEF (decisao do usuario)"))
    if re.search(r"aisef_learn\.py\s+accept\b", cmd):
        found.append(("aisef_decision", "write", env, False, "aprovacao de licao aprendida (decisao do usuario)"))
    if re.search(r"aisef_project\.py\s+(?:decide\b|append\b[^;&|]*--actor\s+user\b|agents\b[^;&|]*--activate\b|settings\b[^;&|]*--apply\b|rotate-key\b)", cmd):
        found.append(("aisef_decision", "write", env, False, "registro de decisao do usuario"))
    return found


def is_pending_request(tool, path, inp):
    """Propor um pedido ao Approval Center (Write de um pedido novo e pendente) nao e decidir."""
    if tool != "Write" or not re.search(r"(?:^|/)\.aisef/approvals/[^/]+\.json$", path) or os.path.exists(path):
        return False
    try:
        doc = json.loads(inp.get("content") or "")
    except ValueError:
        return False
    return isinstance(doc, dict) and doc.get("status") == "pending" and "decision" not in doc and "resulting_ref" not in doc


def scope_covers(project, resource, env, now, max_days=None):
    for path in glob.glob(os.path.join(project, ".aisef", "authorizations", "*.json")):
        try:
            a = load_json(path)
        except (OSError, ValueError):
            continue
        if a.get("kind") != "scope" or a.get("status") != "active" or a.get("environment") != env:
            continue
        if resource not in a.get("resources", []):
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
            if action not in ceiling.get("git_operations", ["status_log_diff"]):
                raise Decision("deny", "agente %s nao pode solicitar %s (teto Git: %s)"
                               % (aid, label, ", ".join(ceiling.get("git_operations", ["status_log_diff"]))))
        elif resource not in allowed:
            raise Decision("deny", "agente %s nao tem %s no teto de permissao (%s)" % (aid, resource, label))


READONLY_CMDS = {"ls", "dir", "cat", "type", "head", "tail", "wc", "grep", "rg", "find", "pwd", "echo", "tree", "less",
                 "more", "stat", "file", "which", "where", "get-content", "gc", "get-childitem", "gci", "select-string", "sls",
                 "get-location", "gl", "measure-object", "where-object", "select-object", "sort-object", "format-table",
                 "format-list", "get-item", "gi", "test-path", "sort", "uniq", "cut", "jq"}
GIT_DRY_RUN_OK = {"add", "rm", "clean", "mv"}  # com -n/--dry-run so mostram o que fariam
GIT_DRY_RUN_RE = re.compile(r"\s(?:-n|--dry-run)\b")
READONLY_GIT = {"status", "log", "diff", "show", "blame", "ls-files", "rev-parse", "describe", "shortlog", "grep", "remote",
                "check-ignore", "check-attr", "ls-tree", "rev-list", "for-each-ref", "cat-file", "merge-base", "name-rev"}
READONLY_AISEF_RE = re.compile(r"(?:aisef_project\.py\s+(?:next|status|verify|waves|precheck|mode)\b(?![^;&|]*--set)|"
                               r"check_project\.py|design_check\.py\s+(?:scan|validate)|aisef_context\.py\s+(?:pack|graph)|"
                               r"aisef_learn\.py\s+list|aisef_route\.py)")


def session_mode(project):
    try:
        with open(os.path.join(project, ".aisef", "session", "mode.json"), encoding="utf-8") as fh:
            return json.load(fh).get("mode", "exec")
    except (OSError, ValueError):
        return "exec"


def read_only_command(cmd):
    """Todo segmento do comando so le? (modo Ask). Redirecionamento para arquivo nunca e leitura."""
    if re.search(r"(?<![0-9&])>>?(?!\s*(?:/dev/null|\$null|nul)\b)", cmd):
        return False
    for seg in re.split(r"&&|\|\||[;&|\n]", cmd):
        toks = [t for t in seg.strip().split() if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t)]
        if not toks:
            continue
        head = os.path.basename(toks[0].strip("\"'")).lower()
        if head.endswith(".exe"):
            head = head[:-4]
        if head == "git":
            sub = next((t for i, t in enumerate(toks[1:], 1) if not t.startswith("-") and toks[i - 1] != "-C"), "")
            if sub not in READONLY_GIT and not (sub == "branch" and not re.search(r"\s-(?:d|D|m|M|-delete|-move)\b", seg)) \
                    and not (sub in GIT_DRY_RUN_OK and GIT_DRY_RUN_RE.search(seg)):
                return False
        elif head in ("python", "python3", "py"):
            if not READONLY_AISEF_RE.search(seg):
                return False
        elif head == "find":
            if re.search(r"\s-(?:delete|exec|execdir|ok)\b", seg):
                return False
        elif head not in READONLY_CMDS:
            return False
    return True


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
    if tool.startswith("mcp__") and not any(fnmatch.fnmatchcase(tool, pat) for pat in config.get("mcp_allow", [])):
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
        items = classify_bash(operation, patterns, env, "ps" if tool == "PowerShell" else "sh")
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
            elif tool in READ_TOOLS and is_sensitive_path(p, patterns):
                items.append(("sensitive_files", "read_content", env, False, "arquivo sensivel"))

    if tool.startswith("mcp__"):
        # Servidor MCP pode escrever arquivos, acessar banco ou fazer deploy sem passar pelo Bash:
        # so as ferramentas que o usuario liberou em config.json -> mcp_allow (globs) passam direto.
        if not any(fnmatch.fnmatchcase(tool, pat) for pat in config.get("mcp_allow", [])):
            items.append(("unclassified", "execute", env, False, "ferramenta MCP %s fora de mcp_allow" % tool))
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
                auth = scope_covers(project, resource, eff_env, now,
                                    policy.get("scope_authorization_schema_ref", {}).get("validity_max_days"))
                if auth:
                    scoped.append(auth)
                    lvl = "allow"
        if LEVELS.index(lvl) > LEVELS.index(worst):
            worst = lvl
        if lvl != "allow":
            why.append("%s (%s/%s) -> %s" % (label, resource, action or "nao classificado", lvl))

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


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        emit("deny", "AISEF: entrada do hook ilegivel (falha fechada)")
    project = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    config_path = os.path.join(project, ".aisef", "config.json")
    if not os.path.exists(config_path):
        sys.exit(0)  # projeto sem AISEF: o gateway nao interfere
    try:
        config = load_json(config_path)
        policy = load_json(POLICY_PATH)
        local = os.path.join(project, ".aisef", "policy.local.json")
        if os.path.exists(local):
            policy = merge_policy(policy, load_json(local))
        patterns = load_patterns()
        now = datetime.datetime.now(datetime.timezone.utc)
        decision, reason = decide(data, project, policy, patterns, config, now)
    except Decision as d:
        decision, reason = d.level, "AISEF: " + d.reason
    except Exception as exc:
        emit("deny", "AISEF: erro no Execution Gateway (%s); falha fechada" % exc)
    if decision:
        record_attempt(project, data, decision, reason)
        emit(decision, reason)
    if data.get("tool_name") in ("Grep", "Glob"):
        nudge(data, project)
    sys.exit(0)


def nudge(data, project):
    """Lembrete consultivo do grafo (graph_nudge) no mesmo processo: antes era um segundo Python por Grep/Glob."""
    try:
        sys.path.insert(0, CORE)
        sys.path.insert(1, HERE)
        import graph_nudge
        text = graph_nudge.nudge_context(data, project)
    except Exception:
        return
    if text:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": text}},
                         ensure_ascii=False))


if __name__ == "__main__":
    main()
