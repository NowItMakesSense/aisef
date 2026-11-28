#!/usr/bin/env python3

"""AISEF check: grupo de regras do check_project (tarefas; relatorios; SDD + TDD (fatias, spec e red-green); autoridade de design (0.6.1) / arquitetura detectada (aisef_detect); roteamento de modelo (execution_profile); aprovacoes e autorizacoes).

H-01 (0.14): saiu da funcao check() do check_project.py sem mudar as regras. Cada funcao recebe `_cx`
(as variaveis do check: rep, feats, tasks, policy...), roda as regras e devolve o que definiu para as seguintes.
A ordem esta em check_project.RULE_GROUPS."""

from check_project import *  # noqa: F401,F403



def rules_tarefas(_cx):
    """Regras: tarefas."""
    a, ag, agents, auths, c, d, f, feats, graph, known_roles, lv, now, order, policy, project, r, rep, reports, reqs, t, task_types, tasks, tid, v, where, x = _cx.get("a"), _cx.get("ag"), _cx.get("agents"), _cx.get("auths"), _cx.get("c"), _cx.get("d"), _cx.get("f"), _cx.get("feats"), _cx.get("graph"), _cx.get("known_roles"), _cx.get("lv"), _cx.get("now"), _cx.get("order"), _cx.get("policy"), _cx.get("project"), _cx.get("r"), _cx.get("rep"), _cx.get("reports"), _cx.get("reqs"), _cx.get("t"), _cx.get("task_types"), _cx.get("tasks"), _cx.get("tid"), _cx.get("v"), _cx.get("where"), _cx.get("x")
    validators =[a for a in agents.values() if a["role"] == "validator" and a["status"] == "active"]
    for tid, t in tasks.items():
        where = "tarefa " + tid
        f = feats.get(t["feature_id"])
        if f is None:
            rep.err("TASK-FEATURE", where, "feature %s nao existe" % t["feature_id"])
        else:
            reqs = {r["id"]: r for r in f["requirements"]}
            for x in t["requirements"]["requirement_ids"]:
                r = reqs.get(x["id"])
                if r is None:
                    rep.err("TASK-REQ-UNKNOWN", where, "requisito %s nao existe na feature" % x["id"])
                elif r["status"] != "active":
                    rep.err("TASK-REQ-SUPERSEDED", where, "requisito %s foi substituido" % x["id"])
                elif r["version"] != x["version"]:
                    rep.err("TASK-REQ-VERSION", where, "%s na v%d, requisito atual v%d" % (x["id"], x["version"], r["version"]),
                            {"cmd": REBASE % t["feature_id"], "hint": "tarefa ainda nao iniciada: nova versao com o requisito atual; iniciada ou concluida: reabra a feature (aisef-feature)"})
            if t.get("reopen_cycle", 1) > f["cycle"]["number"]:
                rep.err("TASK-CYCLE", where, "ciclo %d maior que o da feature (%d)" % (t["reopen_cycle"], f["cycle"]["number"]))
        crit_ids = [c["id"] for c in t["acceptance_criteria"]]
        if len(crit_ids) != len(set(crit_ids)):
            rep.err("ID-DUP", where, "criterios de aceite duplicados")
        own = {x["id"] for x in t["requirements"]["requirement_ids"]}
        for c in t["acceptance_criteria"]:
            for r in c.get("requirement_ids", []):
                if r not in own:
                    rep.err("TASK-CRITERION-REQ", where, "criterio %s cita %s, que a tarefa nao declara" % (c["id"], r))

        ag = agents.get(t["assigned_agent"]["agent_id"])
        if ag is None:
            rep.err("AGENT-UNKNOWN", where, "agente %s nao existe" % t["assigned_agent"]["agent_id"])
        else:
            if ag["contract_version"] != t["assigned_agent"]["agent_contract_version"]:
                rep.err("AGENT-VERSION", where, "tarefa usa o contrato v%d do agente, o atual e v%d" % (t["assigned_agent"]["agent_contract_version"], ag["contract_version"]))
            if t["assigned_agent"].get("role") and t["assigned_agent"]["role"] != ag["role"]:
                rep.err("AGENT-ROLE", where, "papel %s difere do contrato do agente (%s)" % (t["assigned_agent"]["role"], ag["role"]))
            if ag["status"] != "active" and t["state"]["status"] not in ("completed", "cancelled"):
                rep.err("AGENT-INACTIVE", where, "agente %s esta '%s'" % (ag["agent_id"], ag["status"]))
            order = ["dev", "staging", "prod"]
            if order.index(t["permissions"]["environment"]) > order.index(ag["permission_ceiling"]["max_environment"]):
                rep.err("AGENT-ENV", where, "ambiente %s acima do teto do agente (%s)" % (t["permissions"]["environment"], ag["permission_ceiling"]["max_environment"]))
            outside = [r for r in t["permissions"].get("resources", []) if r not in ag["permission_ceiling"]["resources"]]
            if outside:
                rep.err("AGENT-RESOURCE", where, "recursos fora do teto do agente: %s" % outside)
            # 0.5.0: cada path do escopo, classificado como o gateway classifica uma escrita, cabe no teto?
            ceiling = set(ag["permission_ceiling"]["resources"])
            closed = t["state"]["status"] in ("completed", "cancelled")
            for p in list(t["scope"].get("paths_allowed", [])) + list(t["scope"].get("exclusive_files", [])):
                resource, label = gw.write_resource(p, gw_patterns)
                if resource in ("aisef_audit", "aisef_decision") or resource not in ceiling:
                    (rep.warn if closed else rep.err)(
                        "AGENT-PATH-CEILING", where,
                        "%s exige %s (%s), fora do teto do agente %s %s: o gateway negaria a escrita no meio da execucao"
                        % (p, resource, label, ag["agent_id"], sorted(ceiling)))

        vrole = t["validation"].get("validator_role")
        if vrole and vrole != "orchestrator" and vrole not in aisef_catalog.evaluator_roles():
            rep.err("AGENT-ROLE-UNKNOWN", where, "validator_role %s nao e papel avaliador do catalogo" % vrole)
        if t["assigned_agent"].get("role") and t["assigned_agent"]["role"] not in known_roles:
            rep.err("AGENT-ROLE-UNKNOWN", where, "papel %s nao existe no catalogo de agentes" % t["assigned_agent"]["role"])
        if t["validation"]["independent_validator_required"]:
            role = t["assigned_agent"].get("role") or (ag or {}).get("role")
            ok = [v for v in validators if role in v["validation_role"].get("validates", []) and v["agent_id"] != t["assigned_agent"]["agent_id"]]
            if not ok:
                rep.err("VAL-NO-VALIDATOR", where, "validacao independente exigida, mas nenhum agente validador ativo valida o papel '%s'" % role)

        # permissoes x politica x autorizacao
        perms = t["permissions"]
        env = perms["environment"]
        sid = perms.get("scope_authorization_id")
        if policy is not None:
            if perms.get("policy_version") and perms["policy_version"] != policy["policy_version"]:
                rep.warn("PERM-POLICY-VERSION", where, "emitida na politica %s; a atual e %s" % (perms["policy_version"], policy["policy_version"]))
            if env == "prod" and sid:
                rep.err("PERM-PROD-SCOPE", where, "producao nunca por autorizacao de escopo (T2)")
            needs_scope = []
            for r in perms.get("resources", []):
                lv = write_like_levels(policy, r, env)
                if "deny" in lv:
                    rep.err("PERM-DENIED", where, "recurso %s negado em %s" % (r, env))
                if "approve_scope" in lv:
                    needs_scope.append(r)
            if needs_scope and not sid:
                (rep.warn if t["state"]["status"] in ("completed", "cancelled") else rep.err)("PERM-SCOPE-REQUIRED", where, "recursos %s exigem autorizacao de escopo em %s" % (needs_scope, env))
            if sid:
                au = auths.get(sid)
                if au is None or au.get("kind") != "scope":
                    rep.err("AUTH-MISSING", where, "autorizacao de escopo %s nao existe" % sid)
                else:
                    if au["feature_id"] != t["feature_id"]:
                        rep.err("AUTH-FEATURE", where, "%s e da feature %s" % (sid, au["feature_id"]))
                    if au["environment"] != env:
                        rep.err("AUTH-ENV", where, "%s vale em %s, a tarefa em %s" % (sid, au["environment"], env))
                    missing = [r for r in needs_scope if r not in au["resources"]]
                    if missing:
                        rep.err("AUTH-RESOURCE", where, "%s nao cobre %s" % (sid, missing))
                    # A-01: tarefa ja encerrada usou a autorizacao enquanto valia; encerra-la depois e o fluxo normal
                    if au["status"] != "active" and t["state"]["status"] not in ("completed", "cancelled"):
                        rep.err("AUTH-STATUS", where, "%s esta '%s'" % (sid, au["status"]))
                    elif parse_time(au["validity"]["valid_until"]) < now and t["state"]["status"] not in ("completed", "cancelled"):
                        rep.err("AUTH-EXPIRED", where, "%s expirou em %s mas segue 'active'" % (sid, au["validity"]["valid_until"]))
                    if "db_data" in perms.get("resources", []) and perms.get("dataset_classification") != au.get("dataset_classification"):
                        rep.err("AUTH-DATASET", where, "classificacao do dataset difere da autorizacao")

        # estado x relatorio x eventos
        st = t["state"]["status"]
        types = task_types(tid)
        # caminho rapido (FEAT-MAINT, sem validador independente): o orquestrador faz, testa e conclui direto,
        # sem task_started, task_executed nem Execution Report; o task_completed continua obrigatorio
        quick = t.get("feature_id") == MAINT_FEATURE and not t["validation"]["independent_validator_required"]
        if st in STARTED:
            if f is not None and f["approval"]["plan"]["status"] != "approved":
                rep.err("STATE-UNAPPROVED-PLAN", where, "tarefa '%s' com plano da feature nao aprovado" % st)
            if "task_started" not in types and not quick:
                rep.err("STATE-NO-START-EVENT", where, "estado '%s' sem evento task_started" % st)
            for d in graph.get(tid, []):
                if d in tasks and tasks[d]["state"]["status"] != "completed" and not t.get("dependencies", {}).get("parallelizable"):
                    rep.err("STATE-DEP-INCOMPLETE", where, "iniciada com a dependencia %s ainda nao concluida" % d)
        if st in NEEDS_REPORT and not quick:
            rp = [r for r in reports if r["task_id"] == tid]
            if not rp:
                rep.err("STATE-NO-REPORT", where, "estado '%s' sem Execution Report" % st)
            # executor parou com intervencao e a parte bloqueada foi resolvida fora dele (outra tarefa ou
            # correcao do orquestrador): se o validador independente validou depois, o que ficou para tras
            # no relatorio ou no evento do executor e historico (aviso), nao erro
            late = rep.warn if st in ("validated", "completed") and "task_validated" in types else rep.err
            if rp and not any(r["status"] == "executed" for r in rp):
                late("STATE-REPORT-STATUS", where, "estado '%s', mas nenhum relatorio com status 'executed'" % st)
            if "task_executed" not in types:
                late("STATE-NO-EXEC-EVENT", where, "estado '%s' sem evento task_executed" % st)
        if st in ("validated", "completed") and t["validation"]["independent_validator_required"]:
            if "task_validated" not in types:
                rep.err("STATE-NO-VALIDATION", where, "estado '%s' exige validacao independente, sem evento task_validated" % st)
        if st in ("validated", "completed") and (t.get("review") or {}).get("reviewers"):
            import aisef_review
            root = os.path.dirname(project) if os.path.basename(project) == ".aisef" else project
            rv = aisef_review.status(root, t, [r for r in reports if r["task_id"] == t["task_id"]])
            missing = [x["role"] for x in rv["pending"]] + [x["role"] for x in rv["rejected"]]
            if missing:
                rep.err("VAL-REVIEW-MISSING", where, "estado '%s' sem APPROVE dos revisores ativos: %s (aisef_review.py record)"
                        % (st, ", ".join(missing)))
        if st == "completed" and "task_completed" not in types:
            rep.err("STATE-NO-COMPLETE-EVENT", where, "concluida sem evento task_completed")

    _cx.update({k: v for k, v in locals().items() if k != "_cx"})



