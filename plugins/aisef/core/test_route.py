#!/usr/bin/env python3
"""Testes do roteador de modelo (aisef_route.py) e da Model Policy: padroes por papel, cada sinal,
piso/teto, escalonamento, fable bloqueado, regra do validador, avisos de ambiente e contrato sem complexity."""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_route as ar  # noqa: E402
import make_demo_project as demo  # noqa: E402

POLICY = ar.load_policy()
CLEAN_ENV = {}
fails = total = 0


def check(name, cond, extra=""):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond else "  " + str(extra)))
    fails += not cond


def task(role="backend", risk="low", resources=("repo_code",), complexity=None, paths=2):
    d = {"task_id": "T-900", "assigned_agent": {"agent_id": role + "-1", "agent_contract_version": 1, "role": role},
         "risk": {"level": risk}, "permissions": {"environment": "dev", "scope_authorization_id": None, "resources": list(resources)},
         "scope": {"included": ["x"], "excluded": [], "paths_allowed": ["src/p%d/*" % i for i in range(paths)]}}
    if complexity:
        d["complexity"] = complexity
    return d


def r(t, **kw):
    kw.setdefault("environ", CLEAN_ENV)
    return ar.route(t, POLICY, **kw)


def raises(fn):
    try:
        fn()
        return False
    except ar.RouteError:
        return True


# ---------------------------------------------------------------- politica
check("politica consistente", ar.check_policy(POLICY) == [], ar.check_policy(POLICY))
bad = copy.deepcopy(POLICY)
bad["ladder"][2]["level"] = 9
check("politica com escada quebrada e detectada", ar.check_policy(bad) != [])
check("escada L0..L6 na ordem pedida",
      [(e["model"], e["effort"]) for e in POLICY["ladder"]] ==
      [("haiku", "low"), ("haiku", "medium"), ("sonnet", "low"), ("sonnet", "medium"), ("sonnet", "high"), ("opus", "medium"), ("opus", "high")])

# ---------------------------------------------------------------- padroes por papel (tarefa neutra)
expected = {"domain": (0, "haiku", "low"), "devops": (1, "haiku", "medium"), "frontend": (2, "sonnet", "low"),
            "qa": (2, "sonnet", "low"), "backend": (3, "sonnet", "medium"), "database": (3, "sonnet", "medium"),
            "security": (4, "sonnet", "high")}
for role, (lv, model, effort) in expected.items():
    x = r(task(role))
    check("padrao do papel %s: L%d %s/%s" % (role, lv, model, effort), (x["level"], x["model"], x["effort"]) == (lv, model, effort), x)
x = r(task("backend"))
check("saida tem os campos pedidos", set(x) == {"task_id", "role", "model", "effort", "level", "reasons", "warnings"} and x["task_id"] == "T-900"
      and x["role"] == "backend" and x["warnings"] == [] and x["reasons"], x)
check("orquestrador nao e roteado", raises(lambda: r(task("orchestrator"))))
check("papel desconhecido e recusado", raises(lambda: r(task("padeiro"))))

# ---------------------------------------------------------------- sinais (+1 cada)
check("sinal: risco medium nao conta", r(task(risk="medium"))["level"] == 3)
check("sinal: risco high +1", r(task(risk="high"))["level"] == 4)
check("sinal: risco critical +1", r(task(risk="critical"))["level"] == 4)
for res in ("sensitive_files", "db_data", "db_schema", "config_ci_iac", "deploy_infra"):
    check("sinal: recurso %s +1" % res, r(task(resources=["repo_code", res]))["level"] == 4)
