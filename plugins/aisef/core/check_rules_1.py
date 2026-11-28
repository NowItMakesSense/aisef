#!/usr/bin/env python3

"""AISEF check: grupo de regras do check_project (ids; requisitos e features; blueprints; dependencias e paralelismo; config (0.5.0)).

H-01 (0.14): saiu da funcao check() do check_project.py sem mudar as regras. Cada funcao recebe `_cx`
(as variaveis do check: rep, feats, tasks, policy...), roda as regras e devolve o que definiu para as seguintes.
A ordem esta em check_project.RULE_GROUPS."""

from check_project import *  # noqa: F401,F403



def rules_ids(_cx):
    """Regras: ids."""
    docs, log, rep = _cx.get("docs"), _cx.get("log"), _cx.get("rep")
    by = {k: {} for k in KINDS}
    for kind, items in docs.items():
        for rel, d in items:
            i = doc_id(kind, d)
            if i in by[kind]:
                rep.err("ID-DUP", rel, "id duplicado '%s' (tambem em %s)" % (i, by[kind][i][0]))
                continue
            by[kind][i] = (rel, d)
            if os.path.splitext(os.path.basename(rel))[0] != i:
                rep.err("ID-FILE", rel, "nome do arquivo difere do id '%s'" % i)
    feats = {i: d for i, (_, d) in by["features"].items()}
    tasks = {i: d for i, (_, d) in by["tasks"].items()}
    agents = {i: d for i, (_, d) in by["agents"].items()}
    # papeis vem do catalogo de agentes (fonte unica); arena_* sao papeis reservados do schema antigo
    known_roles = aisef_catalog.role_ids() | {"arena_challenger", "arena_reviewer"}
    for aid, ag in sorted(agents.items()):
        if ag["role"] not in known_roles:
            rep.err("AGENT-ROLE-UNKNOWN", "agente " + aid, "papel %s nao existe no catalogo de agentes do plugin" % ag["role"])
        for v in (ag.get("validation_role") or {}).get("validates", []):
            if v not in known_roles:
                rep.err("AGENT-ROLE-UNKNOWN", "agente " + aid, "valida o papel %s, que nao existe no catalogo" % v)
    approvals = {i: d for i, (_, d) in by["approvals"].items()}
    auths = {i: d for i, (_, d) in by["authorizations"].items() if d.get("kind") != "mcp_tool"}
    mcp_trusts = {i: d for i, (_, d) in by["authorizations"].items() if d.get("kind") == "mcp_tool"}
    reports = [d for _, d in docs["reports"]]
    events = {e["sequence"]: e for e in log}
    ev_by_task, ev_by_feature = {}, {}
    for e in log:
        if e.get("task_id"):
            ev_by_task.setdefault(e["task_id"], []).append(e)
        if e.get("feature_id"):
            ev_by_feature.setdefault(e["feature_id"], []).append(e)

    def event_from_ref(ref):
        if not isinstance(ref, str) or not ref.startswith("events/"):
            return None
        try:
            return events.get(int(ref.split("/", 1)[1]))
        except ValueError:
            return None

    def task_types(tid):
        return {e["event_type"] for e in ev_by_task.get(tid, [])}

    _cx.update({k: v for k, v in locals().items() if k != "_cx"})