def rules_relatorios(_cx):
    """Regras: relatorios."""
    a, agents, c, cid, defaults, e, p, r, rep, reports, t, tasks, used, where, x = _cx.get("a"), _cx.get("agents"), _cx.get("c"), _cx.get("cid"), _cx.get("defaults"), _cx.get("e"), _cx.get("p"), _cx.get("r"), _cx.get("rep"), _cx.get("reports"), _cx.get("t"), _cx.get("tasks"), _cx.get("used"), _cx.get("where"), _cx.get("x")
    # Relatorio de avaliacao (validacao/QA/seguranca) usa o mesmo schema do de execucao: e o relatorio de um
    # agente de papel avaliador (contrato do agente, ou agent.role) que NAO e o executor da tarefa.
    def is_eval_report(r):
        t_ = tasks.get(r["task_id"])
        if t_ is None or r["agent"]["agent_id"] == t_["assigned_agent"]["agent_id"]:
            return False
        ag_ = agents.get(r["agent"]["agent_id"])
        return (ag_["role"] if ag_ else r["agent"].get("role")) in aisef_catalog.evaluator_roles()

    for r in reports:
        where = "relatorio " + r["report_id"]
        t = tasks.get(r["task_id"])
        if t is None:
            rep.err("REPORT-TASK", where, "tarefa %s nao existe" % r["task_id"])
            continue
        if r["contract_version"] != t["contract_version"]:
            rep.err("REPORT-VERSION", where, "executou a v%d, o contrato esta na v%d" % (r["contract_version"], t["contract_version"]))
        if r["agent"]["agent_id"] != t["assigned_agent"]["agent_id"] and not is_eval_report(r):
            rep.err("REPORT-AGENT", where, "entregue por %s, mas a tarefa e de %s" % (r["agent"]["agent_id"], t["assigned_agent"]["agent_id"]))
        if r.get("review") and not is_eval_report(r):
            rep.err("REPORT-REVIEW-ROLE", where, "veredito de revisao em relatorio que nao e de avaliador (%s)" % r["agent"]["agent_id"])
        want = {c["id"]: c["required"] for c in t["acceptance_criteria"]}
        got = {c["criterion_id"]: c["required"] for c in r["criteria_results"]}
        for cid in want:
            if cid not in got:
                rep.err("REPORT-CRITERIA-MISSING", where, "criterio %s do contrato sem resultado" % cid)
        for cid in got:
            if cid not in want:
                rep.err("REPORT-CRITERIA-UNKNOWN", where, "resultado para criterio inexistente %s" % cid)
            elif got[cid] != want[cid]:
                rep.err("REPORT-CRITERIA-REQUIRED", where, "criterio %s: 'required' diverge do contrato" % cid)
        eids = {e["id"] for e in r["evidence"]}
        used = {x for c in r["criteria_results"] for x in c["evidence_ids"]} | set(r["tests"].get("evidence_ids", []))
        if used - eids:
            rep.err("REPORT-EVIDENCE-UNKNOWN", where, "evidencias citadas e nao listadas: %s" % sorted(used - eids))
        allowed, forbidden = t["scope"].get("paths_allowed"), t["scope"].get("paths_forbidden", [])
        if allowed is not None:
            for grp in ("created", "modified", "deleted"):
                for fe in r["files"][grp]:
                    p = fe["path"]
                    if not any(fnmatch.fnmatch(p, a) for a in allowed) or any(fnmatch.fnmatch(p, x) for x in forbidden):
                        rep.err("REPORT-FILE-OUT-OF-SCOPE", where, "%s (%s) fora do escopo da tarefa" % (p, grp))
        limit = t["limits"].get("max_fix_attempts")
        if limit is None and defaults:
            limit = defaults["failure_handling"]["max_fix_attempts"]
        if limit is not None and r["attempts"]["fix_attempts_used"] > limit and r["status"] == "executed":
            rep.err("REPORT-ATTEMPTS", where, "%d correcoes usadas, limite %d: devia ter escalado" % (r["attempts"]["fix_attempts_used"], limit))
        sp = t["limits"].get("max_specialist_consultations")
        if sp is None and defaults:
            sp = defaults["failure_handling"]["max_specialist_consultations"]
        if sp is not None and r["attempts"]["specialist_consultations_used"] > sp:
            rep.err("REPORT-CONSULTATIONS", where, "consultas a especialista acima do limite (%d)" % sp)

    _cx.update({k: v for k, v in locals().items() if k != "_cx"})



