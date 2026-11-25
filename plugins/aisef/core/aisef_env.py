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


# ------------------------------------------------------------------ sandbox do Claude Code (F-08)
SANDBOX_PLATFORMS = ("linux", "darwin")  # o sandbox nativo roda em Linux, macOS e WSL2; nao no Windows nativo


def _settings_files(project, home=None):
    home = home or os.path.expanduser("~")
    return [os.path.join(home, ".claude", "settings.json"), os.path.join(project, ".claude", "settings.json"),
            os.path.join(project, ".claude", "settings.local.json")]


def sandbox_status(project, platform=None, home=None):
    """{'supported', 'enabled', 'source'}: o ultimo settings que define sandbox.enabled vence (usuario < projeto < local)."""
    import json
    platform = platform or sys.platform
    st = {"supported": platform.startswith(SANDBOX_PLATFORMS), "enabled": False, "source": None}
    for path in _settings_files(project, home):
        try:
            with open(path, encoding="utf-8") as fh:
                sb = (json.load(fh) or {}).get("sandbox")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(sb, dict) and isinstance(sb.get("enabled"), bool):
            st["enabled"], st["source"] = sb["enabled"], path
    return st


STRICT_PROFILES = ("team", "regulated")
# S-04 (0.17): o que os perfis team e regulated exigem do sandbox nativo. allowUnsandboxedCommands=false fecha a saida
# por dangerouslyDisableSandbox; denyRead tira a chave e as ancoras do AISEF do alcance de qualquer comando.
# failIfUnavailable fica de fora de proposito: no settings do projeto ele impediria o Claude Code de abrir no Windows nativo.
SANDBOX_STRICT = {"enabled": True, "allowUnsandboxedCommands": False, "filesystem": {"denyRead": ["~/.aisef"]}}


def sandbox_effective(project, home=None):
    """O bloco sandbox somado dos settings (usuario < projeto < local; o ultimo valor de cada chave vence)."""
    import json
    eff = {}
    for path in _settings_files(project, home):
        try:
            with open(path, encoding="utf-8") as fh:
                sb = (json.load(fh) or {}).get("sandbox")
        except (OSError, ValueError, AttributeError):
            continue
        if not isinstance(sb, dict):
            continue
        for k, v in sb.items():
            if k == "filesystem" and isinstance(v, dict):
                fs = eff.setdefault("filesystem", {})
                for fk, fv in v.items():
                    fs[fk] = list(dict.fromkeys((fs.get(fk) or []) + list(fv))) if isinstance(fv, list) else fv
            else:
                eff[k] = v
    return eff


def sandbox_missing(profile, effective):
    """O que falta para o perfil, em texto (vazio = atende). Solo so pede enabled."""
    out = []
    if effective.get("enabled") is not True:
        out.append("sandbox.enabled = true")
    if profile in STRICT_PROFILES:
        if effective.get("allowUnsandboxedCommands") is not False:
            out.append("sandbox.allowUnsandboxedCommands = false (sem saida por dangerouslyDisableSandbox)")
        if "~/.aisef" not in ((effective.get("filesystem") or {}).get("denyRead") or []):
            out.append("sandbox.filesystem.denyRead inclui ~/.aisef (chave e ancoras do AISEF)")
    return out


def sandbox_merge(current, profile):
    """Settings com o sandbox que o perfil pede, sem afrouxar nada que ja esteja mais fechado."""
    cur = dict(current or {})
    sb = dict(cur.get("sandbox") or {})
    sb["enabled"] = True
    if profile in STRICT_PROFILES:
        sb["allowUnsandboxedCommands"] = False
        fs = dict(sb.get("filesystem") or {})
        fs["denyRead"] = list(dict.fromkeys(list(fs.get("denyRead") or []) + ["~/.aisef"]))
        sb["filesystem"] = fs
    cur["sandbox"] = sb
    return cur


def sandbox_advice(project, cfg=None, platform=None, home=None):
    """Aviso do doctor, ou None. Perfil solo: silencioso no Windows nativo, com o sandbox ligado ou com
    config.json -> "sandbox_reminder": false (o usuario recusou). Perfis team e regulated (S-04): avisa enquanto o
    sandbox nao estiver estrito e, no Windows nativo, recomenda WSL2 ou devcontainer; no regulated o aviso nao cala."""
    cfg = cfg or {}
    profile = cfg.get("profile")
    if profile in STRICT_PROFILES and not (profile == "team" and cfg.get("sandbox_reminder") is False):
        supported = (platform or sys.platform).startswith(SANDBOX_PLATFORMS)
        if not supported:
            return ("perfil %s sem isolamento: no Windows nativo o Claude Code roda os comandos sem sandbox, e o gateway "
                    "(um hook no seu usuario) fica como unica camada. Rode o Claude Code no WSL2 ou num devcontainer "
                    "para o sandbox valer" % profile)
        missing = sandbox_missing(profile, sandbox_effective(project, home))
        if missing:
            return ("perfil %s pede o sandbox estrito; falta: %s. Aplique com `aisef_setup.py --apply --only sandbox`"
                    % (profile, "; ".join(missing)))
        return None
    if cfg.get("sandbox_reminder") is False:
        return None
    st = sandbox_status(project, platform, home)
    if not st["supported"] or st["enabled"]:
        return None
    return ("sandbox do Claude Code desligado: o gateway decide o que pode rodar, mas le comandos por padroes e nao "
            "isola. Ligue com /sandbox ou pelo setup (`aisef_setup.py --apply --only sandbox`); para nao ver mais "
            "este aviso, grave \"sandbox_reminder\": false no .aisef/config.json")
