#!/usr/bin/env python3
"""Dependencia nova (0.17, S-05): leitor de comandos, conferidor de registro/idade/OSV e modo online do gateway.

Nada aqui usa a rede: o registro e o OSV sao respostas falsas injetadas."""
import datetime
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.join(os.path.dirname(HERE), "core")
sys.path[:0] = [HERE, CORE]
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_deps  # noqa: E402
import aisef_project  # noqa: E402
import gateway  # noqa: E402
import gateway_deps  # noqa: E402

fails = total = 0
NOW = datetime.datetime(2026, 11, 25, tzinfo=datetime.timezone.utc)


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)))
    fails += not cond


# 1. leitor: o que traz pacote novo e o que so instala o que ja esta declarado
cases = {
    "pip install requests==2.0 flask[async]": [("pypi", "requests"), ("pypi", "flask")],
    "python -m pip install -U pip": [("pypi", "pip")],
    "npm i -D @types/node@20 lodash": [("npm", "@types/node"), ("npm", "lodash")],
    "cargo add serde@1 --features derive": [("crates", "serde")],
    "go get github.com/foo/bar@v1.2.0": [("go", "github.com/foo/bar")],
    "dotnet add src/a.csproj package Serilog --version 3": [("nuget", "Serilog")],
    "composer require monolog/monolog:^3": [("packagist", "monolog/monolog")],
    "gem install rails -v 7": [("rubygems", "rails")],
    "git status && sudo npm install -g left-pad": [("npm", "left-pad")],
    "pip install -r req.txt": [], "pip install -e .": [], "npm install": [], "npm ci": [], "uv sync": [],
    "npm install ./local-pkg": [], "pip install dist/pkg-1.0.whl": [], "go get -u ./...": [],
    "pip install --index-url https://x/simple -r req.txt": [], "yarn": [], "pnpm install": [],
}
for cmd, want in cases.items():
    got = gateway_deps.new_dependencies(cmd)
    check("leitor: %s" % cmd, got == want, got)

# 2. conferidor com registro e OSV falsos


def fake(registry, osv=None, fail=False):
    def fetch(url, data=None, timeout=5):
        if fail:
            raise OSError("sem rede")
        if url == aisef_deps.OSV_URL:
            return 200, json.dumps({"vulns": [{"id": v} for v in osv or []]})
        return registry
    return fetch


r = aisef_deps.check("npm", "reqeusts", fetch=fake((404, "")), now=NOW)
check("pacote inexistente: possivel pacote inventado",
      r["exists"] is False and aisef_deps.summary(r) == "nao existe no registro (possivel pacote inventado)", r)
old = (200, json.dumps({"time": {"created": "2012-01-01T00:00:00Z"}}))
r = aisef_deps.check("npm", "lodash", fetch=fake(old), now=NOW)
check("pacote antigo e sem aviso: sem problema", r["exists"] and r["age_days"] > 5000 and not r["problems"]
      and "sem aviso no OSV" in aisef_deps.summary(r), r)
young = (200, json.dumps({"releases": {"0.1": [{"upload_time_iso_8601": "2026-11-20T10:00:00Z"}]}}))
r = aisef_deps.check("pypi", "colourama", fetch=fake(young), now=NOW)
check("pacote de 5 dias: aparece como novo demais", r["age_days"] == 4 and "publicado ha 4 dias" in aisef_deps.summary(r), r)
r = aisef_deps.check("npm", "evil", fetch=fake(old, ["MAL-2025-1"]), now=NOW)
check("pacote malicioso no OSV", "malicioso" in aisef_deps.summary(r), r)
r = aisef_deps.check("crates", "serde", fetch=fake((200, json.dumps({"crate": {"created_at": "2015-01-01T00:00:00Z"}})),
                                                   ["RUSTSEC-1"]), now=NOW)
check("aviso de vulnerabilidade no OSV", "1 aviso(s) no OSV" in aisef_deps.summary(r), r)
r = aisef_deps.check("npm", "x", fetch=fake(None, fail=True), now=NOW)
check("sem rede: nao conferido, sem inventar resultado", r["exists"] is None and "nao conferido" in aisef_deps.summary(r), r)
check("URL do npm com escopo", aisef_deps.registry_url("npm", "@types/node").endswith("/@types%2Fnode"))
check("URL do proxy Go escapa maiuscula", "/github.com/!azure/x/@v/list" in aisef_deps.registry_url("go", "github.com/Azure/x"))

# 3. gateway: pergunta sem rede por padrao; com dependency_check online, o resultado entra no motivo
proj = os.path.join(work, "proj")
os.makedirs(proj)
aisef_project.init(proj, "PRJ-DEPS")
policy, patterns = gateway.load_json(gateway.POLICY_PATH), gateway.load_patterns()
config = gateway.load_json(os.path.join(proj, ".aisef", "config.json"))


def decide(cmd, cfg):
    data = {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": proj}
    d, reason = gateway.decide(data, proj, policy, patterns, cfg, NOW)
    return d or "allow", reason or ""


d, why = decide("npm install reqeusts", config)
check("sem rede: ask com a sugestao do aisef_deps", d == "ask" and "aisef_deps.py check npm reqeusts" in why, why)
calls = []
original = aisef_deps.check
aisef_deps.check = lambda eco, name, timeout=5, **k: (calls.append(name) or original(eco, name, fetch=fake((404, "")), now=NOW))
try:
    d, why = decide("npm install reqeusts", dict(config, dependency_check="online"))
    check("online: inexistente aparece no motivo do ask",
          d == "ask" and "npm:reqeusts [nao existe no registro (possivel pacote inventado)]" in why, why)
    calls.clear()
    decide("npm i a b c d e", dict(config, dependency_check="online"))
    check("online: confere no maximo 3 pacotes por comando", calls == ["a", "b", "c"], calls)
    calls.clear()
    d, _ = decide("npm ci", dict(config, dependency_check="online"))
    check("online: lockfile nao consulta a rede", d == "allow" and calls == [], calls)
finally:
    aisef_deps.check = original
data = {"tool_name": "Bash", "tool_input": {"command": "pip install x"}, "cwd": proj, "permission_mode": "bypassPermissions"}
check("bypassPermissions: dependencia nova e negada", gateway.decide(data, proj, policy, patterns, config, NOW)[0] == "deny")

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