def rules_sdd_tdd(_cx):
    """Regras: SDD + TDD (fatias, spec e red-green)."""
    c, cycles, f, feats, i, label, r, rep, reports, st, t, tasks, tid, where = _cx.get("c"), _cx.get("cycles"), _cx.get("f"), _cx.get("feats"), _cx.get("i"), _cx.get("label"), _cx.get("r"), _cx.get("rep"), _cx.get("reports"), _cx.get("st"), _cx.get("t"), _cx.get("tasks"), _cx.get("tid"), _cx.get("where")
    for r in reports:
        cycles = (r.get("tdd_evidence") or {}).get("cycles", [])
        where = "relatorio " + r["report_id"]
        for i, c in enumerate(cycles, 1):
            label = "ciclo %d (%s)" % (i, c.get("test", "?"))
            if c["red"]["exit_code"] == 0:
                rep.err("TDD-RED-NOT-FAILING", where, "%s: o teste 'vermelho' passou (exit 0); TDD exige ve-lo falhar antes" % label)
            if c["green"]["exit_code"] != 0:
                rep.err("TDD-GREEN-FAILING", where, "%s: o teste 'verde' falhou (exit %d)" % (label, c["green"]["exit_code"]))
            try:
                out_of_order = parse_time(c["red"]["at"]) >= parse_time(c["green"]["at"])
            except (ValueError, TypeError):
                out_of_order = True  # horario ilegivel ou sem fuso: nao da para provar a ordem
            if out_of_order:
                rep.err("TDD-RED-BEFORE-GREEN", where, "%s: o vermelho (%s) nao veio antes do verde (%s)"
                        % (label, c["red"]["at"], c["green"]["at"]))
    for tid, t in tasks.items():
        where = "tarefa " + tid
        st = t["state"]["status"]
        tdd = (t.get("tests") or {}).get("tdd_required")
        if tdd and st in ("executed", "validated", "completed"):
            mine = [r for r in reports if r["task_id"] == tid and r["agent"]["agent_id"] == t["assigned_agent"]["agent_id"]
                    and r["status"] == "executed"]
            if mine and not any((r.get("tdd_evidence") or {}).get("cycles") for r in mine):
                (rep.warn if st == "completed" else rep.err)(
                    "TDD-EVIDENCE-MISSING", where, "TDD obrigatorio, mas nenhum Execution Report do executor traz tdd_evidence")
        if t.get("kind") == "slice":
            if not any((c.get("verification") or {}).get("method") == "automated_test" for c in t["acceptance_criteria"]):
                rep.err("SLICE-NO-AUTOMATED-TEST", where, "fatia vertical sem nenhum criterio verificado por teste automatizado")
            f = feats.get(t["feature_id"])
            spec = (f or {}).get("spec")
            if f is not None and not spec:
                rep.err("SPEC-REQUIRED", where, "fatia vertical numa feature sem spec (solucao, historias e seams de teste)")
            elif spec:
                unknown = set((t.get("tests") or {}).get("seams", [])) - set(spec.get("test_seams", []))
                if unknown:
                    rep.err("SPEC-SEAM-UNKNOWN", where, "seams fora da spec da feature: %s" % ", ".join(sorted(unknown)))

    _cx.update({k: v for k, v in locals().items() if k != "_cx"})



