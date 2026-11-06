#!/usr/bin/env python3
"""AISEF: roteador de modelo e effort por tarefa (selecao hibrida, custo primeiro).

Le o Task Contract, o Agent Contract do papel e a Model Policy (model-policy.v0.1.json) e decide
qual modelo e effort usar ao delegar a tarefa. Nao chama nenhum modelo: so imprime a decisao.

Uso:
    python -I aisef_route.py --project REPO --task T-001 [--attempt N] [--allow-fable]
    python -I aisef_route.py --project REPO --task T-001 --validator --executor-level L3   (ou 3)

Saida (JSON): {task_id, role, model, effort, level, reasons[], warnings[]}

Regras (detalhes e justificativa na propria politica):
  nivel = padrao do papel + sinais (+1 cada: risco alto/critico, recurso sensivel, complexity complex,
          mais de 10 paths; -1: complexity trivial) + (attempt - 1), dentro de [L0, L6].
  fable (L7) so com --allow-fable. Validador: menor nivel >= executor com modelo diferente do do executor.
Codigo de saida: 0 ok, 2 entrada invalida (tarefa/politica/papel).
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
POLICY_PATH = os.path.join(HERE, "model-policy.v0.1.json")
ENV_OVERRIDES = ("CLAUDE_CODE_EFFORT_LEVEL", "CLAUDE_CODE_SUBAGENT_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL_FORCE")


class RouteError(Exception):
    pass


def load_policy(path=POLICY_PATH):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def check_policy(policy):
    """Consistencia interna da politica; devolve lista de problemas (vazia = ok)."""
    p = []
    ladder = policy.get("ladder", [])
    if not ladder or [r.get("level") for r in ladder] != list(range(len(ladder))):
        p.append("a escada precisa ser L0..Ln em ordem, sem buracos")
    if policy.get("ceiling_level") != len(ladder) - 1:
        p.append("ceiling_level deve ser o ultimo nivel da escada")
    if policy.get("floor_level") != 0:
        p.append("floor_level deve ser 0")
    fx = policy.get("fable_extension", {})
    if fx.get("level") != len(ladder) or fx.get("model") != "fable":
        p.append("fable_extension deve ser o nivel logo acima do teto, com modelo fable")
    for role, lv in policy.get("role_defaults", {}).items():
        if not isinstance(lv, int) or not 0 <= lv <= policy.get("ceiling_level", -1):
            p.append("padrao do papel %s fora da escada" % role)
    sd = policy.get("validator", {}).get("static_default", {})
    if not any(r["level"] == sd.get("level") and r["model"] == sd.get("model") and r["effort"] == sd.get("effort") for r in ladder):
        p.append("validator.static_default nao corresponde a um nivel da escada")
    return p


def parse_level(value):
    """Aceita 3, '3' ou 'L3'."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    s = str(value).strip().upper()
    if s.startswith("L"):
        s = s[1:]
    if not s.isdigit():
        raise RouteError("nivel invalido: %r (use L0..L7 ou o numero)" % (value,))
    return int(s)


def _entry(policy, level):
    for r in policy["ladder"]:
        if r["level"] == level:
            return r
    fx = policy["fable_extension"]
    if level == fx["level"]:
        return fx
    raise RouteError("nivel L%d inexistente na politica" % level)


def env_warnings(environ):
    return ["variavel %s esta definida (%s) e anula a escolha do roteador: o Claude Code da precedencia a ela"
            % (v, environ[v]) for v in ENV_OVERRIDES if environ.get(v)]


def signals_for(task_doc, policy):
    """Devolve [(delta, motivo)] dos sinais da tarefa."""
    s = policy["signals"]
    out = []
    risk = (task_doc.get("risk") or {}).get("level")
    if risk in s["high_risk_levels"]:
        out.append((s["up_step"], "risco da tarefa %s" % risk))
    resources = (task_doc.get("permissions") or {}).get("resources") or []
    touched = [r for r in resources if r in s["sensitive_resources"]]
    if touched:
        out.append((s["up_step"], "toca recurso sensivel (%s)" % ", ".join(touched)))
    complexity = task_doc.get("complexity", "normal")
    if complexity == s["complex_value"]:
        out.append((s["up_step"], "complexity complex"))
    elif complexity == s["trivial_value"]:
        out.append((-s["down_step"], "complexity trivial"))
    paths = (task_doc.get("scope") or {}).get("paths_allowed") or []
    if len(paths) > s["paths_more_than"]:
        out.append((s["up_step"], "%d paths permitidos (mais de %d)" % (len(paths), s["paths_more_than"])))
    return out


