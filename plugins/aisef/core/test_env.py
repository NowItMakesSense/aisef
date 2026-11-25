#!/usr/bin/env python3
"""Testes do aisef_env (C-02): achar um Python com jsonschema e cryptography, e o init que recusa sem assinatura (D5).
Os interpretadores sao simulados: arquivos vazios num PATH falso e um `run` injetado."""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_env as env  # noqa: E402
import aisef_project as ap  # noqa: E402

fails = total = 0
EXE = ".exe" if os.name == "nt" else ""


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)))
    fails += not cond


def fake(dirname, name):
    d = os.path.join(work, dirname)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name + EXE)
    open(p, "w").close()
    return p


class Run:
    """Simula os interpretadores: `good` sao os que importam as duas bibliotecas."""

    def __init__(self, good=(), launcher=""):
        self.good, self.launcher, self.calls = set(good), launcher, []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        if cmd[:2] == ["py", "-0p"]:
            return subprocess.CompletedProcess(cmd, 0, self.launcher, "")
        ok = cmd[0] in self.good
        return subprocess.CompletedProcess(cmd, 0 if ok else 1, (cmd[0] + "\n") if ok else "", "")


bad = fake("bin-a", "python3")
good = fake("bin-b", "python")
store = fake("WindowsApps", "python")
path = os.pathsep.join([os.path.dirname(store), os.path.dirname(bad), os.path.dirname(good)])

check("PATH: acha python3/python/py, pula o atalho da Microsoft Store",
      env.path_candidates(path) == [bad, good], env.path_candidates(path))
r = Run(good={good})
check("acha o primeiro Python que tem as duas bibliotecas", env.find_python("/nao/e/este", path, r) == good, r.calls)
check("nao executa o atalho da Store", all(store not in c for c in r.calls), r.calls)
check("nenhum tem: devolve None", env.find_python("/nao/e/este", path, Run()) is None)
check("o proprio Python dos hooks nao conta como solucao", env.find_python(good, path, Run(good={good})) is None)
if os.name == "nt":
    other = fake("py313", "python")
    lst = " -V:3.13 *        %s\n -V:3.12          C:\\x\\python.exe\n" % other
    check("Windows: py -0p entra como candidato", env.find_python("/nao/e/este", "", Run(good={other}, launcher=lst)) == other)

msg = env.advice(["cryptography"], current="/usr/bin/python3", found=good)
check("conselho com Python achado: AISEF_PYTHON no settings.json", "AISEF_PYTHON" in msg and good.replace("\\", "\\\\") in msg
      and "settings.json" in msg, msg)
msg = env.advice(["jsonschema", "cryptography"], current="/usr/bin/python3")
check("conselho sem Python achado: pip install exato no Python dos hooks",
      "`/usr/bin/python3 -m pip install jsonschema cryptography`" in msg, msg)
check("ambiente completo (este Python): diagnose devolve None", env.diagnose(path_env="", run=Run()) is None)

# sandbox do Claude Code (F-08)
import json  # noqa: E402
sbp = os.path.join(work, "sbp")
home = os.path.join(work, "sbhome")
os.makedirs(os.path.join(sbp, ".claude"))
os.makedirs(os.path.join(home, ".claude"))
check("sandbox: Windows nativo nao suporta e o doctor fica quieto",
      env.sandbox_status(sbp, "win32", home)["supported"] is False and env.sandbox_advice(sbp, {}, "win32", home) is None)
check("sandbox: Linux sem settings = desligado, doctor avisa com o caminho para ligar",
      "aisef_setup.py" in (env.sandbox_advice(sbp, {}, "linux", home) or ""))
json.dump({"sandbox": {"enabled": True}}, open(os.path.join(home, ".claude", "settings.json"), "w"))
check("sandbox: ligado no settings do usuario vale para o projeto", env.sandbox_status(sbp, "linux", home)["enabled"] is True
      and env.sandbox_advice(sbp, {}, "linux", home) is None)
