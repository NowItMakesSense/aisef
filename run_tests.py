#!/usr/bin/env python3
"""Roda todas as suites do AISEF e resume. Uso: python run_tests.py [--jobs N] [--only texto]   (precisa de jsonschema e cryptography)

As suites sao scripts autonomos (sem pytest), cada uma com sua propria contagem de falhas.
A do painel renderiza em Chrome headless quando o Chrome existe; sem ele, essa parte e pulada.
"""
import os
import re
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
    ("TDD cruzado com o log assinado (E-01)", [os.path.join(CORE, "test_tdd_log.py")]),
    ("cadeia de hash", [os.path.join(CORE, "audit_chain.py"), "selftest", os.path.join(CORE, "audit-event.schema.v0.1.json")]),
    ("assinatura Ed25519", [os.path.join(CORE, "audit_signing.py"), "selftest", os.path.join(CORE, "audit-event.schema.v0.1.json")]),
    ("politica x schemas", [os.path.join(CORE, "check_policy_consistency.py"), os.path.join(CORE, "permission-policy.v0.1.json"),
                            os.path.join(CORE, "authorization.schema.v0.1.json"), os.path.join(CORE, "approval-request.schema.v0.1.json")]),
    ("painel", [os.path.join(CORE, "test_panel.py"), os.path.join(work, "panel")]),
    ("painel: contraste AA dos tokens", [os.path.join(CORE, "test_panel_contrast.py")]),
    ("gateway: Git por risco (F-03)", [os.path.join(HOOKS, "test_git_risk.py")]),
    ("gateway: corpus e contornos (F-02, S-01, S-02)", [os.path.join(HOOKS, "test_gateway_corpus.py")]),
    ("gateway: dependencia nova (S-05)", [os.path.join(HOOKS, "test_deps.py")]),
    ("gateway: conteudo nao confiavel (S-06)", [os.path.join(HOOKS, "test_taint.py")]),
    ("gateway + auditoria + Approval Center", [os.path.join(HOOKS, "test_gateway.py")]),
    ("geradores (briefs e caminho rapido)", [os.path.join(CORE, "test_generators.py")]),
    ("painel ao vivo (Agora, servidor local)", [os.path.join(CORE, "test_panel_live.py")]),
    ("aprendizado continuo e estado apos compact", [os.path.join(CORE, "test_learn.py")]),
    ("ciclo de vida do log", [os.path.join(CORE, "test_audit_lifecycle.py")]),
    ("append: ator e correcoes", [os.path.join(CORE, "test_append_actor.py")]),
    ("roteador de modelo (politica + CLI)", [os.path.join(CORE, "test_route.py")]),
    ("ondas automaticas (waves)", [os.path.join(CORE, "test_waves.py")]),
    ("modo continuo (next) e branch por feature", [os.path.join(CORE, "test_next.py")]),
    ("despacho e validacao em lote (dispatch, precheck)", [os.path.join(CORE, "test_dispatch.py")]),
    ("metricas (metrics)", [os.path.join(CORE, "test_metrics.py")]),
    ("hook de subagentes (tarefa, tokens, duracao)", [os.path.join(HOOKS, "test_agent_events.py")]),
    ("outras sessoes: deteccao e coordenacao", [os.path.join(HOOKS, "test_sessions.py")]),
    ("Approval Center: request e decide reforcado", [os.path.join(CORE, "test_request_decide.py")]),
    ("context engineering (pack, memoria, check_knowledge)", [os.path.join(CORE, "test_context.py")]),
    ("autoridade de design (tokens, design_check)", [os.path.join(CORE, "test_design.py")]),
    ("combinacoes de modos, ciclo inteiro (48)", [os.path.join(CORE, "test_modes.py")]),
    ("log por pessoa, com merge de verdade (T-04, T-05)", [os.path.join(CORE, "test_streams.py")]),
    ("exportacao OpenTelemetry (T-03)", [os.path.join(CORE, "test_otel.py")]),
    ("pacote de evidencia por feature (T-02)", [os.path.join(CORE, "test_evidence.py")]),
    ("verificacao de PR no CI (T-01)", [os.path.join(CORE, "test_ci.py")]),
    ("worktree por fatia, de ponta a ponta (L-02)", [os.path.join(CORE, "test_slices.py")]),
    ("worktree grava no .aisef principal (L-02a)", [os.path.join(CORE, "test_worktree.py")]),
    ("log em camadas: telemetria (F-05)", [os.path.join(CORE, "test_telemetry.py")]),
    ("workflow declarativo (L-03)", [os.path.join(CORE, "test_workflow.py")]),
    ("grafo do sistema consultavel (G-07)", [os.path.join(CORE, "test_sysgraph.py")]),
    ("orcamento e falta de progresso (L-01, L-06)", [os.path.join(CORE, "test_budget.py")]),
    ("check com correcao e rebase-req (F-07)", [os.path.join(CORE, "test_rebase.py")]),
    ("setup em lote do init (C-03)", [os.path.join(CORE, "test_setup.py")]),
    ("migrate e plugin_version (F-06)", [os.path.join(CORE, "test_migrate.py")]),
    ("triagem e caminho enxuto (C-01)", [os.path.join(CORE, "test_triage.py")]),
    ("ambiente: Python com as bibliotecas (C-02)", [os.path.join(CORE, "test_env.py")]),
    ("grafo nativo de imports (G-06)", [os.path.join(CORE, "test_graph.py")]),
    ("hook consultivo graph_nudge", [os.path.join(HOOKS, "test_graph_nudge.py")]),
    ("benchmark: fixtures validos (sem modelo)", [os.path.join(ROOT, "tools", "bench_outcomes.py"), "--check-fixtures"]),
    ("deteccao de stack e arquitetura", [os.path.join(CORE, "test_detect.py")]),
    ("boas praticas (practices)", [os.path.join(CORE, "test_practices.py")]),
    ("verify-loop (verificacao antes de entregar)", [os.path.join(CORE, "test_verify.py")]),
    ("catalogo de agentes (fonte unica)", [os.path.join(CORE, "test_catalog.py")]),
    ("agentes gerados da fonte unica", [os.path.join(ROOT, "tools", "gen_agents.py"), "--check"]),
    ("referencia de regras do check (docs)", [os.path.join(ROOT, "tools", "gen_docs.py"), "--check"]),
]