def route(task_doc, policy, attempt=1, allow_fable=False, validator_for_level=None, environ=None):
    """Decide modelo/effort/nivel. validator_for_level = nivel do executor quando se roteia o VALIDADOR."""
    environ = os.environ if environ is None else environ
    role = task_doc["assigned_agent"]["role"]
    if role in policy["not_routed_roles"]:
        raise RouteError("o papel %s nao e roteado (roda na sessao principal)" % role)
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        raise RouteError("attempt deve ser inteiro >= 1")
    ceiling = policy["fable_extension"]["level"] if allow_fable else policy["ceiling_level"]
    reasons, warnings = [], env_warnings(environ)
    out_role = role

    if validator_for_level is not None:
        out_role = "validator"
        exec_level = parse_level(validator_for_level)
        if exec_level > ceiling:
            raise RouteError("nivel do executor L%d acima do teto permitido (L%d)%s"
                             % (exec_level, ceiling, "" if allow_fable else "; L7 exige --allow-fable"))
        exec_model = _entry(policy, exec_level)["model"]
        level = None
        for lv in range(exec_level, ceiling + 1):
            if _entry(policy, lv)["model"] != exec_model:
                level = lv
                break
        if level is None:
            level = exec_level
            reasons.append("validador: nenhum nivel >= L%d com modelo diferente de %s; usa o mesmo nivel" % (exec_level, exec_model))
        else:
            reasons.append("validador: menor nivel >= L%d com modelo diferente do executor (%s)" % (exec_level, exec_model))
    elif role == "validator":
        level = policy["validator"]["static_default"]["level"]
        reasons.append("papel validator sem nivel do executor: padrao estatico L%d" % level)
        warnings.append("validador roteado sem --executor-level: usado o padrao estatico; passe o nivel do executor para aplicar a regra de modelo diferente")
    else:
        if role not in policy["role_defaults"]:
            raise RouteError("papel sem padrao na politica: %s" % role)
        level = policy["role_defaults"][role]
        reasons.append("padrao do papel %s: L%d" % (role, level))
        for delta, why in signals_for(task_doc, policy):
            level += delta
            reasons.append("%+d: %s" % (delta, why))
        if attempt > 1:
            step = policy["escalation"]["per_failed_attempt"] * (attempt - 1)
            level += step
            reasons.append("+%d: tentativa %d (escalonamento por falha anterior)" % (step, attempt))
        floor = policy["floor_level"]
        if level < floor:
            reasons.append("piso: L%d -> L%d" % (level, floor))
            level = floor
        if level > ceiling:
            reasons.append("teto: L%d -> L%d%s" % (level, ceiling, "" if allow_fable else " (fable so com --allow-fable)"))
            level = ceiling

    e = _entry(policy, level)
    return {"task_id": task_doc["task_id"], "role": out_role, "model": e["model"], "effort": e["effort"],
            "level": level, "reasons": reasons, "warnings": warnings}


def load_task(project, task_id):
    path = os.path.join(project, ".aisef", "contracts", "tasks", task_id + ".json")
    if not os.path.exists(path):
        raise RouteError("Task Contract nao encontrado: %s" % path)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def agent_contract_warnings(project, task_doc):
    """Confere o Agent Contract do papel; so avisa, nunca bloqueia (a validacao e do check_project)."""
    aid = task_doc["assigned_agent"]["agent_id"]
    path = os.path.join(project, ".aisef", "contracts", "agents", aid + ".json")
    if not os.path.exists(path):
        return ["Agent Contract %s nao encontrado em .aisef/contracts/agents" % aid]
    with open(path, encoding="utf-8") as fh:
        ag = json.load(fh)
    w = []
    if ag.get("role") != task_doc["assigned_agent"]["role"]:
        w.append("papel do Agent Contract (%s) difere do da tarefa (%s)" % (ag.get("role"), task_doc["assigned_agent"]["role"]))
    if ag.get("status") != "active":
        w.append("agente %s esta '%s', nao 'active'" % (aid, ag.get("status")))
    return w


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--attempt", type=int, default=1)
    ap.add_argument("--allow-fable", action="store_true", help="permite fable (L7); so por pedido explicito do usuario")
    ap.add_argument("--validator", action="store_true", help="rotear o validador desta tarefa")
    ap.add_argument("--executor-level", help="nivel usado pelo executor (Lk ou k); obrigatorio com --validator")
    ap.add_argument("--policy", default=POLICY_PATH)
    a = ap.parse_args(argv[1:])
    try:
        if a.validator != (a.executor_level is not None):
            raise RouteError("--validator e --executor-level andam juntos")
        policy = load_policy(a.policy)
        problems = check_policy(policy)
        if problems:
            raise RouteError("politica invalida: " + "; ".join(problems))
        task = load_task(a.project, a.task)
        res = route(task, policy, attempt=a.attempt, allow_fable=a.allow_fable,
                    validator_for_level=a.executor_level if a.validator else None)
        res["warnings"] += agent_contract_warnings(a.project, task)
    except (RouteError, KeyError, ValueError) as e:
        print("erro: %s" % e, file=sys.stderr)
        return 2
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
