#!/usr/bin/env python3
"""Combinacoes de modos, de ponta a ponta: perfil (solo, team, regulated) x pedido (pequeno, com comportamento) x
paralelismo (paths, worktree) x telemetria (split, signed) x log por pessoa (desligado, ligado). Cada eixo ja tem a
sua suite; aqui o que se testa e a combinacao.

Em cada combinacao, um projeto novo com git de verdade passa pelo ciclo inteiro: triagem, Feature Contract (ou caminho
rapido), aprovacao do plano, despacho, edicao (pelo hook de auditoria), relatorio com TDD, validacao independente,
conclusao e aceite. Depois, todos os leitores rodam sobre o mesmo projeto: check, verify do log, next, metrics,
painel, grafo do sistema, OpenTelemetry, pacote de evidencia e a verificacao do CI. Invariantes:
- o log verifica e o check nao acusa erro;
- cada evento cai onde o modo manda (stream da pessoa ou log do dono; telemetria ou log assinado);
- os leitores veem o mesmo ciclo, com ou sem streams e telemetria;
- o caminho e o despacho seguem o perfil e o paralelismo.
Sem git no PATH, o teste e pulado. Uso: python test_modes.py [--quick]   (--quick: so 8 combinacoes)"""
import contextlib
import io
import itertools
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(os.path.dirname(HERE), "hooks")
sys.path.insert(0, HERE)
sys.path.insert(0, HOOKS)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
os.environ["AISEF_USER"] = "alice"
import aisef_ci as ci  # noqa: E402
import aisef_evidence as evd  # noqa: E402
import aisef_metrics as am  # noqa: E402
import aisef_new as an  # noqa: E402
import aisef_next as nx  # noqa: E402
import aisef_otel as otel  # noqa: E402
import aisef_project as ap  # noqa: E402
import aisef_review  # noqa: E402
import aisef_streams as st  # noqa: E402
import aisef_sysgraph as sg  # noqa: E402
import aisef_telemetry as tel  # noqa: E402
import aisef_triage as tri  # noqa: E402
import audit_chain  # noqa: E402
import audit_hook  # noqa: E402
import build_panel  # noqa: E402
import check_project as cp  # noqa: E402

fails = total = 0
SCHEMAS = HERE


def check(name, cond, extra=""):
    global fails, total
    total += 1
    if not cond:
        print("FALHA " + name + "  " + str(extra)[:700])
    fails += not cond


if not shutil.which("git"):
    print("(git ausente: teste pulado)\n\n0 testes, 0 falhas")
    sys.exit(0)


def git(cwd, *args):
    return subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True)