# H-05 (0.17): --jobs N roda as suites em paralelo (cada uma usa o proprio diretorio temporario); --only filtra pelo nome.
# A saida sai na ordem da lista, como antes.
def _opt(flag, default=None):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv[:-1] else default


JOBS = int(_opt("--jobs", "1"))
ONLY = _opt("--only")
if ONLY:
    SUITES = [s for s in SUITES if ONLY.lower() in s[0].lower()]


def _run(args):
    return subprocess.run([sys.executable, "-I"] + args, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)


if JOBS > 1:
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=JOBS) as pool:
        RESULTS = list(pool.map(lambda s: _run(s[1]), SUITES))
else:
    RESULTS = None

failed = []
checks_total = 0
for i, (name, args) in enumerate(SUITES):
    r = RESULTS[i] if RESULTS is not None else _run(args)
    last = (r.stdout.strip().splitlines() or ["(sem saida)"])[-1]
    m = re.match(r"(\d+) (?:testes|verificacoes)", last.strip())
    checks_total += int(m.group(1)) if m else 0
    print("%-40s %s  %s" % (name, "OK   " if r.returncode == 0 else "FALHA", last))
    if r.returncode != 0:
        failed.append(name)
        print("\n".join("    " + line for line in (r.stdout + r.stderr).splitlines() if "FALHA" in line or "Error" in line or "ERRO" in line))

if ONLY:  # filtro: so as suites pedidas, sem demo nem piso do README (o total muda)
    print("\n%d suite(s) com falha" % len(failed) if failed else "\ntudo verde (so as suites filtradas)")
    sys.exit(1 if failed else 0)

demo = os.path.join(work, "demo")
r = subprocess.run([sys.executable, "-I", os.path.join(CORE, "make_demo_project.py"), demo], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
r = subprocess.run([sys.executable, "-I", os.path.join(CORE, "check_project.py"), "--project", demo, "--strict",
                    "--policy", os.path.join(CORE, "permission-policy.v0.1.json"),
                    "--defaults", os.path.join(CORE, "orchestration-defaults.v0.1.json"),
                    "--now", "2026-11-05T15:00:00-03:00"],  # relogio do demo (make_demo_project.DEMO_NOW)
                   capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
print("%-40s %s  %s" % ("demo: check_project --strict", "OK   " if r.returncode == 0 else "FALHA", r.stdout.strip().splitlines()[-1]))
if r.returncode != 0:
    failed.append("demo")

# os numeros do README: o piso de verificacoes ("2,500+") contra o total medido agora
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_docs  # noqa: E402

wrong = gen_docs.readme_problems(checks_total=checks_total)
print("%-40s %s  %s" % ("README: piso de verificacoes", "FALHA" if wrong else "OK   ",
                        "; ".join(wrong) if wrong else "%d verificacoes medidas" % checks_total))
if wrong:
    failed.append("readme")

print("\n%d suite(s) com falha" % len(failed) if failed else "\ntudo verde")
sys.exit(1 if failed else 0)
