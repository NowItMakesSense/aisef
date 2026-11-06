#!/usr/bin/env python3
"""Roda todas as suites do AISEF e resume. Uso: python run_tests.py   (precisa de jsonschema e cryptography)

As suites sao scripts autonomos (como foram escritas e validadas na conversa de origem), nao pytest.
A do painel renderiza em Chrome headless quando o Chrome existe; sem ele, essa parte e pulada.
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.join(ROOT, "plugins", "aisef", "core")
HOOKS = os.path.join(ROOT, "plugins", "aisef", "hooks")
work = tempfile.mkdtemp()
env = dict(os.environ, PYTHONIOENCODING="utf-8", TMPDIR=work)

SUITES = [
    ("approval-request schema", [os.path.join(CORE, "test_approval_request.py"), os.path.join(CORE, "approval-request.schema.v0.1.json")]),
    ("engineering blueprint schema", [os.path.join(CORE, "test_blueprint.py")]),
    ("check_project (mutacoes)", [os.path.join(CORE, "test_check_project.py")]),
    ("cadeia de hash", [os.path.join(CORE, "audit_chain.py"), "selftest", os.path.join(CORE, "audit-event.schema.v0.1.json")]),
    ("assinatura Ed25519", [os.path.join(CORE, "audit_signing.py"), "selftest", os.path.join(CORE, "audit-event.schema.v0.1.json")]),
    ("politica x schemas", [os.path.join(CORE, "check_policy_consistency.py"), os.path.join(CORE, "permission-policy.v0.1.json"),
                            os.path.join(CORE, "authorization.schema.v0.1.json"), os.path.join(CORE, "approval-request.schema.v0.1.json")]),
    ("painel", [os.path.join(CORE, "test_panel.py"), os.path.join(work, "panel")]),
    ("gateway + auditoria + Approval Center", [os.path.join(HOOKS, "test_gateway.py")]),
    ("geradores (briefs e caminho rapido)", [os.path.join(CORE, "test_generators.py")]),
    ("ciclo de vida do log", [os.path.join(CORE, "test_audit_lifecycle.py")]),
    ("agentes gerados da fonte unica", [os.path.join(ROOT, "tools", "gen_agents.py"), "--check"]),
]

failed = []
for name, args in SUITES:
    r = subprocess.run([sys.executable, "-I"] + args, capture_output=True, text=True, encoding="utf-8", env=env)
    last = (r.stdout.strip().splitlines() or ["(sem saida)"])[-1]
    print("%-40s %s  %s" % (name, "OK   " if r.returncode == 0 else "FALHA", last))
    if r.returncode != 0:
        failed.append(name)
        print("\n".join("    " + line for line in (r.stdout + r.stderr).splitlines() if "FALHA" in line or "Error" in line or "ERRO" in line))

demo = os.path.join(work, "demo")
r = subprocess.run([sys.executable, "-I", os.path.join(CORE, "make_demo_project.py"), demo], capture_output=True, text=True, encoding="utf-8", env=env)
r = subprocess.run([sys.executable, "-I", os.path.join(CORE, "check_project.py"), "--project", demo, "--strict",
                    "--policy", os.path.join(CORE, "permission-policy.v0.1.json"),
                    "--defaults", os.path.join(CORE, "orchestration-defaults.v0.1.json")],
                   capture_output=True, text=True, encoding="utf-8", env=env)
print("%-40s %s  %s" % ("demo: check_project --strict", "OK   " if r.returncode == 0 else "FALHA", r.stdout.strip().splitlines()[-1]))
if r.returncode != 0:
    failed.append("demo")

print("\n%d suite(s) com falha" % len(failed) if failed else "\ntudo verde")
sys.exit(1 if failed else 0)