json.dump({"sandbox": {"enabled": False}}, open(os.path.join(sbp, ".claude", "settings.local.json"), "w"))
check("sandbox: settings.local do projeto vence o do usuario", env.sandbox_status(sbp, "darwin", home)["enabled"] is False)
check("sandbox: sandbox_reminder false silencia o doctor", env.sandbox_advice(sbp, {"sandbox_reminder": False}, "linux", home) is None)

# S-04 (0.17): sandbox estrito nos perfis team e regulated
st = os.path.join(work, "strict")
sth = os.path.join(work, "stricthome")
os.makedirs(os.path.join(st, ".claude"))
os.makedirs(sth)
msg = env.sandbox_advice(st, {"profile": "team"}, "win32", sth) or ""
check("S-04: team no Windows nativo recomenda WSL2 ou devcontainer", "WSL2" in msg and "devcontainer" in msg, msg)
check("S-04: regulated no Windows nao cala com sandbox_reminder false",
      env.sandbox_advice(st, {"profile": "regulated", "sandbox_reminder": False}, "win32", sth) is not None)
check("S-04: team cala com sandbox_reminder false",
      env.sandbox_advice(st, {"profile": "team", "sandbox_reminder": False}, "win32", sth) is None)
json.dump({"sandbox": {"enabled": True}}, open(os.path.join(st, ".claude", "settings.json"), "w"))
msg = env.sandbox_advice(st, {"profile": "team"}, "linux", sth) or ""
check("S-04: team com o sandbox so ligado ainda pede o estrito",
      "allowUnsandboxedCommands" in msg and "~/.aisef" in msg, msg)
check("S-04: solo com o sandbox ligado fica quieto", env.sandbox_advice(st, {"profile": "solo"}, "linux", sth) is None)
merged = env.sandbox_merge({"sandbox": {"enabled": False, "filesystem": {"denyRead": ["~/.ssh"]}, "excludedCommands": ["x"]},
                            "permissions": {"deny": ["Read(.env)"]}}, "regulated")
check("S-04: merge fecha o sandbox e preserva o resto",
      merged["sandbox"]["enabled"] is True and merged["sandbox"]["allowUnsandboxedCommands"] is False and
      merged["sandbox"]["filesystem"]["denyRead"] == ["~/.ssh", "~/.aisef"] and merged["sandbox"]["excludedCommands"] == ["x"]
      and merged["permissions"] == {"deny": ["Read(.env)"]}, merged)
check("S-04: merge nao grava failIfUnavailable (travaria o Claude Code no Windows nativo)",
      "failIfUnavailable" not in merged["sandbox"])
json.dump(merged, open(os.path.join(st, ".claude", "settings.json"), "w"))
check("S-04: com o merge aplicado, team no Linux fica quieto", env.sandbox_advice(st, {"profile": "team"}, "linux", sth) is None)
json.dump({"sandbox": {"allowUnsandboxedCommands": True}}, open(os.path.join(st, ".claude", "settings.local.json"), "w"))
check("S-04: settings.local que reabre a saida volta a acusar",
      "allowUnsandboxedCommands" in (env.sandbox_advice(st, {"profile": "team"}, "linux", sth) or ""))
check("S-04: denyRead soma entre os arquivos de settings",
      "~/.aisef" in env.sandbox_effective(st, sth)["filesystem"]["denyRead"])

# init sem cryptography: recusa antes de criar qualquer coisa (D5)
proj = os.path.join(work, "proj")
os.makedirs(proj)
import aisef_base  # noqa: E402
aisef_base.HAS_CRYPTO = False
try:
    ap.init(proj, "PRJ-ENV")
    refused, text = False, ""
except SystemExit as e:
    refused, text = True, str(e)
aisef_base.HAS_CRYPTO = True
check("init sem cryptography recusa e diz como instalar", refused and "nada foi criado" in text and "cryptography" in text, text)
check("init recusado nao cria .aisef/", not os.path.exists(os.path.join(proj, ".aisef")))
check("init com cryptography segue assinado", ap.init(proj, "PRJ-ENV") is True)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