def rules_requisitos_e_features(_cx):
    """Regras: requisitos e features."""
    approvals, by, e, ev_by_feature, feats, i, k, project, ref, rep, tasks, tid = _cx.get("approvals"), _cx.get("by"), _cx.get("e"), _cx.get("ev_by_feature"), _cx.get("feats"), _cx.get("i"), _cx.get("k"), _cx.get("project"), _cx.get("ref"), _cx.get("rep"), _cx.get("tasks"), _cx.get("tid")
    arch_decisions = {}
    for a in approvals.values():
        rr = a.get("resulting_ref")
        if a["status"] == "approved" and rr and rr["kind"] == "architectural_decision":
            arch_decisions[(rr["id"], rr.get("version", 1))] = a

    try:
        with open(os.path.join(project, "config.json"), encoding="utf-8") as fh:
            profile = (json.load(fh) or {}).get("profile") or "team"
    except (OSError, ValueError, AttributeError):
        profile = "team"
    import aisef_workflow  # L-03: o que cada perfil exige vem do workflow.v0.1.json
    overlay = aisef_workflow.profile(profile)
    if not overlay["quick"] and MAINT_FEATURE in feats:
        rep.err("PROFILE-QUICK", "feature " + MAINT_FEATURE, "perfil %s nao tem caminho rapido: mova as tarefas para uma feature" % profile)
    for fid, f in feats.items():
        where = "feature " + fid
        reqs = {}
        for r in f["requirements"]:
            if r["id"] in reqs:
                rep.err("ID-DUP", where, "requisito duplicado " + r["id"])
            reqs[r["id"]] = r
            hv = [h["version"] for h in r["history"]]
            if hv != sorted(set(hv)) or hv[-1] != r["version"]:
                rep.err("REQ-HISTORY", where, "%s: historico %s incompativel com a versao %d" % (r["id"], hv, r["version"]))
        active = {i: r for i, r in reqs.items() if r["status"] == "active"}
        rule_ids = {b["id"] for b in f.get("business_rules", [])}

        if (overlay["tdd_all_executors"] or overlay["blueprint_high_risk"]) and fid != MAINT_FEATURE:  # L-04
            ftasks = [tasks.get(i["task_id"]) for i in f["task_plan"]]
            ftasks = [t for t in ftasks if t is not None]
            for t in ftasks:
                if overlay["tdd_all_executors"] and t["assigned_agent"].get("role") in aisef_catalog.validatable_roles() \
                        and not (t.get("tests") or {}).get("tdd_required"):
                    rep.err("PROFILE-TDD", where, "perfil %s: %s sem TDD (tests.tdd_required)" % (profile, t["task_id"]))
            high = [t["task_id"] for t in ftasks if (t.get("risk") or {}).get("level") in ("high", "critical")]
            if overlay["blueprint_high_risk"] and high and not any(b[1]["feature_id"] == fid for b in by["blueprints"].values()):
                rep.err("PROFILE-BLUEPRINT", where, "perfil %s: risco alto em %s exige Engineering Blueprint"
                        % (profile, ", ".join(high)))
        try:
            import aisef_budget
            with open(os.path.join(project, "config.json"), encoding="utf-8") as fh:
                _cfg = json.load(fh)
        except (OSError, ValueError, ImportError):
            _cfg = {}
        for k in aisef_budget.raised(_cfg if isinstance(_cfg, dict) else {}, f):  # L-01
            rep.err("BUDGET-RAISED", where, "budget.%s acima do limite do projeto: subir e decisao do usuario" % k,
                    {"hint": "baixe o valor no Feature Contract ou peca ao usuario para subir config.json -> budget.%s" % k})
        tri = f.get("triage")
        if tri:  # C-01: caminho escolhido em codigo (aisef_triage.py)
            order = ("quick", "lean", "full")
            if order.index(tri["path"]) < order.index(tri["computed"]):
                rep.err("TRIAGE-OVERRIDDEN-DOWN", where, "caminho %s abaixo do calculado (%s: %s)"
                        % (tri["path"], tri["computed"], "; ".join(tri["reasons"])))
            if tri["path"] == "lean":
                plan = [tasks.get(i["task_id"]) for i in f["task_plan"]]
                if len(plan) != 1 or any(t is not None and t.get("kind") != "slice" for t in plan):
                    rep.err("TRIAGE-LEAN-SHAPE", where, "caminho lean tem exatamente uma fatia (kind slice); o plano tem %d tarefa(s)"
                            % len(plan))
                elif plan[0] is not None and not (plan[0].get("tests") or {}).get("tdd_required"):
                    rep.err("TRIAGE-LEAN-SHAPE", where, "caminho lean exige TDD na fatia %s" % plan[0]["task_id"])

        plan_ids = []
        for item in f["task_plan"]:
            tid = item["task_id"]
            plan_ids.append(tid)
            t = tasks.get(tid)
            if t is None:
                rep.err("PLAN-TASK-MISSING", where, "plano cita a tarefa %s, que nao existe como contrato valido" % tid)
                continue
            if t["feature_id"] != fid:
                rep.err("PLAN-FEATURE", where, "%s pertence a %s, nao a esta feature" % (tid, t["feature_id"]))
            if t["contract_version"] != item["contract_version"]:
                rep.err("PLAN-VERSION", where, "%s: plano espera v%d, contrato esta em v%d" % (tid, item["contract_version"], t["contract_version"]),
                        {"cmd": REBASE % fid, "hint": "alinha o plano as versoes atuais das tarefas"})
            if t["feature_contract_version"] != f["contract_version"]:
                rep.err("PLAN-FEATURE-VERSION", where, "%s foi emitida para a v%d do Feature Contract; a atual e v%d" % (tid, t["feature_contract_version"], f["contract_version"]),
                        {"cmd": REBASE % fid, "hint": "leva as tarefas a versao atual da feature; tarefa iniciada pede reabertura"})
            if set(item.get("depends_on", [])) != set(t.get("dependencies", {}).get("depends_on", [])):
                rep.err("PLAN-DEPS", where, "%s: dependencias do plano diferem das do contrato da tarefa" % tid)
            if item.get("role") and t["assigned_agent"].get("role") and item["role"] != t["assigned_agent"]["role"]:
                rep.warn("PLAN-ROLE", where, "%s: papel do plano (%s) difere do agente (%s)" % (tid, item["role"], t["assigned_agent"]["role"]))
        for tid, t in tasks.items():
            if t["feature_id"] == fid and tid not in plan_ids:
                rep.err("PLAN-ORPHAN-TASK", where, "tarefa %s da feature fora do plano" % tid)

        rtm = {}
        for e in f["rtm"]:
            if e["requirement_id"] in rtm:
                rep.err("RTM-DUP", where, "requisito %s com mais de uma entrada na RTM" % e["requirement_id"])
            rtm[e["requirement_id"]] = e
        for rid in active:
            if rid not in rtm:
                rep.err("RTM-MISSING", where, "requisito ativo %s sem entrada na RTM" % rid)
        for rid, e in rtm.items():
            req = reqs.get(rid)
            if req is None:
                rep.err("RTM-REQ-UNKNOWN", where, "RTM cita requisito inexistente " + rid)
                continue
            if req["status"] != "active":
                rep.err("RTM-REQ-SUPERSEDED", where, "RTM cita requisito substituido " + rid)
            if e["requirement_version"] != req["version"]:
                rep.err("RTM-VERSION", where, "%s: RTM na v%d, requisito na v%d" % (rid, e["requirement_version"], req["version"]))
            for b in e.get("business_rule_ids", []):
                if b not in rule_ids:
                    rep.err("RTM-RULE-UNKNOWN", where, "%s cita regra de negocio inexistente %s" % (rid, b))
            crit_found = set()
            for tid in e["task_ids"]:
                t = tasks.get(tid)
                if t is None:
                    rep.err("RTM-TASK-MISSING", where, "%s: RTM cita a tarefa %s, que nao existe" % (rid, tid))
                    continue
                refs = {(x["id"], x["version"]) for x in t["requirements"]["requirement_ids"]}
                if (rid, req["version"]) not in refs:
                    rep.err("RTM-TASK-NOT-LINKED", where, "%s: a tarefa %s nao declara este requisito (nesta versao)" % (rid, tid),
                            {"cmd": REBASE % fid, "hint": "atualiza a tarefa para a versao atual do requisito"})
                crit_found |= {c["id"] for c in t["acceptance_criteria"]}
            for cid in e["criterion_ids"]:
                if cid not in crit_found:
                    rep.err("RTM-CRITERION-UNKNOWN", where, "%s: criterio %s nao existe nas tarefas ligadas" % (rid, cid))
        for tid in plan_ids:
            t = tasks.get(tid)
            if not t:
                continue
            for x in t["requirements"]["requirement_ids"]:
                e = rtm.get(x["id"])
                if e is not None and tid not in e["task_ids"]:
                    rep.err("RTM-TASK-NOT-IN-RTM", where, "%s declara %s, mas a RTM nao lista a tarefa" % (tid, x["id"]))

        covered = set()
        for c in f["acceptance_criteria"]:
            for rid in c["requirement_ids"]:
                if rid not in active:
                    rep.err("FEAT-CRITERION-REQ", where, "criterio %s cita requisito inexistente ou substituido %s" % (c["id"], rid))
                covered.add(rid)
        for rid in active:
            if rid not in covered:
                rep.err("FEAT-REQ-NO-CRITERION", where, "requisito %s sem criterio de aceite da feature" % rid)

        for ref in f["architectural_decisions"]:
            if (ref["id"], ref["version"]) not in arch_decisions:
                rep.err("FEAT-ARCH-UNKNOWN", where, "decisao arquitetural %s v%d nao tem aprovacao do usuario registrada" % (ref["id"], ref["version"]))

        status = f["state"]["status"]
        plan = f["approval"]["plan"]
        if plan["status"] == "approved":
            if not any(e["event_type"] == "approval_granted" and e["actor"]["type"] == "user" for e in ev_by_feature.get(fid, [])):
                rep.warn("STATE-PLAN-NO-EVENT", where, "plano aprovado sem evento approval_granted do usuario no log")
        if status in ("awaiting_acceptance", "closed"):
            pending = [t for t in plan_ids if t in tasks and tasks[t]["state"]["status"] != "completed"]
            if pending:
                rep.err("STATE-FEATURE-TASKS", where, "feature '%s' com tarefas nao concluidas: %s" % (status, pending))
        if status == "closed" and not any(e["event_type"] == "feature_accepted" and e["actor"]["type"] == "user" for e in ev_by_feature.get(fid, [])):
            rep.err("STATE-CLOSED-NO-ACCEPT", where, "feature encerrada sem evento feature_accepted do usuario")

    _cx.update({k: v for k, v in locals().items() if k != "_cx"})