check("sinal: varios recursos sensiveis contam uma vez so", r(task(resources=["db_schema", "config_ci_iac", "deploy_infra"]))["level"] == 4)
check("sinal: repo_code sozinho nao conta", r(task(resources=["repo_code"]))["level"] == 3)
check("sinal: complexity complex +1", r(task(complexity="complex"))["level"] == 4)
check("sinal: complexity normal 0", r(task(complexity="normal"))["level"] == 3)
check("sinal: complexity trivial -1", r(task(complexity="trivial"))["level"] == 2)
check("sinal: 10 paths nao conta", r(task(paths=10))["level"] == 3)
check("sinal: 11 paths +1", r(task(paths=11))["level"] == 4)
x = r(task(risk="high", resources=["db_schema"], complexity="complex", paths=11))
check("sinais cumulativos: backend com os quatro sinais sobe 4 niveis (L7 vira teto L6)", x["level"] == 6 and any("teto" in s for s in x["reasons"]), x)
check("sinais cumulativos: dois sinais", r(task(risk="high", complexity="complex"))["level"] == 5)
check("sinais +1 e -1 se anulam", r(task(risk="high", complexity="trivial"))["level"] == 3)
check("razoes citam cada sinal", len(r(task(risk="high", complexity="complex"))["reasons"]) == 3)

# ---------------------------------------------------------------- piso e teto
check("piso: domain trivial fica em L0", r(task("domain", complexity="trivial"))["level"] == 0)
x = r(task("domain", complexity="trivial"))
check("piso registrado nas razoes", any("piso" in s for s in x["reasons"]), x)
check("piso: devops trivial = L0 (haiku/low)", (r(task("devops", complexity="trivial"))["model"], r(task("devops", complexity="trivial"))["effort"]) == ("haiku", "low"))
check("teto: security com todos os sinais fica em L6 opus/high",
      (lambda x: (x["level"], x["model"], x["effort"]))(r(task("security", risk="critical", resources=["sensitive_files"], complexity="complex", paths=20))) == (6, "opus", "high"))

# ---------------------------------------------------------------- escalonamento
check("tentativa 1: sem escalonamento", r(task(), attempt=1)["level"] == 3)
check("tentativa 2: +1", r(task(), attempt=2)["level"] == 4)
check("tentativa 3: +2", r(task(), attempt=3)["level"] == 5)
check("escalonamento soma com sinais", r(task(risk="high"), attempt=3)["level"] == 6)
check("escalonamento respeita o teto L6", r(task(), attempt=9)["level"] == 6)
check("escalonamento parte do piso (domain tentativa 2 = L1)", r(task("domain"), attempt=2)["level"] == 1)
check("attempt invalido e recusado", raises(lambda: r(task(), attempt=0)) and raises(lambda: r(task(), attempt="2")))

# ---------------------------------------------------------------- fable
x = r(task("security", risk="high", complexity="complex", paths=11), attempt=5)
check("fable nunca e escolhido sem flag (teto L6, opus)", x["level"] == 6 and x["model"] == "opus", x)
x = r(task("security", risk="high", complexity="complex", paths=11), attempt=5, allow_fable=True)
check("com --allow-fable o teto passa a L7 fable/high", (x["level"], x["model"], x["effort"]) == (7, "fable", "high"), x)
x = r(task("backend"), allow_fable=True)
check("--allow-fable nao muda tarefa que nao chega ao teto", (x["level"], x["model"]) == (3, "sonnet"), x)
x = r(task("security", risk="high", complexity="complex"), allow_fable=True)
check("--allow-fable: L6 natural continua opus/high (L7 so se o calculo passar de L6)", (x["level"], x["model"]) == (6, "opus"), x)

# ---------------------------------------------------------------- validador
expected_val = {0: 2, 1: 2, 2: 5, 3: 5, 4: 5, 5: 5, 6: 6}  # menor nivel >= executor com modelo diferente; opus = mesmo nivel
for ex_lv, val_lv in expected_val.items():
    x = r(task("backend"), validator_for_level=ex_lv)
    exec_model = POLICY["ladder"][ex_lv]["model"]
    check("validador: executor L%d (%s) -> L%d (%s)" % (ex_lv, exec_model, val_lv, POLICY["ladder"][val_lv]["model"]),
          x["level"] == val_lv and x["role"] == "validator" and x["level"] >= ex_lv
          and (x["model"] != exec_model or exec_model == "opus"), x)
check("validador: executor opus usa o mesmo nivel e justifica",
      any("mesmo nivel" in s for s in r(task("backend"), validator_for_level=6)["reasons"]))
