"""Dependencia nova no gateway (0.17, S-05).

Le um texto de comando e devolve os pacotes que ele adicionaria ao projeto, por ecossistema. Instalar o que ja esta
no lockfile ou no manifesto (`npm ci`, `npm install` sem nome, `pip install -r`, `pip install -e .`, `uv sync`,
`poetry install`, `cargo build`, `go mod download`) nao entra: nao traz pacote novo.

Pacote novo vira pergunta (`ask`): um nome inventado pelo modelo (slopsquatting) ou parecido com um conhecido
(typosquatting) roda codigo na instalacao. O motivo sugere `aisef_deps.py check`, que confere registro, idade e
avisos no OSV; com `dependency_check: "online"` no config.json o proprio gateway faz essa conferencia.
Sem rede por padrao: nada sai da maquina sem o usuario pedir.
"""
import re
import shlex

SEG_RE = re.compile(r"&&|\|\||[;&|\n]")
ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# opcoes que consomem o proximo argumento (o valor nao e pacote)
PIP_VALUE = {"-r", "--requirement", "-c", "--constraint", "-i", "--index-url", "--extra-index-url", "-t", "--target",
             "--prefix", "-f", "--find-links", "--root", "--python", "-p", "--src", "--upgrade-strategy", "--platform",
             "--python-version", "--implementation", "--abi", "--only-binary", "--no-binary", "--progress-bar",
             "--cache-dir", "--log", "--trusted-host", "--proxy", "--retries", "--timeout", "--group", "--index"}
NPM_VALUE = {"--prefix", "--registry", "--tag", "--workspace", "-w", "--filter", "--cache", "--userconfig", "-C", "--dir",
             "--cwd", "--omit", "--include"}
CARGO_VALUE = {"--features", "-F", "--package", "-p", "--manifest-path", "--rename", "--path", "--git", "--branch",
               "--tag", "--rev", "--registry", "--target"}
GEM_VALUE = {"-v", "--version", "-i", "--install-dir", "-n", "--bindir", "-s", "--source", "--platform"}
DOTNET_VALUE = {"-v", "--version", "-s", "--source", "-f", "--framework", "--package-directory"}
COMPOSER_VALUE = {"--working-dir", "-d"}
GO_VALUE = {"-C", "-modfile", "-tags"}
POETRY_VALUE = {"-G", "--group", "-E", "--extras", "--source", "--python", "--platform", "-C", "--directory"}


def _tokens(seg):
    try:
        toks = shlex.split(seg, posix=True)
    except ValueError:
        toks = seg.split()
    while toks and ENV_RE.match(toks[0]):
        toks = toks[1:]
    while toks and toks[0] in ("sudo", "env", "command", "exec", "time", "nohup"):
        toks = toks[1:]
    return toks


def _base(tok):
    name = tok.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def _positional(args, value_opts):
    """Argumentos que nao sao opcao (nem valor de opcao)."""
    out, skip = [], False
    for a in args:
        if skip:
            skip = False
            continue
        if a.startswith("-"):
            if "=" not in a and a in value_opts:
                skip = True
            continue
        out.append(a)
    return out


def _local(arg):
    """Caminho, URL ou arquivo local: nao e nome de pacote do registro."""
    return (arg.startswith((".", "/", "~", "file:", "git+", "http:", "https:", "link:", "workspace:")) or
            re.match(r"^[A-Za-z]:[\\/]", arg) is not None or
            arg.endswith((".whl", ".tar.gz", ".zip", ".tgz", ".gem", ".nupkg")) or
            (("/" in arg or "\\" in arg) and not arg.startswith("@")))


def _pip_name(arg):
    return re.split(r"[\[<>=!~;@ ]", arg, 1)[0]


def _npm_name(arg):
    if arg.startswith("@"):
        scope, _, rest = arg.partition("/")
        return scope + "/" + rest.split("@", 1)[0] if rest else arg
    return arg.split("@", 1)[0]


def _pip(args):
    if args[:1] != ["install"]:
        return []
    return [_pip_name(a) for a in _positional(args[1:], PIP_VALUE | {"-e", "--editable"}) if not _local(a)]


def _npm_like(args, verbs):
    if not args or args[0] not in verbs:
        return []
    return [_npm_name(a) for a in _positional(args[1:], NPM_VALUE) if not _local(a)]