def rules_blueprints(_cx):
    """Regras: blueprints."""
    active, approvals, arch_decisions, b, by, c, e, f, feats, i, kind, r, ref, rep, reqs, where, x = _cx.get("active"), _cx.get("approvals"), _cx.get("arch_decisions"), _cx.get("b"), _cx.get("by"), _cx.get("c"), _cx.get("e"), _cx.get("f"), _cx.get("feats"), _cx.get("i"), _cx.get("kind"), _cx.get("r"), _cx.get("ref"), _cx.get("rep"), _cx.get("reqs"), _cx.get("where"), _cx.get("x")
    for bid, (_, b) in by["blueprints"].items():
        where = "blueprint " + bid
        f = feats.get(b["feature_id"])
        if f is None:
            rep.err("BP-FEATURE", where, "feature %s nao existe" % b["feature_id"])
            continue
        if b["feature_contract_version"] != f["contract_version"] and b["state"]["status"] != "superseded":
            rep.err("BP-FEATURE-VERSION", where, "baseado na v%d do Feature Contract; a atual e v%d" % (b["feature_contract_version"], f["contract_version"]),
                    {"cmd": REBASE % b["feature_id"], "hint": "acerta a base do blueprint; se ele cita o requisito que mudou, crie a nova versao do blueprint"})
        active = {r["id"] for r in f["requirements"] if r["status"] == "active"}
        allr = {r["id"] for r in f["requirements"]}
        comps = {c["id"] for c in b["architecture"]["components"]}
        if len(comps) != len(b["architecture"]["components"]):
            rep.err("ID-DUP", where, "componentes duplicados")
        eps = {e["id"] for e in b.get("backend", {}).get("endpoints", [])}
        ents = {e["id"]: e for e in b.get("database", {}).get("entities", [])}
        used = set()

        def reqs(kind, ident, ids, count=True):
            for r in ids:
                if count:
                    used.add(r)
                if r not in allr:
                    rep.err("BP-REQ-UNKNOWN", where, "%s %s cita requisito inexistente %s" % (kind, ident, r))
                elif r not in active:
                    rep.err("BP-REQ-SUPERSEDED", where, "%s %s cita requisito substituido %s" % (kind, ident, r))
        for c in b["architecture"]["components"]:
            reqs("componente", c["id"], c["requirement_ids"])
        for i in b["architecture"]["interactions"]:
            for end in (i["from"], i["to"]):
                if end not in comps:
                    rep.err("BP-COMPONENT-UNKNOWN", where, "interacao %s liga o componente inexistente %s" % (i["id"], end))
        for e in b.get("backend", {}).get("endpoints", []):
            reqs("endpoint", e["id"], e["requirement_ids"])
            if e["component_id"] not in comps:
                rep.err("BP-COMPONENT-UNKNOWN", where, "endpoint %s no componente inexistente %s" % (e["id"], e["component_id"]))
        for s_ in b.get("frontend", {}).get("screens", []):
            reqs("tela", s_["id"], s_["requirement_ids"])
            for ep in s_["calls_endpoint_ids"]:
                if ep not in eps:
                    rep.err("BP-ENDPOINT-UNKNOWN", where, "tela %s chama o endpoint inexistente %s" % (s_["id"], ep))
            if s_.get("component_id") and s_["component_id"] not in comps:
                rep.err("BP-COMPONENT-UNKNOWN", where, "tela %s no componente inexistente %s" % (s_["id"], s_["component_id"]))
        for e in ents.values():
            reqs("entidade", e["id"], e["requirement_ids"])
            fields = {x["name"] for x in e["fields"]}
            # so tabela precisa de chave primaria; arquivo, documento ou memoria (storage) nao (A-01)
            if e.get("storage", "table") == "table" and not any(x.get("primary_key") for x in e["fields"]):
                rep.warn("BP-NO-PK", where, "entidade %s sem chave primaria" % e["id"])
            for x in e["fields"]:
                ref = x.get("references")
                if ref:
                    tgt = ents.get(ref["entity_id"])
                    if tgt is None:
                        rep.err("BP-ENTITY-UNKNOWN", where, "%s.%s referencia a entidade inexistente %s" % (e["id"], x["name"], ref["entity_id"]))
                    elif ref["field"] not in {y["name"] for y in tgt["fields"]}:
                        rep.err("BP-FIELD-UNKNOWN", where, "%s.%s referencia o campo inexistente %s.%s" % (e["id"], x["name"], ref["entity_id"], ref["field"]))
            for ix in e.get("indexes", []):
                for fld in ix["fields"]:
                    if fld not in fields:
                        rep.err("BP-FIELD-UNKNOWN", where, "indice de %s usa o campo inexistente %s" % (e["id"], fld))
        for m_ in b.get("database", {}).get("migrations", []):
            for en in m_.get("entity_ids", []):
                if en not in ents:
                    rep.err("BP-ENTITY-UNKNOWN", where, "migracao %s cita a entidade inexistente %s" % (m_["id"], en))
        for th in b["security"]["threats"]:
            for c in th["component_ids"]:
                if c not in comps:
                    rep.err("BP-COMPONENT-UNKNOWN", where, "ameaca %s cita o componente inexistente %s" % (th["id"], c))
        for lv in b["test_strategy"]["levels"]:
            reqs("teste", lv["level"], lv["covers"], count=False)
        for ref in b["architecture"]["decisions"]:
            if (ref["id"], ref["version"]) not in arch_decisions:
                rep.err("BP-ADR-UNAPPROVED", where, "decisao %s v%d sem aprovacao do usuario registrada" % (ref["id"], ref["version"]))
        tested = {r for lv in b["test_strategy"]["levels"] for r in lv["covers"]}
        for r in sorted(active - used):
            rep.warn("BP-REQ-UNCOVERED", where, "requisito ativo %s nao e atendido por nenhum elemento do desenho" % r)
        for r in sorted(active - tested):
            rep.warn("BP-REQ-UNTESTED", where, "requisito ativo %s sem nivel de teste na estrategia" % r)
        if b["approval"]["status"] == "approved":
            ar = approvals.get(b["approval"].get("request_ref"))
            if ar is None or ar["status"] != "approved":
                rep.err("BP-APPROVAL-REF", where, "aprovacao do blueprint aponta para pedido inexistente ou nao aprovado")
        if b["state"]["status"] == "approved" and f["approval"]["plan"]["status"] != "approved":
            rep.warn("BP-BEFORE-PLAN", where, "blueprint aprovado antes do plano da feature")
        if len([x for x in by["blueprints"].values() if x[1]["feature_id"] == b["feature_id"] and x[1]["state"]["status"] != "superseded"]) > 1:
            rep.err("BP-MULTIPLE-ACTIVE", where, "mais de um blueprint vigente para a feature %s" % b["feature_id"])

    _cx.update({k: v for k, v in locals().items() if k != "_cx"})