check("validador: aceita 'L3' e '3'", r(task(), validator_for_level="L3")["level"] == r(task(), validator_for_level="3")["level"] == 5)
check("validador: nivel invalido recusado", raises(lambda: r(task(), validator_for_level="abc")))
check("validador: L7 do executor exige allow_fable", raises(lambda: r(task(), validator_for_level=7)))
x = r(task(), validator_for_level=7, allow_fable=True)
check("validador: executor fable (L7) usa o mesmo nivel", x["level"] == 7 and x["model"] == "fable", x)
check("validador ignora sinais e tentativa da tarefa (so depende do executor)",
      r(task(risk="critical"), attempt=4, validator_for_level=3)["level"] == 5)
x = r(task("validator"))
check("papel validator sem nivel do executor: padrao estatico L3 sonnet/medium + aviso",
      (x["level"], x["model"], x["effort"]) == (3, "sonnet", "medium") and x["warnings"], x)

# ---------------------------------------------------------------- avisos de ambiente
check("sem variaveis de ambiente: sem avisos", r(task())["warnings"] == [])
for var in ar.ENV_OVERRIDES:
    w = r(task(), environ={var: "opus"})["warnings"]
    check("aviso quando %s esta definida" % var, len(w) == 1 and var in w[0] and "anula" in w[0], w)
w = r(task(), environ=dict.fromkeys(ar.ENV_OVERRIDES, "x"))["warnings"]
check("tres variaveis definidas: tres avisos", len(w) == 3)
check("variavel vazia nao avisa", r(task(), environ={"CLAUDE_CODE_EFFORT_LEVEL": ""})["warnings"] == [])
old = os.environ.get("CLAUDE_CODE_SUBAGENT_MODEL_FORCE")
os.environ["CLAUDE_CODE_SUBAGENT_MODEL_FORCE"] = "haiku"
try:
    check("route() le os.environ por padrao", len(ar.route(task(), POLICY)["warnings"]) == 1)
finally:
    if old is None:
        del os.environ["CLAUDE_CODE_SUBAGENT_MODEL_FORCE"]
    else:
        os.environ["CLAUDE_CODE_SUBAGENT_MODEL_FORCE"] = old

# ---------------------------------------------------------------- contrato sem complexity (antigo)
t_old = task()
check("contrato sem complexity equivale a normal", "complexity" not in t_old and r(t_old)["level"] == 3)
check("route nao altera o contrato recebido", t_old == task())

# ---------------------------------------------------------------- CLI contra o projeto demo
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
try:
    proj = os.path.join(work, "p")
    demo.make(os.path.join(proj, ".aisef"))
    env = {k: v for k, v in os.environ.items() if k not in ar.ENV_OVERRIDES}

    def cli(*args, env=env):
        p = subprocess.run([sys.executable, "-I", os.path.join(HERE, "aisef_route.py"), "--project", proj] + list(args),
                           capture_output=True, text=True, encoding="utf-8", env=env)
        return p.returncode, p.stdout, p.stderr

    code, out, err = cli("--task", "T-001")
    j = json.loads(out) if code == 0 else {}
    check("CLI: roteia a tarefa do demo e imprime JSON", code == 0 and j.get("task_id") == "T-001" and j.get("model") and j.get("level") is not None, (code, err))
    code, out, err = cli("--task", "T-001", "--attempt", "3")
    check("CLI: --attempt escalona", code == 0 and json.loads(out)["level"] == min(6, j["level"] + 2), (out, err))
    code, out, err = cli("--task", "T-001", "--validator", "--executor-level", "L3")
    check("CLI: --validator --executor-level", code == 0 and json.loads(out)["role"] == "validator" and json.loads(out)["level"] == 5, (out, err))
    check("CLI: --validator sem --executor-level e erro", cli("--task", "T-001", "--validator")[0] == 2)
    check("CLI: tarefa inexistente e erro", cli("--task", "T-404")[0] == 2)
    code, out, err = cli("--task", "T-001", env=dict(env, CLAUDE_CODE_SUBAGENT_MODEL="haiku"))
    check("CLI: avisa quando CLAUDE_CODE_SUBAGENT_MODEL esta definida", code == 0 and any("CLAUDE_CODE_SUBAGENT_MODEL" in w for w in json.loads(out)["warnings"]), out)
finally:
    shutil.rmtree(work, ignore_errors=True)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
