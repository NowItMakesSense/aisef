#!/usr/bin/env python3
"""AISEF: despacho e validacao em lote (0.7.0). Usado por `aisef_project.py dispatch | validate-wave | precheck`.

Antes, cada tarefa da onda custava ao orquestrador tres chamadas (pack, rota, append de delegation), cada uma
passando pelos hooks. Agora:

    dispatch       uma chamada: calcula a onda (mesma regra do `next`), monta pacote de contexto + modelo/effort de
                   cada tarefa, registra os `delegation` e devolve o prompt pronto de cada agente. O orquestrador
                   dispara todos na mesma mensagem.
    validate-wave  um validador para a onda inteira: as tarefas `executed` que passaram no precheck vao num so prompt,
                   no nivel do executor mais alto (outro modelo quando possivel). Quem falha no precheck volta ao
                   executor sem gastar o validador.
    precheck       checagem deterministica de uma tarefa executed, sem modelo e sem rodar comandos: relatorio do
                   executor presente, criterios obrigatorios 'met' com evidencia, evidencia de TDD coerente,
                   arquivos dentro do escopo e (UI) nada fora dos tokens de design.

Nada aqui executa comando do projeto: os testes sao rodados pelos agentes, pelo Bash, onde o gateway os ve.
"""
import datetime
import fnmatch
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_context as ctx  # noqa: E402
import aisef_next as nx  # noqa: E402
import aisef_project as ap  # noqa: E402
import aisef_route as rt  # noqa: E402

PY = "python -I %s" % os.path.join(HERE, "aisef_project.py").replace("\\", "/")


def _load(project, rel):
    with open(os.path.join(ap.aisef_dir(project), rel), encoding="utf-8") as fh:
        return json.load(fh)


def _reports(project, task_id):
    out = []
    rdir = os.path.join(ap.aisef_dir(project), "reports")
    for name in sorted(os.listdir(rdir)) if os.path.isdir(rdir) else []:
        if name.endswith(".json"):
            try:
                r = _load(project, os.path.join("reports", name))
            except (OSError, ValueError):
                continue
            if r.get("task_id") == task_id:
                out.append(r)
    return out


def executor_prompt(project, task, route, attempt, pack_text):
    tid, fid, role = task["task_id"], task["feature_id"], task["assigned_agent"]["agent_id"]
    tdd = (task.get("tests") or {}).get("tdd_required")
    lines = [
        "Voce e o agente `%s` do AISEF. Execute SO a tarefa %s (feature %s), tentativa %d." % (role, tid, fid, attempt),
        "Contrato: .aisef/contracts/tasks/%s.json. Trabalhe so dentro de scope.paths_allowed." % tid,
        "",
        "1. Ao comecar, registre: %s append --project . --type task_started --actor agent --actor-id %s --feature %s "
        "--task %s --summary \"%s iniciada\"" % (PY, role, fid, tid, tid),
        "2. Faca a tarefa%s." % (" com TDD: um comportamento por vez, teste vermelho antes do verde, nos seams de "
                                 "tests.seams; registre cada ciclo em tdd_evidence.cycles" if tdd else ""),
        "3. Grave o Execution Report em .aisef/reports/RPT-%s-%d.json (schema execution-report do plugin) e o "
        "relatorio legivel, com execution_profile = {\"model\": \"%s\", \"effort\": \"%s\", \"level\": %d, \"attempt\": %d}."
        % (tid, attempt, route["model"], route["effort"], route["level"], attempt),
        "4. Ao terminar, registre: %s append --project . --type task_executed --actor agent --actor-id %s --feature %s "
        "--task %s --summary \"%s executada\"" % (PY, role, fid, tid, tid),
        "Achou algo fora do escopo ou uma decisao que nao e sua: pare a parte afetada e reporte em scope_discoveries.",
        "",
        "--- Pacote de contexto ---",
        pack_text,
    ]
    return "\n".join(lines)