def rules_dependencias_e_paralelismo(_cx):
    """Regras: dependencias e paralelismo."""
    a, b, c, d, i, ids, rep, t, tasks, tid, x, y = _cx.get("a"), _cx.get("b"), _cx.get("c"), _cx.get("d"), _cx.get("i"), _cx.get("ids"), _cx.get("rep"), _cx.get("t"), _cx.get("tasks"), _cx.get("tid"), _cx.get("x"), _cx.get("y")
    graph = {}
    for tid, t in tasks.items():
        deps = t.get("dependencies", {}).get("depends_on", [])
        graph[tid] = list(deps)
        for d in deps:
            if d == tid:
                rep.err("DEP-CYCLE", "tarefa " + tid, "depende de si mesma")
            elif d not in tasks:
                rep.err("DEP-UNKNOWN", "tarefa " + tid, "depende de %s, que nao existe" % d)
            elif tasks[d]["feature_id"] != t["feature_id"]:
                rep.warn("DEP-CROSS-FEATURE", "tarefa " + tid, "depende de %s, de outra feature" % d)
    state, cycles = {}, set()

    def dfs(n, stack):
        state[n] = 1
        for m in graph.get(n, []):
            if m not in graph:
                continue
            if state.get(m) == 1:
                cycles.add(tuple(sorted(stack[stack.index(m):] + [m] if m in stack else [n, m])))
            elif state.get(m) is None:
                dfs(m, stack + [m])
        state[n] = 2

    for n in graph:
        if state.get(n) is None:
            dfs(n, [n])
    for c in cycles:
        rep.err("DEP-CYCLE", "tarefas", "ciclo de dependencias entre %s" % ", ".join(c))

    def reach(a):
        seen, todo = set(), list(graph.get(a, []))
        while todo:
            x = todo.pop()
            if x in seen or x not in graph:
                continue
            seen.add(x)
            todo.extend(graph[x])
        return seen

    ids = sorted(tasks)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            ta, tb = tasks[a], tasks[b]
            if ta["feature_id"] != tb["feature_id"]:
                continue
            if not (ta.get("dependencies", {}).get("parallelizable") and tb.get("dependencies", {}).get("parallelizable")):
                continue
            if b in reach(a) or a in reach(b):
                continue
            ea, eb = ta["scope"].get("exclusive_files", []), tb["scope"].get("exclusive_files", [])
            pa, pb = ta["scope"].get("paths_allowed", []), tb["scope"].get("paths_allowed", [])
            if any(overlaps(x, y) for x in ea for y in eb + pb) or any(overlaps(x, y) for x in eb for y in ea + pa):
                rep.err("PAR-FILE-CONFLICT", "tarefas %s/%s" % (a, b), "tarefas paralelas com arquivos exclusivos em conflito")
            elif any(overlaps(x, y) for x in pa for y in pb) and not all(
                    (t.get("state") or {}).get("status") in ("completed", "cancelled") for t in (ta, tb)):
                # duas tarefas ja encerradas nao rodam mais juntas: a sobreposicao so importa enquanto alguma esta aberta
                rep.warn("PAR-PATH-OVERLAP", "tarefas %s/%s" % (a, b), "tarefas paralelas com caminhos permitidos que se sobrepoem")

    _cx.update({k: v for k, v in locals().items() if k != "_cx"})



