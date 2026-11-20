#!/usr/bin/env python3
"""AISEF shell_parse (0.13, S-01): le um comando de shell por tokens antes dos regex do gateway. Somente stdlib.

O gateway classificava a linha inteira com regex. Aspas e aninhamento escondiam o comando:
    g"i"t push            bash -c "git push"        eval "rm -rf build"        x=$(git push)
`analyze()` devolve textos extras para o gateway classificar, alem da linha original (o pior nivel vence, entao
nada aqui afrouxa uma decisao):
- cada segmento (separado por ; && || | & e quebra de linha, respeitando aspas) sem aspas nem escapes;
- o conteudo de bash/sh/zsh/dash -c, pwsh/powershell -Command/-c, cmd /c, eval, $(...), crases (so no sh),
  <(...) e de prefixos como env, sudo, nohup, time, exec, command, xargs; ate MAX_DEPTH niveis.
E duas marcas que viram pergunta (nunca allow):
- `dynamic`: o nome do comando vem de variavel ou substituicao ($X args, $(cmd) args, & $x no PowerShell);
  as variaveis de interpretador conhecidas (AISEF_PYTHON, PYTHON...) contam como python;
- `unparsed`: aspas ou parenteses sem fechar.
"""
import re

MAX_DEPTH = 3
SEPARATORS = (";", "&&", "||", "|", "&", "\n")
WRAPPERS = {"env", "sudo", "nohup", "time", "exec", "command", "builtin", "nice", "xargs", "timeout", "stdbuf", "doas"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "fish"}
PWSH = {"pwsh", "powershell"}
KNOWN_PY_VARS = {"AISEF_PYTHON", "PYTHON", "PY", "PYTHON3"}
ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
VAR_HEAD_RE = re.compile(r"^\$\{?([A-Za-z_][A-Za-z0-9_:]*)\}?$")


