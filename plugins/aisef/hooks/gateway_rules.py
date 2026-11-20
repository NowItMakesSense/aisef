#!/usr/bin/env python3
"""AISEF gateway: padroes de operacao sensivel e classificacao de comandos e caminhos (o que cada chamada pede: recurso, acao, ambiente)

H-01 (0.14): saiu de gateway.py sem mudar o codigo; gateway reexporta tudo."""
import datetime
import fnmatch
import glob
import json
import os
import re
import sys
HERE = os.path.dirname(os.path.abspath(__file__))


PATTERNS_PATH = os.path.join(HERE, "sensitive_patterns.json")

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


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


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
        "mcp_code": re.compile((raw.get("mcp_code_execution") or {}).get("regex") or r"(?!)", re.I),
    }


def mcp_runs_code(tool, patterns):
    """A ferramenta MCP executa codigo ou comandos? (pelo nome curto, depois do ultimo __)."""
    return bool(patterns["mcp_code"].search(tool.rsplit("__", 1)[-1]))


def mcp_allowed(tool, config, patterns):
    """mcp_allow do config.json: nome exato sempre vale; glob nao cobre ferramenta que executa codigo (F-01)."""
    code = mcp_runs_code(tool, patterns)
    for pat in config.get("mcp_allow", []):
        if pat == tool or (not code and fnmatch.fnmatchcase(tool, pat)):
            return True
    return False


def mcp_trust(project, tool, now, patterns, max_days=7):
    """Confianca do usuario numa ferramenta MCP (authorizations/*.json, kind mcp_tool, F-01): ativa, no prazo
    (no maximo `max_days`), com glob que casa. Ferramenta que executa codigo so com allow_code_execution."""
    code = mcp_runs_code(tool, patterns)
    for path in glob.glob(os.path.join(project, ".aisef", "authorizations", "*.json")):
        try:
            a = load_json(path)
        except (OSError, ValueError):
            continue
        if a.get("kind") != "mcp_tool" or a.get("status") != "active":
            continue
        if code and a.get("allow_code_execution") is not True:
            continue
        if not any(fnmatch.fnmatchcase(tool, g) for g in a.get("tools", [])):
            continue
        try:
            start = datetime.datetime.fromisoformat(a["validity"]["valid_from"])
            end = datetime.datetime.fromisoformat(a["validity"]["valid_until"])
        except (KeyError, ValueError, TypeError):
            continue
        if (end - start).total_seconds() > max_days * 86400 + 1:
            continue
        if start <= now <= end:
            return a.get("authorization_id", os.path.basename(path))
    return None


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


def classify_bash(cmd, patterns, env, shell="sh", ctx=None):
    """Retorna lista de (recurso, acao, ambiente, destrutivo, rotulo). Vazia = repo_code em dev.

    S-01 (0.13): alem da linha original, classifica os textos que o shell_parse tira dela (segmentos sem aspas,
    conteudo de bash -c, eval, $(...), crases, heredoc que alimenta um shell). O pior nivel vence, entao nada
    afrouxa. Comando que vem de variavel ou que nao fecha aspas vira pergunta."""
    if HERE not in sys.path:
        sys.path.insert(0, HERE)
    import shell_parse
    an = shell_parse.analyze(cmd, shell)
    found = _classify_text(cmd, patterns, env, ctx)
    for text in an["texts"]:
        found += _classify_text(text, patterns, env, ctx)
    for why in an["dynamic"]:
        found.append(("unclassified", "execute", env, False, why + ": o gateway nao sabe o que vai rodar"))
    if an["unparsed"]:
        found.append(("unclassified", "execute", env, False, "aspas ou parenteses sem fechar: o gateway nao consegue ler o comando"))
    return list(dict.fromkeys(found))


SLICE_REF_RE = re.compile(r"(?<![\w/.-])((?:slice|feat)/[\w./-]+)")


def _slice_merge(ctx, rest):
    """L-02: 'integrate' = fatia (slice/*) mergeada na branch de feature atual; 'local' = branch de feature mergeada
    na fatia atual (dentro do worktree); None = outro merge (regra antiga)."""
    branch = ctx.get("branch") or ""
    refs = SLICE_REF_RE.findall(rest)
    if not refs or not branch:
        return None
    feat = ctx["aisef_git"].is_feature_branch
    if feat(branch, ctx["prefix"], ctx["base"]) and all(r.startswith("slice/") for r in refs):
        return "integrate"
    if branch.startswith("slice/") and all(feat(r, ctx["prefix"], ctx["base"]) for r in refs):
        return "local"
    return None