def rules_autoridade_de_design_arquitetura_detecta(_cx):
    """Regras: autoridade de design (0.6.1) / arquitetura detectada (aisef_detect)."""
    a, approvals, e, fh, high, project, r, rep, rid, schemas_dir, t, tasks, tid, v = _cx.get("a"), _cx.get("approvals"), _cx.get("e"), _cx.get("fh"), _cx.get("high"), _cx.get("project"), _cx.get("r"), _cx.get("rep"), _cx.get("rid"), _cx.get("schemas_dir"), _cx.get("t"), _cx.get("tasks"), _cx.get("tid"), _cx.get("v")
    arch_file = os.path.join(project, "architecture.json")
    if os.path.exists(arch_file):
        try:
            with open(arch_file, encoding="utf-8") as fh:
                arch = json.load(fh)
            try:
                import jsonschema as _js
            except ImportError:
                _js = None
            with open(os.path.join(HERE, "architecture.schema.v0.1.json"), encoding="utf-8") as fh:
                for e in (_js.Draft202012Validator(json.load(fh)).iter_errors(arch) if _js else []):
                    rep.err("ARCH-SCHEMA", "architecture.json", "%s: %s" % ("/".join(map(str, e.path)) or "(raiz)", e.message))
            ok_ = arch.get("approved")
            if ok_:
                a = approvals.get(ok_.get("request_id"))
                if a is None or a.get("status") != "approved" or a.get("request_type") != "architecture_decision":
                    rep.err("ARCH-UNAPPROVED", "architecture.json",
                            "estilo adotado sem pedido architecture_decision aprovado (%s)" % ok_.get("request_id"))
            elif arch.get("styles") or arch.get("recommendations"):
                rep.warn("ARCH-PENDING", "architecture.json",
                         "estilo de arquitetura detectado mas nao adotado: confirme com o usuario e registre como ADR "
                         "(skill aisef-discovery). Recomendacoes abertas: %s"
                         % (", ".join(r["id"] for r in arch.get("recommendations", [])) or "nenhuma"))
            high = [v for v in arch.get("violations", []) if v.get("severity") == "high"]
            if high:
                rep.warn("ARCH-DEPENDENCY", "architecture.json",
                         "%d violacao(oes) da regra de dependencia (ex.: %s:%d importa %s); rode aisef_detect.py deps"
                         % (len(high), high[0]["file"], high[0]["line"], high[0]["import"]))
        except ValueError as exc:
            rep.err("ARCH-SCHEMA", "architecture.json", "JSON invalido: %s" % exc)

    tokens_file = os.path.join(project, "design", "tokens.json")
    tokens = None
    if os.path.exists(tokens_file):
        try:
            with open(tokens_file, encoding="utf-8") as fh:
                tokens = json.load(fh)
            try:
                import jsonschema as _js
            except ImportError:
                _js = None
            schema_p = os.path.join(schemas_dir, "design-tokens.schema.v0.1.json")
            with open(schema_p if os.path.exists(schema_p) else os.path.join(HERE, "design-tokens.schema.v0.1.json"),
                      encoding="utf-8") as fh:
                errs = _js.Draft202012Validator(json.load(fh)).iter_errors(tokens) if _js else []
                for e in errs:
                    rep.err("DESIGN-SCHEMA", "design/tokens.json", "%s: %s" % ("/".join(map(str, e.path)) or "(raiz)", e.message))
        except ValueError as exc:
            rep.err("DESIGN-SCHEMA", "design/tokens.json", "JSON invalido: %s" % exc)
            tokens = None
    if tokens and tokens.get("status") == "approved":
        rid = (tokens.get("approval") or {}).get("request_id")
        a = approvals.get(rid)
        if not rid or a is None or a.get("status") != "approved" or a.get("request_type") != "architecture_decision":
            rep.err("DESIGN-UNAPPROVED", "design/tokens.json",
                    "status 'approved' sem pedido architecture_decision aprovado (%s)" % (rid or "sem request_id"))
    ui_open = [tid for tid, t in tasks.items() if t["state"]["status"] not in ("completed", "cancelled")
               and ("ui" in (t.get("touches") or []) or t["assigned_agent"].get("role") == "frontend")]
    if ui_open and not (tokens and tokens.get("status") == "approved"):
        rep.warn("DESIGN-MISSING", "design/tokens.json",
                 "tarefas de UI abertas (%s) sem autoridade de design aprovada: tipografia, cores e componentes podem "
                 "variar de fatia para fatia (skill aisef-design)" % ", ".join(sorted(ui_open)))

    _cx.update({k: v for k, v in locals().items() if k != "_cx"})