def quiet(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def edit_hook(proj, path, agent):
    """PostToolUse de um Edit feito por um subagente, pelo hook de auditoria de verdade."""
    data = {"tool_name": "Edit", "tool_input": {"file_path": os.path.join(proj, path)}, "cwd": proj,
            "agent_type": "aisef:" + agent, "session_id": "s-1"}
    old = sys.stdin
    sys.stdin = io.StringIO(json.dumps(data))
    try:
        os.environ["CLAUDE_PROJECT_DIR"] = proj
        audit_hook.main()
    finally:
        sys.stdin = old
        os.environ.pop("CLAUDE_PROJECT_DIR", None)


def report(proj, task, agent, n, tdd):
    t0 = ap.now_iso()
    red = ap.iso_in(seconds=-60)
    rid = "RPT-%s" % task["task_id"]
    ev_dir = os.path.join(ap.aisef_dir(proj), "evidence")
    os.makedirs(ev_dir, exist_ok=True)
    open(os.path.join(ev_dir, "EV-%s.txt" % task["task_id"]), "w").write("1 passed\n")
    crits = [c["id"] for c in task["acceptance_criteria"]]
    r = {"schema_version": "0.1.0", "report_id": rid, "task_id": task["task_id"],
         "contract_version": task["contract_version"],
         "agent": {"agent_id": agent, "agent_contract_version": 1, "role": agent},
         "status": "executed", "timing": {"started_at": t0, "finished_at": t0},
         "attempts": {"fix_attempts_used": 0, "specialist_consultations_used": 0},
         "files": {"created": [], "modified": [{"path": p} for p in task_paths(task)], "deleted": []},
         "changes": [{"summary": "mudanca %d" % n, "reason": task["requirements"]["requirement_ids"][0]["id"]}],
         "tests": {"executed": 1, "passed": 1, "failed": 0, "skipped": 0},
         "evidence": [{"id": "EV-1", "type": "test_output", "ref": "evidence/EV-%s.txt" % task["task_id"],
                       "secrets_redacted": True}],
         "criteria_results": [{"criterion_id": c, "required": True, "result": "met", "evidence_ids": ["EV-1"]} for c in crits],
         "problems": [], "risks": [], "pending": [], "limitations": [], "intervention": {"needed": False},
         "technical_report": {"ref": "reports/%s.md" % rid, "sha256": "a" * 64},
         "integrity": {"created_at": t0, "event_log_ref": "events/%s" % task["task_id"]}}
    if tdd:
        r["tdd_evidence"] = {"cycles": [{"behavior": "mudanca %d" % n, "test": "tests/test_shared.py::test_%d" % n,
                                         "red": {"command": "python -m pytest -q", "exit_code": 1, "at": red},
                                         "green": {"command": "python -m pytest -q", "exit_code": 0, "at": t0}}]}
    ap.write_json(os.path.join(ap.aisef_dir(proj), "reports", rid + ".json"), r)
    return r


def task_paths(task):
    return (task.get("scope") or {}).get("paths_allowed") or ["src/shared.py"]


def load_task(proj, tid):
    with open(os.path.join(ap.aisef_dir(proj), "contracts", "tasks", tid + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


def dispatched(res):
    return {t["task_id"]: t for a in res["actions"] if a["kind"] == "dispatch" for t in a["tasks"]}


def append(proj, etype, actor, fid, tid=None, summary=None, **extra):
    p = {"event_type": etype, "actor": {"type": actor[0], "id": actor[1]}, "feature_id": fid,
         "summary": summary or "%s %s" % (tid or fid, etype)}
    if tid:
        p["task_id"] = tid
    p.update(extra)
    return ap.append(proj, p)


BRIEFS = {
    # pedido pequeno, sem mudar comportamento: quick em solo e team; regulated sobe para lean
    "pequeno": {"changes": ["docs"], "paths": ["src/shared.py"], "files": 1, "lines": 4},
    # muda comportamento: lean em solo e regulated; team transforma em full (sugestao)
    "comportamento": {"changes": ["behavior"], "paths": ["src/shared.py"], "files": 1, "lines": 30},
}


def run_combo(i, profile, kind, par, telemetry, streams):
    label = "%s/%s/%s/%s/%s" % (profile, kind, par, telemetry, "streams" if streams else "owner")
    proj = os.path.join(work, "p%02d" % i)
    os.makedirs(os.path.join(proj, "src"))
    git(proj, "init", "-q", "-b", "main")
    git(proj, "config", "user.email", "alice@aisef")
    git(proj, "config", "user.name", "alice")
    open(os.path.join(proj, "src", "shared.py"), "w").write("VALOR = 0\n")
    pid = "PRJ-M%02d" % i
    quiet(ap.init, proj, pid, profile=profile)
    quiet(ap.activate_agents, proj)
    cfg = ap.load_config(proj)
    cfg["parallel"] = {"mode": par}
    cfg.setdefault("audit", {})["telemetry"] = telemetry
    ap.write_json(os.path.join(proj, ".aisef", "config.json"), cfg)
    if streams:
        quiet(st.enable, proj)
    git(proj, "add", "-A")
    git(proj, "commit", "-qm", "init")
    git(proj, "switch", "-qc", "feat/020")

    # 1. triagem pelo perfil
    b = BRIEFS[kind]
    t = tri.triage(proj, paths=b["paths"], changes=b["changes"], files=b["files"], lines=b["lines"])
    expected = {("solo", "pequeno"): "quick", ("team", "pequeno"): "quick", ("regulated", "pequeno"): "lean",
                ("solo", "comportamento"): "lean", ("team", "comportamento"): "full",
                ("regulated", "comportamento"): "lean"}[(profile, kind)]
    check("%s: triagem da %s" % (label, expected), t["path"] == expected, t)

    # 2. contrato
    if t["path"] == "quick":
        quiet(an.cmd_quick, proj, "Ajuste de texto", "doc desatualizada", ["src/shared.py"], "python -m pytest -q")
        fid, tids, tdd = an.MAINT_FEATURE, ["T-MAINT-001"], False
    else:
        two = t["path"] == "full"
        tasks = [{"id": "T-1", "title": "primeira mudanca em shared", "reqs": ["REQ-1"],
                  "criteria": {"AC-1": "teste da primeira"}, "paths": ["src/shared.py"], "parallelizable": True}]
        if two:
            tasks.append({"id": "T-2", "title": "segunda mudanca em shared", "reqs": ["REQ-2"],
                          "criteria": {"AC-2": "teste da segunda"}, "paths": ["src/shared.py"], "parallelizable": True})
        else:
            tasks[0]["kind"] = "slice"
        brief = {"id": "FEAT-020", "title": "Mudanca em shared", "objective": "Testar a combinacao de modos",
                 "problem": "Cada modo tinha teste, a combinacao nao",
                 "requirements": {"REQ-1": "Primeira mudanca", **({"REQ-2": "Segunda mudanca"} if two else {})},
                 "scope_in": ["shared"], "tasks": tasks, "triage": t,
                 "spec": {"solution": "Mudar o modulo shared", "user_stories": ["Como dev quero mudar shared"],
                          "test_seams": ["VALOR"]}}
        try:
            quiet(an.cmd_feature, proj, brief)
        except SystemExit as e:
            check("%s: Feature Contract criado" % label, False, e)
            return
        fid, tids = "FEAT-020", [x["id"] for x in tasks]
        tdd = True
    apr = [n for n in sorted(os.listdir(os.path.join(proj, ".aisef", "approvals")))
           if json.load(open(os.path.join(proj, ".aisef", "approvals", n), encoding="utf-8")).get("status") == "pending"]
    check("%s: um pedido de aprovacao do plano" % label, len(apr) == 1, apr)
    quiet(ap.decide, proj, apr[0][:-5], "approve")

    # 3. despacho conforme o paralelismo
    gs = {"current": "feat/020", "branches": {"main", "feat/020"}}
    d = dispatched(nx.compute_next(proj, feature=fid, git_state=gs))
    want = set(tids) if (len(tids) == 1 or par == "worktree") else {tids[0]}
    check("%s: onda despacha %s" % (label, sorted(want)), set(d) == want, sorted(d))
    for tid in d:
        wt = d[tid].get("worktree")
        check("%s: worktree so no modo worktree (%s)" % (label, tid), bool(wt) == (par == "worktree"), wt)

    # 4. ciclo de cada tarefa (a segunda, no modo paths, vem na onda seguinte)
    executor = "orchestrator" if fid == an.MAINT_FEATURE else "implementer"
    validator = ("orchestrator", "orchestrator") if fid == an.MAINT_FEATURE else ("validator", "validator")
    if streams:
        os.environ["AISEF_USER"] = "bob"  # a segunda pessoa do time executa; a dona (alice) aprovou e aceita
    for n, tid in enumerate(tids, 1):
        task = load_task(proj, tid)
        actor = ("orchestrator", executor) if executor == "orchestrator" else ("agent", executor)
        append(proj, "task_started", actor, fid, tid)
        edit_hook(proj, "src/shared.py", executor)
        open(os.path.join(proj, "src", "shared.py"), "w").write("VALOR = %d\n" % n)
        report_doc = report(proj, task, executor, n, tdd)
        append(proj, "task_executed", actor, fid, tid)
        for rv in aisef_review.status(proj, task, [report_doc])["pending"]:
            quiet(aisef_review.record, proj, tid, rv["role"], "APPROVE", {}, "sem achados")
        if fid != an.MAINT_FEATURE:  # o caminho rapido nao tem validacao independente
            append(proj, "task_validated", validator, fid, tid, summary="%s validada: criterios atendidos" % tid)
        append(proj, "task_completed", ("orchestrator", "orchestrator"), fid, tid)
        for k in (tid,):
            tp = os.path.join(proj, ".aisef", "contracts", "tasks", k + ".json")
            doc = load_task(proj, k)
            doc["state"] = {"status": "completed"}
            ap.write_json(tp, doc)
    os.environ["AISEF_USER"] = "alice"
    git(proj, "add", "-A")
    git(proj, "commit", "-qm", "feature")

    # 5. onde cada evento caiu
    cfg = ap.load_config(proj)
    sdir = os.path.join(proj, ".aisef", "audit", "streams")
    if streams:
        own = os.path.join(sdir, "bob")
        check("%s: eventos de bob no stream dele" % label,
              os.path.isdir(own) and any(e["event_type"] == "task_executed"
                                         for e in audit_chain.read_log_dir(own)), os.listdir(sdir) if os.path.isdir(sdir) else None)
    log = audit_chain.read_log_dir(os.path.join(proj, ".aisef", "audit"))  # todos os streams, em ordem de tempo
    edits_log = [e for e in log if e["event_type"] == "tool_used" and (e.get("data") or {}).get("tool") == "Edit"]
    edits_tel = [r for r in tel.read(proj) if (r.get("data") or {}).get("tool") == "Edit"]
    if telemetry == "split":
        check("%s: edicao na telemetria, fora do log assinado" % label, len(edits_tel) == len(tids) and not edits_log,
              (len(edits_tel), len(edits_log)))
        check("%s: telemetria integra" % label, tel.verify(proj) == [], tel.verify(proj))
    else:
        check("%s: edicao no log assinado" % label, len(edits_log) == len(tids) and not edits_tel,
              (len(edits_log), len(edits_tel)))
    check("%s: leitores veem as %d execucoes" % (label, len(tids)),
          sum(e["event_type"] == "task_executed" for e in log) == len(tids))

    # 6. leitores
    errs, _w = ap.verify(proj)
    check("%s: log verifica" % label, errs == [], errs)
    res = cp.check(proj, policy_path=os.path.join(HERE, "permission-policy.v0.1.json"))
    errors = [f for f in res.findings if f["severity"] == "error"]
    check("%s: check sem erro" % label, not errors, [(f["rule"], f["message"][:160]) for f in errors])
    nxt = nx.compute_next(proj, feature=fid, git_state=gs)
    check("%s: next sem despacho pendente" % label, not dispatched(nxt), nxt.get("stop_reason"))
    m = am.compute_metrics(proj, run_check=False)
    check("%s: metrics ve as tarefas" % label, set(tids) <= set(m.get("tasks", {})), sorted(m.get("tasks", {})))
    quiet(build_panel.build, os.path.join(proj, ".aisef"), os.path.join(work, "panel%02d" % i), SCHEMAS)
    pdata = json.load(open(os.path.join(work, "panel%02d" % i, "panel-data.json"), encoding="utf-8"))
    integ = pdata["manifest"]["integrity"]
    check("%s: painel com integridade ok" % label, integ["status"] == "ok", integ)
    reqs = ["REQ-%d" % k for k in range(1, len(tids) + 1)] if fid != an.MAINT_FEATURE else [an.MAINT_REQ]
    seen = {x["task_id"] for r in reqs for x in sg.impact_req(proj, r).get("tasks", [])}
    check("%s: grafo liga os requisitos as tarefas" % label, set(tids) <= seen, seen)
    tr = otel.export(proj, feature=fid)
    spans = [s for rs in tr["resourceSpans"] for ss in rs["scopeSpans"] for s in ss["spans"]]
    check("%s: OpenTelemetry com um span por tentativa" % label,
          sum(s["name"].startswith("invoke_agent") for s in spans) == len(tids), [s["name"] for s in spans])
    pack = os.path.join(work, "pack%02d" % i)
    quiet(evd.build, proj, fid, pack)
    check("%s: pacote de evidencia verifica" % label, evd.verify(pack) == [], evd.verify(pack))
    rep = ci.run(proj, pr=False, strict=False)
    check("%s: CI aprova" % label, rep.get("ok", not rep.get("errors")), rep)


quick = "--quick" in sys.argv
combos = list(itertools.product(("solo", "team", "regulated"), ("pequeno", "comportamento"), ("paths", "worktree"),
                                ("split", "signed"), (False, True)))
if quick:
    combos = combos[::5]
before = 0
for i, c in enumerate(combos):
    run_combo(i, *c)
    print(("OK    " if fails == before else "FALHA ") + "/".join(c[:4]) + ("/streams" if c[4] else "/owner"))
    before = fails

print("\n%d testes, %d falhas (%d combinacoes)" % (total, fails, len(combos)))
sys.exit(1 if fails else 0)
