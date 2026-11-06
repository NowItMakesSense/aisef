#!/usr/bin/env python3
"""AISEF Execution Gateway: hook PreToolUse do Claude Code (v0.1).

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
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.join(os.path.dirname(HERE), "core")
POLICY_PATH = os.path.join(CORE, "permission-policy.v0.1.json")
PATTERNS_PATH = os.path.join(HERE, "db_patterns.json")
LEVELS = ["allow", "approve_scope", "approve_operation", "approve_reinforced", "deny"]

GIT_RE = re.compile(r"(?:^|[;&|(]\s*|\s)git(?:\s+-C\s+\S+)?\s+([a-z-]+)([^;&|]*)", re.I)
DEPLOY_RE = re.compile(
    r"\b(?:terraform\s+(?:apply|destroy)|tofu\s+apply|pulumi\s+up|kubectl\s+(?:apply|delete|rollout)|"
    r"helm\s+(?:install|upgrade|uninstall)|serverless\s+deploy|sls\s+deploy|fly\s+deploy|vercel\s+.*--prod|"
    r"netlify\s+deploy\s+.*--prod|gcloud\s+\S+\s+deploy|aws\s+cloudformation\s+deploy|cdk\s+deploy)\b", re.I)
RM_RECURSIVE_RE = re.compile(r"\brm\s+(?:-[a-z]*r[a-z]*|--recursive)\b|\bRemove-Item\b[^;&|]*-Recurse\b|\brmdir\s+/s\b", re.I)
SQL_DESTRUCTIVE_RE = re.compile(r"\b(?:DROP\s+(?:TABLE|DATABASE|SCHEMA|INDEX|VIEW)|TRUNCATE\s+TABLE?|DELETE\s+FROM\s+\w+\s*(?:;|$))", re.I)
CONFIG_PATH_RE = re.compile(
    r"(?:^|/)(?:\.github/workflows/|\.gitlab-ci\.yml$|Jenkinsfile$|azure-pipelines\.yml$|\.circleci/|"
    r"Dockerfile[^/]*$|docker-compose[^/]*\.ya?ml$|compose\.ya?ml$|[^/]+\.tf$|[^/]+\.tfvars$|helm/|charts/|k8s/|"
    r"kubernetes/|\.claude/settings[^/]*\.json$)", re.I)
AISEF_PROTECTED_RE = re.compile(r"(?:^|[/\s\"'=>])\.aisef/(?:approvals|authorizations)/|(?:^|[/\s\"'=>])\.aisef/(?:config|policy\.local)\.json")
AISEF_AUDIT_RE = re.compile(r"(?:^|[/\s\"'=>])\.aisef/(?:audit|keys)/")
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
READ_TOOLS = {"Read", "Grep", "Glob"}


class Decision(Exception):
    def __init__(self, level, reason):
        super().__init__(reason)
        self.level, self.reason = level, reason


def emit(decision, reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": decision,
        "permissionDecisionReason": reason}}, ensure_ascii=False))
    sys.exit(0)


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


def classify_bash(cmd, patterns, env):
    """Retorna lista de (recurso, acao, ambiente, destrutivo, rotulo). Vazia = repo_code em dev."""
    found = []
    for rx, label in patterns["cmd"]:
        if rx.search(cmd):
            if "secret" in label or "environment dump" in label:
                found.append(("sensitive_files", "read_content", env, False, label))
            else:
                # banco ou conexao: o ambiente alvo e desconhecido -> tratado como producao
                found.append(("db_data", "write", "unknown", bool(SQL_DESTRUCTIVE_RE.search(cmd)), label))
    for m in GIT_RE.finditer(cmd):
        sub, rest = m.group(1).lower(), m.group(2)
        if sub in ("status", "log", "diff", "show", "blame", "fetch", "remote", "rev-parse", "ls-files", "describe",
                   "shortlog", "grep") or (sub == "branch" and not re.search(r"\s-(?:d|D|-delete)\b", rest)):
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
        found.append(("git", op, env, op in ("force_push", "branch_delete"), "git " + sub))
    if re.search(r"\bgh\s+(?:release\s+create|pr\s+merge)\b|\bnpm\s+publish\b|\btwine\s+upload\b|\bcargo\s+publish\b", cmd):
        found.append(("git", "release_publish", env, False, "release/publicacao"))
    if DEPLOY_RE.search(cmd):
        found.append(("deploy_infra", "execute", "unknown", False, "deploy/infra"))
    if RM_RECURSIVE_RE.search(cmd):
        found.append(("repo_code", "write", env, True, "remocao recursiva"))
    if AISEF_AUDIT_RE.search(norm(cmd)) and not re.search(r"audit_chain\.py\s+verify|aisef_project\.py\s+(?:verify|status)", cmd):
        raise Decision("deny", "o log de auditoria e as chaves do AISEF so podem ser alterados pelo hook de auditoria")
    if re.search(r"aisef_project\.py\s+(?:decide\b|append\b[^;&|]*--actor\s+user\b)", cmd):
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


def scope_covers(project, resource, env, now):
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
        if start <= now <= end:
            return a.get("authorization_id", os.path.basename(path))
    return None


def reinforced_for(project, operation, now):
    for path in glob.glob(os.path.join(project, ".aisef", "authorizations", "*.json")):
        try:
            a = load_json(path)
        except (OSError, ValueError):
            continue
        if a.get("kind") != "reinforced" or a.get("status") != "approved" or a.get("consumed"):
            continue
        if (a.get("operation") or "").strip() != operation.strip():
            continue
        try:
            if now <= datetime.datetime.fromisoformat(a["expires_at"]):
                return a.get("approval_id", os.path.basename(path))
        except (KeyError, ValueError):
            continue
    return None


def decide(data, project, policy, patterns, config, now):
    tool = data.get("tool_name", "")
    inp = data.get("tool_input") or {}
    env = config.get("environment", "dev")
    if env not in ("dev", "staging", "prod"):
        env = "prod"  # defaults.unknown_environment

    items = []
    operation = ""
    if tool == "Bash":
        operation = inp.get("command", "") or ""
        items = classify_bash(operation, patterns, env)
    else:
        paths = [norm(inp.get(k)) for k in ("file_path", "path", "notebook_path", "pattern", "glob") if isinstance(inp.get(k), str)]
        operation = tool + " " + " ".join(paths)
        for p in paths:
            sensitive = patterns["path"].search(p) and not patterns["safe"].search(p)
            if tool in EDIT_TOOLS:
                if AISEF_AUDIT_RE.search(p):
                    raise Decision("deny", "o log de auditoria e as chaves do AISEF so podem ser alterados pelo hook de auditoria")
                if AISEF_PROTECTED_RE.search(p) and not is_pending_request(tool, p, inp):
                    items.append(("aisef_decision", "write", env, False, "aprovacoes/autorizacoes/config do AISEF"))
                elif sensitive:
                    items.append(("sensitive_files", "write", env, False, "arquivo sensivel"))
                elif CONFIG_PATH_RE.search(p):
                    items.append(("config_ci_iac", "write", env, False, "config/CI/IaC"))
            elif tool in READ_TOOLS and sensitive:
                items.append(("sensitive_files", "read_content", env, False, "arquivo sensivel"))

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
                auth = scope_covers(project, resource, eff_env, now)
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
    if worst in ("approve_scope", "approve_operation"):
        return "ask", reason + ". Aprove so se isso estiver dentro do que voce autorizou."
    if worst == "approve_reinforced":
        appr = reinforced_for(project, operation, now)
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
        raw = load_json(PATTERNS_PATH)
        patterns = {
            "cmd": [(re.compile(p["pattern"], re.I), p["label"]) for p in raw["cmd_patterns"]],
            "path": re.compile(raw["path_pattern"], re.I),
            "safe": re.compile(raw["safe_path"], re.I),
        }
        now = datetime.datetime.now(datetime.timezone.utc)
        decision, reason = decide(data, project, policy, patterns, config, now)
    except Decision as d:
        emit(d.level, "AISEF: " + d.reason)
    except Exception as exc:
        emit("deny", "AISEF: erro no Execution Gateway (%s); falha fechada" % exc)
    if decision:
        emit(decision, reason)
    sys.exit(0)


if __name__ == "__main__":
    main()