def _scan(cmd, ps=False):
    """Divide em segmentos respeitando aspas e agrupamentos; coleta substituicoes $(...), `...` e <(...).
    Devolve (segmentos, substituicoes, ok)."""
    segs, subs, cur = [], [], []
    i, n, quote = 0, len(cmd), None
    ok = True
    esc = "`" if ps else "\\"
    while i < n:
        c = cmd[i]
        if quote:
            if c == esc and quote == '"' and i + 1 < n:
                cur.append(c + cmd[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
            elif quote == '"' and c == "$" and i + 1 < n and cmd[i + 1] == "(":
                j = _close(cmd, i + 1)
                if j < 0:
                    return segs, subs, False
                subs.append(cmd[i + 2:j])
                cur.append(cmd[i:j + 1])
                i = j + 1
                continue
            elif quote == '"' and c == "`" and not ps:
                j = cmd.find("`", i + 1)
                if j < 0:
                    return segs, subs, False
                subs.append(cmd[i + 1:j])
                cur.append(cmd[i:j + 1])
                i = j + 1
                continue
            cur.append(c)
            i += 1
            continue
        if c == esc and i + 1 < n:
            cur.append(c + cmd[i + 1])
            i += 2
            continue
        if c in ("'", '"'):
            quote = c
            cur.append(c)
            i += 1
            continue
        if c in ("$", "<", ">") and i + 1 < n and cmd[i + 1] == "(":
            j = _close(cmd, i + 1)
            if j < 0:
                return segs, subs, False
            subs.append(cmd[i + 2:j])
            cur.append(cmd[i:j + 1])
            i = j + 1
            continue
        if c == "`" and not ps:
            j = cmd.find("`", i + 1)
            if j < 0:
                return segs, subs, False
            subs.append(cmd[i + 1:j])
            cur.append(cmd[i:j + 1])
            i = j + 1
            continue
        if c == "(":
            j = _close(cmd, i)
            if j < 0:
                return segs, subs, False
            subs.append(cmd[i + 1:j])  # subshell ( ... ): o conteudo e outro comando
            cur.append(cmd[i:j + 1])
            i = j + 1
            continue
        two = cmd[i:i + 2]
        if two in ("&&", "||"):
            segs.append("".join(cur))
            cur = []
            i += 2
            continue
        if c in (";", "|", "\n") or (c == "&" and not ps and not (i > 0 and cmd[i - 1] in "<>") and not (i + 1 < n and cmd[i + 1] == ">")):
            segs.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    if quote:
        ok = False
    segs.append("".join(cur))
    return [s.strip() for s in segs if s.strip()], subs, ok


HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
PS_HERESTRING_RE = re.compile(r"@(['\"])\r?\n.*?\r?\n\1@", re.S)


def _strip_heredocs(cmd, ps=False):
    """Tira o corpo dos heredocs (dado, nao comando). Devolve (texto sem os corpos, [corpos que alimentam um shell])."""
    if ps:
        return PS_HERESTRING_RE.sub("@''@", cmd), []
    if "<<" not in cmd:
        return cmd, []
    lines, out, bodies, i = cmd.split("\n"), [], [], 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        tags = [m.group(2) for m in HEREDOC_RE.finditer(line) if "<<<" not in line[max(0, m.start() - 1):m.start() + 3]]
        i += 1
        for tag in tags:
            body = []
            while i < len(lines) and lines[i].strip() != tag:
                body.append(lines[i])
                i += 1
            if i < len(lines):
                out.append(lines[i])  # a linha do terminador
                i += 1
            first = _tokens(line.split("<<", 1)[0].strip().split("|")[-1])
            k = _head(first)
            base = first[k].rsplit("/", 1)[-1].lower() if k < len(first) else ""
            if base in SHELLS:
                bodies.append("\n".join(body))
    return "\n".join(out), bodies


def _close(cmd, open_idx):
    """Indice do ')' que fecha o '(' em open_idx, respeitando aspas. -1 se nao fecha."""
    depth, quote, i = 0, None, open_idx
    while i < len(cmd):
        c = cmd[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in ("'", '"'):
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _tokens(seg, ps=False):
    """Tokens do segmento sem aspas nem escapes (cada token e uma palavra do shell)."""
    out, cur, quote, i, has = [], [], None, 0, False
    esc = "`" if ps else "\\"
    while i < len(seg):
        c = seg[i]
        if quote:
            if c == quote:
                quote = None
            elif c == esc and quote == '"' and i + 1 < len(seg):
                cur.append(seg[i + 1])
                i += 1
            else:
                cur.append(c)
        elif c in ("'", '"'):
            quote, has = c, True
        elif c in ("$", "<", ">") and i + 1 < len(seg) and seg[i + 1] == "(" and _close(seg, i + 1) > 0:
            j = _close(seg, i + 1)  # $(...) e <(...) sao uma palavra so
            cur.append(seg[i:j + 1])
            has = True
            i = j
        elif c == esc and i + 1 < len(seg):
            cur.append(seg[i + 1])
            has = True
            i += 1
        elif c.isspace():
            if cur or has:
                out.append("".join(cur))
            cur, has = [], False
        else:
            cur.append(c)
            has = True
        i += 1
    if cur or has:
        out.append("".join(cur))
    return out


def _head(toks):
    """(indice do comando, lista) pulando atribuicoes VAR=x e prefixos (env, sudo, nohup...)."""
    i = 0
    while i < len(toks):
        t = toks[i]
        base = t.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
        if base.endswith(".exe"):
            base = base[:-4]
        if ASSIGN_RE.match(t):
            i += 1
        elif base in WRAPPERS:
            i += 1
            while i < len(toks) and (toks[i].startswith("-") or ASSIGN_RE.match(toks[i]) or
                                     (base in ("timeout", "nice") and re.match(r"^[\d.]+[smhd]?$", toks[i]))):
                i += 1
        else:
            return i
    return i


def _inner(toks, start, ps=False):
    """Comando passado como texto para outro interpretador (bash -c "...", pwsh -Command "...", eval ...)."""
    if start >= len(toks):
        return None
    base = toks[start].rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
    if base.endswith(".exe"):
        base = base[:-4]
    rest = toks[start + 1:]
    if base in SHELLS:
        for k, t in enumerate(rest):
            if re.match(r"^-[a-z]*c[a-z]*$", t) and k + 1 < len(rest):
                return rest[k + 1]
        return None
    if base in PWSH:
        for k, t in enumerate(rest):
            if t.lower() in ("-c", "-command", "-com") and k + 1 < len(rest):
                return " ".join(rest[k + 1:])
            if t.lower() in ("-encodedcommand", "-enc", "-e", "-ec"):
                return "\0encoded"
        return None
    if base == "cmd":
        for k, t in enumerate(rest):
            if t.lower() in ("/c", "/k") and k + 1 < len(rest):
                return " ".join(rest[k + 1:])
        return None
    if base in ("eval", "invoke-expression", "iex"):
        return " ".join(rest) if rest else None
    if base in INTERPRETERS:
        for k, t in enumerate(rest):
            if t in ("-c", "-e", "-r", "--eval", "-E") and k + 1 < len(rest):
                return "\0code:" + rest[k + 1]
    return None


INTERPRETERS = {"python", "python3", "py", "node", "deno", "bun", "perl", "ruby", "php"}
LITERAL_RE = re.compile(r"""(['"])((?:(?!\1).){1,400})\1""")


def code_strings(code):
    """Textos que um codigo inline (python -c, node -e...) passaria a um shell: cada string literal e todas juntas
    (subprocess.run(["git", "push"]) -> "git push"). Nao e analise do codigo: so da aos regex o que esta escrito."""
    lits = [m.group(2) for m in LITERAL_RE.finditer(code)]
    return [x for x in lits if " " in x] + ([" ".join(lits)] if len(lits) > 1 else [])


def analyze(cmd, shell="sh"):
    """{'texts': [textos extras para classificar], 'dynamic': [motivos], 'unparsed': bool}. Nunca levanta excecao."""
    ps = shell == "ps"
    out = {"texts": [], "dynamic": [], "unparsed": False}
    seen = set()

    def visit(text, depth):
        if depth > MAX_DEPTH or not text or text in seen:
            return
        seen.add(text)
        text, bodies = _strip_heredocs(text, ps)
        for body in bodies:  # heredoc que alimenta um shell: o conteudo e comando
            out["texts"].append(body)
            visit(body, depth + 1)
        segs, subs, ok = _scan(text, ps)
        if not ok:
            out["unparsed"] = True
        for sub in subs:
            out["texts"].append(sub)
            visit(sub, depth + 1)
        for seg in segs:
            toks = _tokens(seg, ps)
            if not toks:
                continue
            i = _head(toks)
            if i >= len(toks):
                continue
            if ps:
                # no PowerShell, `$x = ...` e `$x.Metodo()` sao expressoes; so `& alvo` e `. alvo` executam
                if toks[i] in ("&", ".") and i + 1 < len(toks):
                    i += 1
                else:
                    i = -1 if toks[i].startswith("$") else i
            if i < 0:
                continue
            head = toks[i]
            m = VAR_HEAD_RE.match(head)
            if m:
                if m.group(1).upper() in KNOWN_PY_VARS:
                    toks = toks[:i] + ["python"] + toks[i + 1:]
                else:
                    out["dynamic"].append("o comando vem da variavel %s" % head)
            elif head.startswith("$(") or head.startswith("`"):
                out["dynamic"].append("o comando vem de uma substituicao (%s)" % head[:30])
            flat = " ".join(toks[i:])
            if flat != seg:
                out["texts"].append(flat)
            inner = _inner(toks, i, ps)
            if inner == "\0encoded":
                out["dynamic"].append("comando do PowerShell codificado (-EncodedCommand)")
            elif inner and inner.startswith("\0code:"):
                out["texts"].extend(code_strings(inner[6:]))
            elif inner:
                out["texts"].append(inner)
                visit(inner, depth + 1)

    try:
        visit(cmd, 0)
    except Exception:
        out["unparsed"] = True
    out["texts"] = [t for t in dict.fromkeys(out["texts"]) if t and t != cmd]
    return out