def rules_roteamento_de_modelo(_cx):
    """Regras: roteamento de modelo (execution_profile)."""
    is_eval_report, r, rep, reports, tasks, tid = _cx.get("is_eval_report"), _cx.get("r"), _cx.get("rep"), _cx.get("reports"), _cx.get("tasks"), _cx.get("tid")
    # O validador nunca pode ter nivel menor que o do executor (Model Policy). Compara o relatorio de avaliacao
    # com o do executor da mesma tarefa na tentativa mais recente (ou o ultimo na ordem dos arquivos).
    def newest(rs):
        return max(enumerate(rs), key=lambda ir: ((ir[1]["execution_profile"].get("attempt") or 1), ir[0]))[1]

    for tid in tasks:
        profiled = [r for r in reports if r["task_id"] == tid and r.get("execution_profile")]
        ex = [r for r in profiled if r["agent"]["agent_id"] == tasks[tid]["assigned_agent"]["agent_id"]]
        ev = [r for r in profiled if is_eval_report(r)]
        if ex and ev:
            e_, v_ = newest(ex), newest(ev)
            if v_["execution_profile"]["level"] < e_["execution_profile"]["level"]:
                rep.err("ROUTE-VALIDATOR-WEAKER", "relatorio " + v_["report_id"],
                        "nivel do validador L%d menor que o do executor L%d (relatorio %s)"
                        % (v_["execution_profile"]["level"], e_["execution_profile"]["level"], e_["report_id"]))

    _cx.update({k: v for k, v in locals().items() if k != "_cx"})