def _classify_text(cmd, patterns, env, ctx=None):
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
            if "--amend" in rest:
                op = "history_rewrite"
            elif ctx and ctx["feature"] and env in ("dev", "staging"):
                op = "commit_feature"  # F-03: commit na branch de feature e livre em dev e staging
            else:
                op = "commit"
        elif sub == "push":
            if re.search(r"\s(?:-f|--force(?:-with-lease)?)\b|\s\+\S", rest):
                op = "force_push"
            elif re.search(r"\s(?:--delete|-d)\b|\s:\S", rest):
                op = "branch_delete"
            elif "--tags" in rest or "--all" in rest or "--mirror" in rest:
                op = "release_publish"
            else:
                op = "push"
                targets = ctx["aisef_git"].push_targets(rest.split(), ctx["branch"]) if ctx else None
                if targets and all(s == d and ctx["aisef_git"].is_feature_branch(d, ctx["prefix"], ctx["base"])
                                   for s, d in targets):
                    # F-03: a branch de feature para ela mesma vai pelo escopo da feature (git_feature_branch)
                    ctx["push_targets"] += [d for _s, d in targets]
                    found.append(("git_feature_branch", "push", env, False,
                                  "git push da branch de feature %s" % ", ".join(d for _s, d in targets)))
                    continue
        elif (sub == "add" or sub == "switch" or (sub == "checkout" and re.search(r"\s-[bB]\s", rest + " "))):
            op = "local_staging"  # F-03: preparar o commit e trocar/criar branch local nao muda o remoto
        elif sub == "merge" and ctx and ("--abort" in rest or _slice_merge(ctx, rest) == "local"):
            op = "worktree_local"  # L-02: abortar merge ou trazer a feature para a fatia, no worktree
        elif sub == "merge" and ctx and _slice_merge(ctx, rest) == "integrate":
            # L-02: integrar a fatia na branch da feature e coberto pelo mesmo escopo do push (git_feature_branch)
            ctx["push_targets"].append(ctx["branch"])
            found.append(("git_feature_branch", "merge", env, False, "git merge da fatia em %s" % ctx["branch"]))
            continue
        elif sub in ("merge", "pull", "cherry-pick"):
            op = "merge"
        elif sub in ("rebase", "filter-branch", "filter-repo", "replace") or (sub == "reset" and "--hard" in rest):
            op = "history_rewrite"
        elif sub == "worktree" and env in ("dev", "staging"):
            op = "worktree_local"  # L-02: criar, listar e remover worktree local
        elif sub == "branch" and re.search(r"\s-d\b", rest) and not re.search(r"\s(?:-D|--force|-f)\b", rest) and \
                [n for n in rest.split() if not n.startswith("-")] and \
                all(n.startswith("slice/") for n in rest.split() if not n.startswith("-")):
            op = "worktree_local"  # L-02: apagar a branch da fatia ja integrada (-d so apaga o que foi mergeado)
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
    if re.search(r"aisef_mcp\.py\s+(?:trust|revoke)\b", cmd):
        found.append(("aisef_decision", "write", env, False, "confianca numa ferramenta MCP (decisao do usuario)"))
    if re.search(r"aisef_streams\.py\s+enable\b", cmd):
        found.append(("aisef_decision", "write", env, False, "ligar o log por pessoa (decisao do usuario)"))
    if re.search(r"aisef_migrate\.py\b[^;&|]*--apply\b", cmd):
        found.append(("aisef_decision", "write", env, False, "migrate do projeto AISEF (decisao do usuario)"))
    if re.search(r"aisef_learn\.py\s+accept\b", cmd):
        found.append(("aisef_decision", "write", env, False, "aprovacao de licao aprendida (decisao do usuario)"))
    if re.search(r"aisef_project\.py\s+(?:decide\b|append\b[^;&|]*--actor\s+user\b|agents\b[^;&|]*--activate\b|settings\b[^;&|]*--apply\b|rotate-key\b)", cmd):
        found.append(("aisef_decision", "write", env, False, "registro de decisao do usuario"))
    return found


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
