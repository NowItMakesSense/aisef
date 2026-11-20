#!/usr/bin/env python3
"""AISEF git (0.13, F-03, ADR 0025): branch atual e alvo de um push, sem subprocesso (o gateway roda a cada chamada).

Le o `.git/HEAD` direto: `ref: refs/heads/<branch>`. Em worktree, `.git` e um arquivo `gitdir: <caminho>` e o HEAD
fica la. HEAD solto, repositorio ausente ou qualquer erro devolvem None: quem chama trata como branch desconhecida e
cai na regra mais restritiva (falha fechada). Somente stdlib.
"""
import fnmatch
import os

PROTECTED = ("main", "master", "develop", "trunk", "release", "release/*", "hotfix/*", "production", "prod")


def _git_dir(start):
    d = os.path.abspath(start)
    while True:
        g = os.path.join(d, ".git")
        if os.path.isdir(g):
            return g
        if os.path.isfile(g):
            try:
                with open(g, encoding="utf-8") as fh:
                    line = fh.read().strip()
            except OSError:
                return None
            if line.startswith("gitdir:"):
                p = line.split(":", 1)[1].strip()
                return p if os.path.isabs(p) else os.path.normpath(os.path.join(d, p))
            return None
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def current_branch(path):
    """Nome da branch atual do repositorio que contem `path`, ou None (sem repo, HEAD solto, erro)."""
    try:
        g = _git_dir(path)
        if not g:
            return None
        with open(os.path.join(g, "HEAD"), encoding="utf-8") as fh:
            head = fh.read().strip()
    except OSError:
        return None
    if head.startswith("ref: refs/heads/"):
        return head[len("ref: refs/heads/"):] or None
    return None


def is_feature_branch(branch, prefix="feat/", base_branch="main"):
    """Branch de feature: comeca com o prefixo, tem nome depois dele e nao e protegida."""
    if not branch or not prefix or not branch.startswith(prefix) or len(branch) <= len(prefix):
        return False
    if branch == base_branch or any(fnmatch.fnmatchcase(branch, p) for p in PROTECTED):
        return False
    return True


def push_targets(args, current):
    """Branches de destino de `git push <args>` e se cada uma vem da branch de mesmo nome.
    args: lista de tokens depois de `push`. Devolve [(origem, destino)] ou None se nao der para saber."""
    opts_with_value = {"--repo", "--receive-pack", "--exec", "-o", "--push-option", "--recurse-submodules"}
    pos, skip = [], False
    for a in args:  # posicionais: remoto e refspecs (pula as opcoes e o valor das que levam argumento separado)
        if skip:
            skip = False
        elif a in opts_with_value:
            skip = True
        elif not a.startswith("-"):
            pos.append(a)
    refspecs = pos[1:]
    if not refspecs:
        return [(current, current)] if current else None

    def short(ref):
        return ref[len("refs/heads/"):] if ref and ref.startswith("refs/heads/") else ref

    out = []
    for r in refspecs:
        src, _, dst = r.lstrip("+").partition(":")
        src = current if src in ("HEAD", "@") else short(src)
        dst = short(dst) or src
        if not src or not dst:
            return None
        out.append((src, dst))
    return out


def main_worktree_root(path):
    """Raiz do repositorio principal quando `path` esta num worktree (L-02a). Le `.git` (arquivo `gitdir:`) e o
    `commondir` do worktree, sem subprocesso. Fora de worktree, ou em erro, devolve None."""
    d = os.path.abspath(path)
    while True:
        g = os.path.join(d, ".git")
        if os.path.isdir(g):
            return None  # repositorio principal (ou sem worktree): nada a redirecionar
        if os.path.isfile(g):
            try:
                with open(g, encoding="utf-8") as fh:
                    line = fh.read().strip()
                if not line.startswith("gitdir:"):
                    return None
                gitdir = line.split(":", 1)[1].strip()
                gitdir = gitdir if os.path.isabs(gitdir) else os.path.normpath(os.path.join(d, gitdir))
                with open(os.path.join(gitdir, "commondir"), encoding="utf-8") as fh:
                    common = fh.read().strip()
            except OSError:
                return None
            common = common if os.path.isabs(common) else os.path.normpath(os.path.join(gitdir, common))
            return os.path.dirname(os.path.normpath(common))
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def aisef_root(path):
    """Projeto AISEF efetivo: num worktree, o repositorio principal (se ele tem .aisef/config.json), para o log, as
    aprovacoes e o runtime nunca se dividirem entre copias. Senao, o proprio caminho."""
    try:
        main = main_worktree_root(path)
    except Exception:
        main = None
    if main and os.path.isfile(os.path.join(main, ".aisef", "config.json")):
        return main
    return path