def rules_aprovacoes_e_autorizacoes(_cx):
    """Regras: aprovacoes e autorizacoes."""
    a, aid, approvals, au, auths, b, event_from_ref, feats, lv, mcp_trusts, now, policy, project, r, rep, req, rid, rr, sp, tasks, tid, where, x = _cx.get("a"), _cx.get("aid"), _cx.get("approvals"), _cx.get("au"), _cx.get("auths"), _cx.get("b"), _cx.get("event_from_ref"), _cx.get("feats"), _cx.get("lv"), _cx.get("mcp_trusts"), _cx.get("now"), _cx.get("policy"), _cx.get("project"), _cx.get("r"), _cx.get("rep"), _cx.get("req"), _cx.get("rid"), _cx.get("rr"), _cx.get("sp"), _cx.get("tasks"), _cx.get("tid"), _cx.get("where"), _cx.get("x")
    for rid, a in approvals.items():
        where = "aprovacao " + rid
        if a.get("feature_id") and a["feature_id"] not in feats:
            rep.err("APPROVAL-FEATURE", where, "feature %s nao existe" % a["feature_id"])
        if a.get("task_id") and a["task_id"] not in tasks:
            rep.err("APPROVAL-TASK", where, "tarefa %s nao existe" % a["task_id"])
        for tid in a["blocks"]["blocked_task_ids"]:
            if tid not in tasks:
                rep.err("APPROVAL-BLOCKED-TASK", where, "bloqueia a tarefa inexistente %s" % tid)
        req = event_from_ref(a["audit"]["requested_event_ref"])
        if req is None:
            rep.err("APPROVAL-EVENT-REF", where, "requested_event_ref '%s' nao aponta para um evento do log" % a["audit"]["requested_event_ref"])
        else:
            if req["event_type"] != "approval_requested":
                rep.err("APPROVAL-EVENT-TYPE", where, "pedido aponta para evento '%s', esperado approval_requested" % req["event_type"])
            if req.get("feature_id") and req["feature_id"] != a.get("feature_id"):
                rep.err("APPROVAL-EVENT-FEATURE", where, "evento do pedido e de outra feature")
        if a["status"] != "pending" and "decided_event_ref" in a["audit"]:
            dec = event_from_ref(a["audit"]["decided_event_ref"])
            if dec is None:
                rep.err("APPROVAL-EVENT-REF", where, "decided_event_ref '%s' nao aponta para um evento do log" % a["audit"]["decided_event_ref"])
            else:
                if dec["actor"]["type"] != "user" or dec["event_type"] not in DECIDER_EVENTS:
                    rep.err("APPROVAL-DECIDER", where, "decisao aponta para evento '%s' de %s: so o usuario decide" % (dec["event_type"], dec["actor"]["type"]))
                if req is not None and dec["sequence"] <= req["sequence"]:
                    rep.err("APPROVAL-ORDER", where, "decisao registrada antes do pedido")
        if a["status"] == "pending" and parse_time(a["expires_at"]) < now:
            rep.err("APPROVAL-EXPIRED-PENDING", where, "pedido pendente expirou em %s e deveria estar 'expired'" % a["expires_at"])
        rr = a.get("resulting_ref")
        if a["status"] == "approved" and rr and rr["kind"] in ("scope_authorization", "reinforced_approval"):
            au = auths.get(rr["id"])
            if au is None:
                rep.err("APPROVAL-AUTH-MISSING", where, "autorizacao gerada %s nao existe" % rr["id"])
            elif a["request_type"] == "scope_authorization":
                sp = a["scope_proposal"]
                if au.get("kind") != "scope" or au["environment"] != sp["environment"] or set(au["resources"]) != set(sp["resources"]) \
                        or set(au["operations"]) != set(sp["operations"]) or au["validity"]["valid_until"] != sp["valid_until"]:
                    rep.err("APPROVAL-AUTH-MISMATCH", where, "autorizacao %s difere do escopo que o usuario aprovou" % rr["id"])
                if au["feature_id"] != a.get("feature_id"):
                    rep.err("APPROVAL-AUTH-MISMATCH", where, "autorizacao gerada e de outra feature")

    for aid, au in auths.items():
        where = "autorizacao " + aid
        if au["feature_id"] not in feats:
            rep.err("AUTH-FEATURE", where, "feature %s nao existe" % au["feature_id"])
        elif au.get("kind") == "scope" and au["cycle"] > feats[au["feature_id"]]["cycle"]["number"]:
            rep.err("AUTH-CYCLE", where, "ciclo maior que o da feature")
        if au.get("kind") == "scope" and "git_feature_branch" in au["resources"]:  # F-03
            import aisef_git
            gcfg = aisef_project_git_settings(project)
            pats = (au.get("resource_filters") or {}).get("branches") or []
            if not pats:
                rep.err("AUTH-GIT-BRANCH", where, "git_feature_branch sem resource_filters.branches: o escopo nao diria qual branch")
            for b in pats:
                probe = b.replace("*", "x").replace("?", "x")
                if not aisef_git.is_feature_branch(probe, gcfg["branch_prefix"], gcfg["base_branch"]):
                    rep.err("AUTH-GIT-BRANCH", where, "%s nao e branch de feature (prefixo %s, nunca %s nem protegidas)"
                            % (b, gcfg["branch_prefix"], gcfg["base_branch"]))
        if au.get("kind") == "scope":
            if au["status"] == "active" and parse_time(au["validity"]["valid_until"]) < now:
                rep.err("AUTH-EXPIRED", where, "expirou em %s mas segue 'active'" % au["validity"]["valid_until"])
            if au["history"][0]["event"] != "granted":
                rep.err("AUTH-HISTORY", where, "primeiro evento do historico deve ser 'granted'")
            max_days = (policy or {}).get("scope_authorization_schema_ref", {}).get("validity_max_days")
            if max_days is not None:
                days = (parse_time(au["validity"]["valid_until"]) - parse_time(au["validity"]["valid_from"])).total_seconds() / 86400
                if days > max_days + 1e-6:
                    rep.err("AUTH-SCOPE-TOO-LONG", where, "validade de %.1f dias excede o maximo da politica (%d)" % (days, max_days))
            if policy is not None:
                for r in au["resources"]:
                    lv = write_like_levels(policy, r, au["environment"])
                    if "approve_scope" in lv:
                        continue
                    if any(x in lv for x in ("approve_operation", "approve_reinforced", "deny")):
                        rep.err("AUTH-NOT-SCOPABLE", where, "a politica nao admite escopo para %s em %s (exige %s)" % (r, au["environment"], [x for x in lv if x != "allow"]))
                    elif au["status"] == "active":  # encerrada: nada a fazer
                        rep.warn("AUTH-REDUNDANT", where, "%s em %s ja e 'allow' na politica; o escopo nao acrescenta nada" % (r, au["environment"]))
                if au["policy_version"] != policy["policy_version"]:
                    rep.warn("AUTH-POLICY-VERSION", where, "emitida na politica %s; a atual e %s" % (au["policy_version"], policy["policy_version"]))
        else:
            if au["task_id"] not in tasks:
                rep.err("AUTH-TASK", where, "tarefa %s nao existe" % au["task_id"])
            span = (parse_time(au["expires_at"]) - parse_time(au["issued_at"])).total_seconds() / 60
            if span > au["validity_minutes"] + 0.01:
                rep.err("AUTH-REINFORCED-VALIDITY", where, "janela real de %.0f min excede validity_minutes (%d)" % (span, au["validity_minutes"]))
            if au["status"] == "approved" and parse_time(au["expires_at"]) < now:
                rep.err("AUTH-REINFORCED-EXPIRED", where, "aprovada e vencida sem uso: deveria estar 'expired'")

    for aid, au in mcp_trusts.items():  # F-01: confianca em ferramentas MCP, com prazo
        where = "confianca MCP " + aid
        if au["status"] == "active" and parse_time(au["validity"]["valid_until"]) < now:
            rep.warn("AUTH-EXPIRED", where, "venceu em %s; o gateway ja nao a usa (renove com aisef_mcp.py trust)"
                     % au["validity"]["valid_until"])
        if au["history"][0]["event"] != "granted":
            rep.err("AUTH-HISTORY", where, "primeiro evento do historico deve ser 'granted'")
        max_days = (policy or {}).get("scope_authorization_schema_ref", {}).get("validity_max_days") or 7
        days = (parse_time(au["validity"]["valid_until"]) - parse_time(au["validity"]["valid_from"])).total_seconds() / 86400
        if days > max_days + 1e-6:
            rep.err("AUTH-SCOPE-TOO-LONG", where, "validade de %.1f dias excede o maximo da politica (%d); o gateway a ignora"
                    % (days, max_days))

    _cx.update({k: v for k, v in locals().items() if k != "_cx"})