def dispatch_wave(project, feature=None, dry_run=False, now=None):
    res = nx.compute_next(project, feature, now=now)
    action = next((a for a in res["actions"] if a["kind"] == "dispatch"), None)
    out = {"stop_reason": res["stop_reason"], "phase": res["guide"]["phase"], "agents": [], "skipped": res["deferred"],
           "other_actions": [a["kind"] for a in res["actions"] if a["kind"] not in ("dispatch", "wait")]}
    if action is None:
        return out
    policy = rt.load_policy()
    for item in action["tasks"]:
        task = rt.load_task(project, item["task_id"])
        route = rt.route(task, policy, attempt=item["attempt"])
        pack = ctx.build_pack(project, item["task_id"])
        prompt = executor_prompt(project, task, route, item["attempt"], ctx.render_pack(pack))
        if not dry_run:
            ap.append(project, {"event_type": "delegation", "actor": {"type": "orchestrator", "id": "orchestrator"},
                                "feature_id": task["feature_id"], "task_id": task["task_id"],
                                "summary": "%s delegada ao %s (%s/%s, tentativa %d)" % (
                                    task["task_id"], task["assigned_agent"]["agent_id"], route["model"], route["effort"],
                                    item["attempt"]),
                                "data": {"model": route["model"], "effort": route["effort"], "level": route["level"],
                                         "attempt": item["attempt"], "context_mode": pack.get("context_mode"),
                                         "lessons": [k["id"] for k in pack["on_demand"]["knowledge"] if k.get("lesson")]}})
        out["agents"].append({"task_id": task["task_id"], "subagent_type": "aisef:" + task["assigned_agent"]["agent_id"],
                              "model": route["model"], "effort": route["effort"], "level": route["level"],
                              "attempt": item["attempt"], "warnings": route.get("warnings", []) + pack["warnings"],
                              "description": "%s: %s" % (task["task_id"], (task.get("title") or "")[:40]),
                              "prompt": prompt})
    return out


def precheck(project, task_id):
    """Problemas deterministicos de uma tarefa executed (lista vazia = pode ir ao validador)."""
    task = rt.load_task(project, task_id)
    agent = task["assigned_agent"]["agent_id"]
    mine = [r for r in _reports(project, task_id) if r.get("agent", {}).get("agent_id") == agent]
    if not mine:
        return ["nenhum Execution Report do executor (%s)" % agent]
    rep = mine[-1]
    problems = ["relatorio %s: %s" % (rep.get("report_id"), p) for p in ap.validate(rep, "execution-report.schema.v0.1.json")]
    if problems:
        return problems[:10]
    if rep["status"] != "executed":
        problems.append("relatorio com status '%s' (esperado executed)" % rep["status"])
    got = {c["criterion_id"]: c for c in rep["criteria_results"]}
    evid = {e["id"] for e in rep["evidence"]}
    for c in task["acceptance_criteria"]:
        r = got.get(c["id"])
        if c.get("required", True) and (r is None or r.get("result") != "met"):
            problems.append("criterio obrigatorio %s nao atendido" % c["id"])
        elif r and r.get("result") == "met" and not set(r.get("evidence_ids", [])) & evid:
            problems.append("criterio %s 'met' sem evidencia listada" % c["id"])
    if (task.get("tests") or {}).get("tdd_required"):
        cycles = (rep.get("tdd_evidence") or {}).get("cycles", [])
        if not cycles:
            problems.append("TDD obrigatorio e o relatorio nao traz tdd_evidence")
        for i, cy in enumerate(cycles, 1):
            if cy["red"]["exit_code"] == 0 or cy["green"]["exit_code"] != 0:
                problems.append("ciclo TDD %d: vermelho precisa falhar e verde precisa passar" % i)
            try:
                if datetime.datetime.fromisoformat(cy["red"]["at"]) >= datetime.datetime.fromisoformat(cy["green"]["at"]):
                    problems.append("ciclo TDD %d: vermelho nao veio antes do verde" % i)
            except (ValueError, TypeError):
                problems.append("ciclo TDD %d: horario ilegivel ou sem fuso" % i)
    allowed = task["scope"].get("paths_allowed")
    if allowed is not None:
        for grp in ("created", "modified", "deleted"):
            for fe in rep["files"][grp]:
                if not any(fnmatch.fnmatch(fe["path"], a) for a in allowed):
                    problems.append("%s fora de paths_allowed" % fe["path"])
    if "ui" in (task.get("touches") or []) and os.path.exists(os.path.join(ap.aisef_dir(project), "design", "tokens.json")):
        import design_check
        bad = design_check.scan(project, allowed or [])
        if bad:
            problems.append("%d valor(es) de UI fora dos tokens de design (ex.: %s:%d %s)"
                            % (len(bad), bad[0]["file"], bad[0]["line"], bad[0]["value"]))
    return problems


