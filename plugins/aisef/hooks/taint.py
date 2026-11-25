#!/usr/bin/env python3
"""Conteudo nao confiavel marca a sessao (0.17, S-06, ADR 0029).

Pagina da web, resultado de busca e resposta de MCP sem confianca do usuario podem trazer instrucoes escondidas
(prompt injection). Sozinho isso nao vaza nada; o perigo e a "lethal trifecta": dado privado + conteudo nao
confiavel + canal de saida. Este hook (PostToolUse sincrono de WebFetch, WebSearch e mcp__*) grava uma marca com
prazo em .aisef/runtime/untrusted/<sessao>.json; enquanto ela vale, o gateway sobe um nivel a saida de dados e a
escrita em config/CI e passa a perguntar antes de comando de rede.

A marca vence sozinha (`untrusted_ttl_minutes` no config.json, padrao 60). Ler de novo renova o prazo.
"""
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TTL_MINUTES = 60
UNTRUSTED_TOOLS = ("WebFetch", "WebSearch")
# comando que fala com a rede (alem do que o gateway ja trata como saida de dados com arquivo)
NET_CMDS = {"curl", "wget", "nc", "ncat", "netcat", "telnet", "ftp", "sftp", "scp", "rsync", "ssh", "socat",
            "invoke-webrequest", "invoke-restmethod", "iwr", "irm", "send-mailmessage", "sendmail"}
LEVELS = ["allow", "approve_scope", "approve_operation", "approve_reinforced", "deny"]


def _dir(project):
    return os.path.join(project, ".aisef", "runtime", "untrusted")


def _key(session):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", session or "sem-sessao")[:80]


def _ttl(config):
    try:
        return max(1, int((config or {}).get("untrusted_ttl_minutes") or TTL_MINUTES))
    except (TypeError, ValueError):
        return TTL_MINUTES


def is_untrusted(tool, trusted_mcp):
    """WebFetch e WebSearch sempre; MCP so quando o usuario nao confia na ferramenta (`trusted_mcp(tool)`)."""
    if tool in UNTRUSTED_TOOLS:
        return True
    return tool.startswith("mcp__") and not trusted_mcp(tool)


def mark(project, session, tool, now, config=None, detail=""):
    """Grava (ou renova) a marca da sessao. Devolve o caminho."""
    os.makedirs(_dir(project), exist_ok=True)
    until = now + datetime.timedelta(minutes=_ttl(config))
    path = os.path.join(_dir(project), _key(session) + ".json")
    doc = {"session_id": session, "source": tool, "detail": detail[:200], "marked_at": now.isoformat(),
           "until": until.isoformat()}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    os.replace(tmp, path)
    return path


def active(project, session, now):
    """A marca da sessao, se ainda vale; None quando nao ha marca ou ela venceu."""
    path = os.path.join(_dir(project), _key(session) + ".json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        until = datetime.datetime.fromisoformat(doc["until"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        # o que nao da para ler conta como marca (falha fechada), sem prazo conhecido
        return {"source": "marca ilegivel", "until": (now + datetime.timedelta(minutes=1)).isoformat()}
    return doc if until > now else None


def network_command(cmd, shell="sh"):
    """Algum segmento (inclusive dentro de bash -c, eval, $(...)) comeca com um comando de rede?"""
    import gateway_deps
    import shell_parse
    for text in [cmd] + list(shell_parse.analyze(cmd, shell)["texts"]):
        for seg in gateway_deps.SEG_RE.split(text):
            toks = gateway_deps._tokens(seg.strip())
            if toks and gateway_deps._base(toks[0]) in NET_CMDS:
                return True
    return False


def harden(items, operation, taint, env, is_shell):
    """Com a marca: comando de rede sem item de saida de dados vira pergunta (item novo)."""
    if not taint or not is_shell or not network_command(operation or ""):
        return items
    if any("saida de dados" in it[4] for it in items):
        return items
    return items + [("unclassified", "execute", env, False, "comando de rede depois de conteudo nao confiavel (%s)"
                     % taint.get("source", "?"))]


def raise_level(lvl, resource, action, label, taint):
    """Com a marca: saida de dados e escrita em config/CI sobem um nivel (nunca alem de approve_reinforced)."""
    if not taint or lvl in ("allow", "deny"):
        return lvl
    if "saida de dados" in label or (resource == "config_ci_iac" and action == "write"):
        return LEVELS[min(LEVELS.index(lvl) + 1, LEVELS.index("approve_reinforced"))]
    return lvl


def note(taint, now):
    """Trecho do motivo: de onde veio a marca e quando vence."""
    try:
        mins = int((datetime.datetime.fromisoformat(taint["until"]) - now).total_seconds() // 60) + 1
    except (KeyError, ValueError, TypeError):
        mins = 0
    return ("a sessao leu conteudo nao confiavel (%s); saida de dados e config/CI ficam mais restritas por mais "
            "%d min" % (taint.get("source", "?"), mins))


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    tool = data.get("tool_name", "")
    if tool not in UNTRUSTED_TOOLS and not tool.startswith("mcp__"):
        return
    sys.path.insert(0, HERE)
    import gateway
    project = gateway._aisef_root(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd())
    cfg_path = os.path.join(project, ".aisef", "config.json")
    if not os.path.exists(cfg_path):
        return
    try:
        config = gateway.load_json(cfg_path)
        now = datetime.datetime.now(datetime.timezone.utc)
        patterns = gateway.load_patterns()
        trusted = lambda t: gateway.mcp_allowed(t, config, patterns) or bool(gateway.mcp_trust(project, t, now, patterns))  # noqa: E731
        if is_untrusted(tool, trusted):
            inp = data.get("tool_input") or {}
            mark(project, data.get("session_id"), tool, now, config, str(inp.get("url") or inp.get("query") or ""))
    except Exception as exc:  # nunca bloqueia a sessao
        sys.stderr.write("AISEF: marca de conteudo nao confiavel NAO gravada (%s)\n" % exc)


if __name__ == "__main__":
    main()