def parse_segment(seg):
    """[(ecossistema, nome, texto original)] que um segmento simples de comando adicionaria."""
    toks = _tokens(seg.strip())
    if not toks:
        return []
    head, args = _base(toks[0]), toks[1:]
    if head in ("python", "python3", "py") and args[:2] == ["-m", "pip"]:
        head, args = "pip", args[2:]
    elif head in ("python", "python3", "py") and args[:1] and args[0].startswith("-3") and args[1:3] == ["-m", "pip"]:
        head, args = "pip", args[3:]
    found = []
    if head in ("pip", "pip3"):
        found = [("pypi", n) for n in _pip(args)]
    elif head == "uv":
        if args[:1] == ["pip"]:
            found = [("pypi", n) for n in _pip(args[1:])]
        elif args[:1] == ["add"]:
            found = [("pypi", _pip_name(a)) for a in _positional(args[1:], PIP_VALUE) if not _local(a)]
    elif head in ("poetry", "pdm") and args[:1] == ["add"]:
        found = [("pypi", _pip_name(a)) for a in _positional(args[1:], POETRY_VALUE) if not _local(a)]
    elif head == "npm":
        found = [("npm", n) for n in _npm_like(args, ("install", "i", "add", "in", "ins", "isntall"))]
    elif head == "pnpm":
        found = [("npm", n) for n in _npm_like(args, ("add",))]
    elif head == "yarn":
        found = [("npm", n) for n in _npm_like(args, ("add",))]
    elif head == "bun":
        found = [("npm", n) for n in _npm_like(args, ("add", "a"))]
    elif head == "cargo" and args[:1] == ["add"]:
        found = [("crates", a.split("@", 1)[0]) for a in _positional(args[1:], CARGO_VALUE) if not _local(a)]
    elif head == "go" and args[:1] == ["get"]:
        found = [("go", a.split("@", 1)[0]) for a in _positional(args[1:], GO_VALUE)
                 if not a.startswith((".", "/")) and a.split("@", 1)[0] not in ("all", "")]
    elif head == "dotnet" and "package" in args[:3] and args[:1] == ["add"]:
        i = args.index("package")
        found = [("nuget", a) for a in _positional(args[i + 1:], DOTNET_VALUE)[:1] if not _local(a)]
    elif head == "gem" and args[:1] == ["install"]:
        found = [("rubygems", a) for a in _positional(args[1:], GEM_VALUE) if not _local(a)]
    elif head == "composer" and args[:1] in (["require"], ["req"]):
        found = [("packagist", a.split(":", 1)[0]) for a in _positional(args[1:], COMPOSER_VALUE)
                 if "/" in a and not a.startswith((".", "/"))]
    return [(eco, name) for eco, name in found if name]


def new_dependencies(text):
    """Pacotes novos de todos os segmentos do texto, sem repetir, na ordem em que aparecem."""
    out = []
    for seg in SEG_RE.split(text):
        for item in parse_segment(seg):
            if item not in out:
                out.append(item)
    return out


_LABELS = {}  # rotulo -> pacotes, para a conferencia online achar o item depois da classificacao


def item(deps, env):
    """Item do gateway para a lista de pacotes novos (sempre pergunta: recurso nao classificado)."""
    text = label(deps)
    _LABELS[text] = deps
    return ("unclassified", "execute", env, False, text)


def enrich(items, check=None, max_packages=3, timeout=3):
    """dependency_check online: troca o rotulo pelo resultado do aisef_deps (registro, idade, OSV).
    Confere no maximo `max_packages` pacotes por comando para caber no tempo do hook."""
    if check is None:
        import aisef_deps
        check = lambda eco, name: aisef_deps.summary(aisef_deps.check(eco, name, timeout=timeout))  # noqa: E731
    out = []
    for it in items:
        deps = _LABELS.get(it[4])
        if deps:
            results = {d: check(*d) for d in deps[:max_packages]}
            it = it[:4] + (label(deps, results),)
        out.append(it)
    return out


def label(deps, results=None):
    """Motivo do ask. `results` (opcional) e {(eco, nome): texto} vindo da conferencia online."""
    results = results or {}
    parts = []
    for eco, name in deps:
        extra = results.get((eco, name))
        parts.append("%s:%s%s" % (eco, name, " [%s]" % extra if extra else ""))
    first = deps[0]
    hint = "" if results else "; confira antes com aisef_deps.py check %s %s" % first
    return "dependencia nova (%s): roda codigo do pacote na instalacao%s" % (", ".join(parts), hint)
