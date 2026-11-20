#!/usr/bin/env python3
"""AISEF env (0.13, C-02): acha um Python com as bibliotecas do AISEF (jsonschema e cryptography) e diz o que fazer.

Usado pelo doctor (SessionStart) e pelo init. So roda quando falta biblioteca, entao pode executar os interpretadores
candidatos (fora do caminho quente dos hooks). Candidatos, nesta ordem, sem repetir:
- python3, python e py em cada pasta do PATH (pulando o atalho da Microsoft Store, WindowsApps);
- no Windows, os Pythons que o `py -0p` lista.
Cada candidato roda `-I -c "import jsonschema, cryptography"` com tempo limite. Somente stdlib.
"""
import importlib.util
import os
import re
import subprocess
import sys

LIBS = ("jsonschema", "cryptography")
NAMES = ("python3", "python", "py")
TIMEOUT = 8
PY_LIST_RE = re.compile(r"^\s*-\S+\s+(?:\*\s+)?(.+?\.exe)\s*$", re.I)


def missing_libs():
    import userlibs  # noqa: F401  (enxerga a pasta de usuario do pip, como os hooks)
    return [m for m in LIBS if importlib.util.find_spec(m) is None]


def _norm(p):
    return os.path.normcase(os.path.realpath(p))


def path_candidates(path_env=None):
    """Executaveis python3/python/py do PATH, na ordem, sem o atalho da Microsoft Store."""
    exts = [""] + ([".exe"] if os.name == "nt" else [])
    out = []
    for d in (path_env if path_env is not None else os.environ.get("PATH", "")).split(os.pathsep):
        if not d or "WindowsApps" in d:
            continue
        for name in NAMES:
            for e in exts:
                p = os.path.join(d, name + e)
                if os.path.isfile(p):
                    out.append(p)
    return out


def launcher_candidates(run=subprocess.run):
    """Pythons listados pelo `py -0p` (so no Windows). Falha em silencio."""
    if os.name != "nt":
        return []
    try:
        r = run(["py", "-0p"], capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return []
    out = []
    for line in (r.stdout or "").splitlines():  # " -V:3.13 *        C:\...\python.exe" (o * marca o padrao)
        m = PY_LIST_RE.match(line)
        if m:
            out.append(m.group(1))
    return out


def has_libs(python, run=subprocess.run):
    """O interpretador importa as duas bibliotecas? Devolve o sys.executable dele ou None."""
    code = "import site,sys; sys.path.append(site.getusersitepackages()); import jsonschema, cryptography; print(sys.executable)"
    try:
        r = run([python, "-I", "-c", code], capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    out = (r.stdout or "").strip().splitlines()
    return out[-1] if r.returncode == 0 and out else None


def find_python(current=None, path_env=None, run=subprocess.run):
    """Primeiro Python (diferente do atual) que tem as bibliotecas, ou None."""
    current = _norm(current or sys.executable)
    seen = {current}
    for cand in path_candidates(path_env) + launcher_candidates(run):
        key = _norm(cand)
        if key in seen:
            continue
        seen.add(key)
        exe = has_libs(cand, run)
        if exe and _norm(exe) != current:
            return exe
    return None


def advice(missing, current=None, found=None):
    """Texto do que fazer, com o comando exato."""
    current = current or sys.executable
    msg = "faltam bibliotecas no Python dos hooks (%s): %s." % (current, ", ".join(missing))
    if found:
        return msg + (" Este Python tem tudo: %s. Defina AISEF_PYTHON com ele no settings.json do Claude Code "
                      "(\"env\": {\"AISEF_PYTHON\": \"%s\"}) e reinicie a sessao."
                      % (found, found.replace("\\", "\\\\")))
    return msg + " Nenhum outro Python do PATH tem as duas. Instale no dos hooks: `%s -m pip install %s`" % (
        current, " ".join(missing))


def diagnose(path_env=None, run=subprocess.run):
    """None se esta tudo certo; senao o texto do problema com a solucao."""
    missing = missing_libs()
    if not missing:
        return None
    return advice(missing, found=find_python(path_env=path_env, run=run))