def validation_wave(project, feature=None, dry_run=False, now=None):
    res = nx.compute_next(project, feature, now=now)
    todo = [a for a in res["actions"] if a["kind"] == "validate"]
    out = {"rejected_by_precheck": [], "validator": None}
    ready, levels = [], []
    policy = rt.load_policy()
    for a in todo:
        tid = a["task_id"]
        problems = precheck(project, tid)
        task = rt.load_task(project, tid)
        if problems:
            if not dry_run:
                ap.append(project, {"event_type": "task_rejected", "actor": {"type": "orchestrator", "id": "orchestrator"},
                                    "feature_id": task["feature_id"], "task_id": tid,
                                    "summary": "%s reprovada no precheck (sem validador): %s" % (tid, "; ".join(problems)[:300]),
                                    "data": {"precheck": problems[:20]}})
            out["rejected_by_precheck"].append({"task_id": tid, "problems": problems})
            continue
        lvl = next((r["execution_profile"]["level"] for r in reversed(_reports(project, tid))
                    if r.get("execution_profile") and r["agent"]["agent_id"] == task["assigned_agent"]["agent_id"]), None)
        levels.append(lvl if lvl is not None else rt.route(task, policy)["level"])
        ready.append(task)
    if not ready:
        return out
    route = rt.route(ready[0], policy, validator_for_level=max(levels))
    lines = ["Voce e o validador independente do AISEF. Valide CADA tarefa abaixo separadamente; voce nao executou "
             "nenhuma delas (se executou alguma, recuse aquela e avise).",
             "Para cada tarefa: leia o Task Contract e o Execution Report do executor, rode de novo os testes dos "
             "criterios (Bash), confira o diff e a tdd_evidence quando houver. Grave o relatorio de avaliacao "
             ".aisef/reports/RPT-<T>-VAL.json com execution_profile = {\"model\": \"%s\", \"effort\": \"%s\", \"level\": %d} "
             "e registre o veredito de cada uma:" % (route["model"], route["effort"], route["level"]),
             "  aprovada:  %s append --project . --type task_validated --actor validator --actor-id validator "
             "--feature <F> --task <T> --summary \"<T> validada: ...\"" % PY,
             "  reprovada: %s append --project . --type task_rejected --actor validator --actor-id validator "
             "--feature <F> --task <T> --summary \"<T> reprovada: <criterios nao atendidos>\"" % PY, "", "Tarefas:"]
    for t in ready:
        lines.append("- %s (feature %s, executor %s): %s" % (t["task_id"], t["feature_id"], t["assigned_agent"]["agent_id"],
                                                            t.get("title")))
        for c in t["acceptance_criteria"]:
            lines.append("    - %s: %s%s" % (c["id"], c["description"],
                                            " [%s]" % c["verification"]["command"] if c["verification"].get("command") else ""))
    out["validator"] = {"subagent_type": "aisef:validator", "model": route["model"], "effort": route["effort"],
                        "level": route["level"], "task_ids": [t["task_id"] for t in ready],
                        "description": "Validar onda: " + ", ".join(t["task_id"] for t in ready)[:40],
                        "prompt": "\n".join(lines)}
    return out
