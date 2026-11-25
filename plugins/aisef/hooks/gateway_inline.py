"""S-07 (0.17, ADR 0033): contornos achados na reavaliacao de 2026-11-25 que o gateway deixava passar.

- literais concatenados que montam o caminho da chave (`'~/.ai' + 'sef/keys'`): `joined` devolve o texto com as
  partes juntas, para o `home_secret_ref` negar como nega o caminho escrito inteiro;
- codigo inline de interpretador (`python -c`, `node -e`, `perl -e`, heredoc ou pipe para o interpretador) citando
  `.aisef`: o gateway nao le codigo, entao pergunta (apagar o log ou ler a chave por dentro do codigo);
- substituicao de comando montando um caminho com `keys` ou `anchors` (`"$(echo ~/.ai)sef/keys/x"`);
- arquivar ou copiar a home inteira (leva `~/.aisef` junto);
- executar pacote baixado da rede na hora (`npx` sem o pacote no node_modules, `npx -y`, `pnpm dlx`, `yarn dlx`,
  `bunx`, `uvx`, `pipx run`).

Tudo vira pergunta (`ask`), nunca `allow`; so o caso dos literais vira negacao, pela regra que ja existia.
"""
import os
import re

JOIN_RE = re.compile(r"(['\"])\s*(?:\+|\.\s*concat\s*\(|,)?\s*(['\"])")
INTERP = r"(?:python[0-9.]*|py|node|nodejs|deno|bun|perl|ruby|php|pwsh|powershell)(?:\.exe)?"
INLINE_RE = re.compile(
    r"(?:^|[\s;&|(])" + INTERP + r"\b[^\n;&|]*?(?:\s-[A-Za-z]*[ceEr]\b|\s--eval\b|\s-Command\b|\s-\s*(?:<<|$)|<<-?\s*['\"]?\w)"
    r"|\|\s*" + INTERP + r"\b(?![^\n;&|]*\.(?:py|js|mjs|ts|pl|rb|php)\b)|\b" + INTERP + r"\s+-\s*<<", re.I | re.M)
AISEF_RE = re.compile(r"\.aisef\b|\.ai['\"]?\s*\+\s*['\"]?sef|['\"]aisef['\"]", re.I)
SUBST_PATH_RE = re.compile(r"(?:\$\([^)]*\)|`[^`]*`)[^\s;&|]*[/\\](?:keys|anchors)\b", re.I)
HOME_ARG = r"(?:~|~/|\$HOME/?|\$\{HOME\}/?|%USERPROFILE%\\?|\$env:USERPROFILE\\?|\$env:HOME/?)"
ARCHIVE_RE = re.compile(
    r"\b(?:tar|zip|7z|7za|rar|gzip|cpio|rsync|scp|cp|robocopy|xcopy|Compress-Archive|Copy-Item)\b[^\n;&|]*?"
    r"(?:\s|=|-Path\s+)['\"]?" + HOME_ARG + r"['\"]?(?=\s|$|[;&|])", re.I)
FETCH_RUN_RE = re.compile(r"\b(?:pnpm\s+dlx|yarn\s+dlx|bunx|uvx|pipx\s+run)\s+(?:-\S+\s+)*([@\w][\w@./:=-]*)", re.I)
NPX_RE = re.compile(r"\bnpx\s+((?:-\S+\s+)*)([@\w][\w@./:=-]*)", re.I)
# Ferramentas que o proprio plugin manda rodar (skills find, design_check com impeccable). Instalar skill continua
# perguntando pela TOOLING_INSTALL_RE do gateway_rules.
PLUGIN_NPX = {"skills", "impeccable"}


def joined(text):
    """O texto com literais vizinhos juntos ('a' + 'b', 'a' 'b', 'a'.concat('b')); igual ao original se nao ha."""
    return JOIN_RE.sub("", text or "")


def _npx_local(name, cwd):
    base = re.sub(r"@[^/@]+$", "", name) if not name.startswith("@") or name.count("@") > 1 else name
    bin_name = base.split("/")[-1]
    root = cwd or os.getcwd()
    for _ in range(6):  # node_modules do projeto ou de uma pasta acima (monorepo)
        if os.path.exists(os.path.join(root, "node_modules", ".bin", bin_name)) or \
                os.path.isdir(os.path.join(root, "node_modules", base)):
            return True
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    return False


def hints(cmd, cwd=None):
    """Motivos para perguntar (lista vazia se nada destes casos aparece)."""
    out = []
    if not cmd:
        return out
    if INLINE_RE.search(cmd) and (AISEF_RE.search(cmd) or AISEF_RE.search(joined(cmd))):
        out.append("codigo inline de interpretador citando .aisef: o gateway nao le codigo (pode apagar o log ou "
                   "ler a chave por dentro); use os scripts do AISEF")
    if any(re.search(r"~|HOME|USERPROFILE|\.ai|sef[/\\]", m.group(0), re.I) for m in SUBST_PATH_RE.finditer(cmd)):
        out.append("substituicao de comando montando caminho com keys/anchors: o gateway nao sabe onde vai dar")
    if ARCHIVE_RE.search(cmd):
        out.append("copia ou arquivo da home inteira: leva ~/.aisef (chave e ancoras) junto; diga as pastas")
    m = FETCH_RUN_RE.search(cmd)
    if m:
        out.append("executa o pacote %s baixado da rede na hora (sem lockfile nem conferencia)" % m.group(1))
    else:
        for flags, name in NPX_RE.findall(cmd):
            if name.split("@")[0] in PLUGIN_NPX and not re.search(r"(?:^|\s)(?:-p|--package)\b", flags):
                continue
            if re.search(r"(?:^|\s)(?:-y|--yes|-p|--package)\b", flags) or not _npx_local(name, cwd):
                out.append("npx %s: o pacote nao esta no node_modules do projeto, entao vem da rede na hora" % name)
                break
    return out