def rules_config(_cx):
    """Regras: config (0.5.0)."""
    fh, project, rep = _cx.get("fh"), _cx.get("project"), _cx.get("rep")
    cfg_path = os.path.join(project, "config.json")
    if os.path.exists(cfg_path):
        import aisef_project  # noqa: E402 (import tardio)
        try:
            with open(cfg_path, encoding="utf-8") as fh:
                cfg = json.load(fh)
        except (OSError, ValueError) as exc:
            rep.err("CONFIG-GIT", "config.json", "ilegivel: %s" % exc)
            cfg = {}
        for problem in aisef_project.git_settings(cfg if isinstance(cfg, dict) else {})[1]:
            rep.err("CONFIG-GIT", "config.json", problem)
        for problem in aisef_project.graphify_settings(cfg if isinstance(cfg, dict) else {})[1]:
            rep.err("CONFIG-GRAPHIFY", "config.json", problem)
        prof = (cfg if isinstance(cfg, dict) else {}).get("profile")
        if prof is not None and prof not in aisef_project.PROFILES:
            rep.err("CONFIG-PROFILE", "config.json", "profile %r invalido (use %s)" % (prof, ", ".join(aisef_project.PROFILES)))
        par = ((cfg if isinstance(cfg, dict) else {}).get("parallel") or {}).get("mode")
        if par is not None and par not in aisef_project.PARALLEL_MODES:  # L-02
            rep.err("CONFIG-PARALLEL", "config.json", "parallel.mode %r invalido (use %s)" % (par, ", ".join(aisef_project.PARALLEL_MODES)))

    _cx.update({k: v for k, v in locals().items() if k != "_cx"})
