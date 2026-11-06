#!/usr/bin/env python3
"""AISEF: validador de consistencia entre documentos (RASCUNHO v0.1).

Os schemas garantem que cada documento e valido SOZINHO. Este validador garante que os documentos
sao coerentes ENTRE SI: o que um aponta existe, bate em versao e respeita a politica.

Entradas (estrutura do projeto):
    contracts/features/*.json  contracts/tasks/*.json  contracts/agents/*.json
    approvals/*.json  authorizations/*.json  reports/*.json
    audit/log.jsonl
Opcionais:
    --policy permission-policy.json   (ativa as regras de permissao e a checagem politica x schemas)
    --defaults orchestration-defaults.json   (limite padrao de tentativas)
    --now 2026-11-05T21:00:00-03:00  (para checar validades; padrao: agora)

Regras (codigo -> o que verifica):
    SCHEMA          documento invalido no proprio schema (ficou fora das demais checagens)
    ID-DUP / ID-FILE   id duplicado; nome do arquivo diferente do id
    REQ-HISTORY     historico do requisito inconsistente com a versao atual
    PLAN-*          plano de tarefas x contratos de tarefa (existencia, versao, feature, dependencias, papel)
    RTM-*           rastreabilidade: requisito x tarefa x criterio, nos dois sentidos
    FEAT-*          criterios de aceite da feature, referencias arquiteturais, estado x tarefas
    TASK-*          referencias da tarefa (requisitos, criterios, ciclo)
    DEP-*           dependencias inexistentes, ciclos, entre features
    PAR-*           paralelismo: conflito de arquivos entre tarefas simultaneas
    AGENT-*         agente da tarefa (existe, versao, papel, ativo, ambiente, recursos)
    VAL-*           validacao independente (existe validador, validador diferente do executor)
    PERM-* / AUTH-* permissoes da tarefa x politica e autorizacoes (existe, escopo, ambiente, validade)
    BP-*            blueprint x feature (versao, requisitos, componentes, endpoints, entidades, decisoes aprovadas, cobertura)
    STATE-*         estado da tarefa/feature x relatorios e eventos de auditoria
    REPORT-*        relatorio x contrato (versao, criterios, evidencias, arquivos dentro do escopo, tentativas)
    APPROVAL-*      aprovacoes x tarefas, autorizacoes geradas, eventos e validade
    LOG-*           log x contratos (ids, versoes, ordem do tempo, atores)
    POLICY-SCHEMA   politica x schemas (via check_policy_consistency)

Uso:
    python3 -I check_project.py --project DIR [--schemas DIR] [--policy F] [--defaults F] [--now ISO] [--json F] [--strict]
Saida: codigo 1 se houver erro (ou aviso com --strict).
"""
import argparse
import datetime
import fnmatch
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import audit_chain  # noqa: E402
import check_policy_consistency as pol  # noqa: E402

KINDS = {
    "features": ("contracts/features/*.json", "feature-contract.schema.v0.1.json", "feature_id"),
    "tasks": ("contracts/tasks/*.json", "task-contract.schema.v0.1.json", "task_id"),
    "blueprints": ("blueprints/*.json", "engineering-blueprint.schema.v0.1.json", "blueprint_id"),
    "agents": ("contracts/agents/*.json", "agent-contract.schema.v0.1.json", "agent_id"),
    "approvals": ("approvals/*.json", "approval-request.schema.v0.1.json", "request_id"),
    "authorizations": ("authorizations/*.json", "authorization.schema.v0.1.json", None),
    "reports": ("reports/*.json", "execution-report.schema.v0.1.json", "report_id"),
}
READ_ACTIONS = {"read", "read_content", "read_rows", "status_log_diff"}
STARTED = {"in_progress", "executed", "validated", "completed"}
NEEDS_REPORT = {"executed", "validated", "completed"}
DECIDER_EVENTS = {"approval_granted", "approval_rejected", "decision_recorded", "feature_accepted", "authorization_granted"}


def parse_time(s):
    return datetime.datetime.fromisoformat(s)


class Report:
    def __init__(self):
        self.findings = []

    def add(self, severity, rule, where, message):
        self.findings.append({"severity": severity, "rule": rule, "where": where, "message": message})

    def err(self, rule, where, message):
        self.add("error", rule, where, message)

    def warn(self, rule, where, message):
        self.add("warning", rule, where, message)

    def codes(self):
        return {f["rule"] for f in self.findings}

    def count(self, severity):
        return sum(1 for f in self.findings if f["severity"] == severity)


def load_project(project, schemas_dir, rep):
    try:
        import jsonschema
    except ImportError:
        rep.err("SCHEMA", "(validador)", "jsonschema ausente: documentos nao puderam ser validados")
        jsonschema = None
    docs = {k: [] for k in KINDS}
    for kind, (pattern, schema_file, idf) in KINDS.items():
        validator = None
        sp = os.path.join(schemas_dir, schema_file)
        if jsonschema and os.path.exists(sp):
            with open(sp, encoding="utf-8") as fh:
                validator = jsonschema.Draft202012Validator(json.load(fh))
        for path in sorted(glob.glob(os.path.join(project, pattern))):
            rel = os.path.relpath(path, project)
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, ValueError) as exc:
                rep.err("SCHEMA", rel, "JSON ilegivel: %s" % exc)
                continue
            if validator:
                problems = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
                if problems:
                    p = problems[0]
                    rep.err("SCHEMA", rel, "%s: %s" % ("/".join(map(str, p.path)) or "(raiz)", p.message[:140]))
                    continue
            docs[kind].append((rel, data))
    log = audit_chain.read_log_dir(os.path.join(project, "audit"))  # inclui segmentos arquivados
    return docs, log


def doc_id(kind, d):
    if kind == "authorizations":
        return d.get("authorization_id") or d.get("approval_id")
    return d[KINDS[kind][2]]


def overlaps(a, b):
    if a == b or fnmatch.fnmatch(a, b) or fnmatch.fnmatch(b, a):
        return True
    pa, pb = a.rstrip("*").rstrip("/"), b.rstrip("*").rstrip("/")
    return bool(pa) and bool(pb) and (pa.startswith(pb + "/") or pb.startswith(pa + "/") or pa == pb)


def write_like_levels(policy, resource, env):
    out = []
    for action, val in policy["matrix"].get(resource, {}).items():
        if action.startswith("$") or action in READ_ACTIONS:
            continue
        lvl = val.get(env) if isinstance(val, dict) else val
        if lvl and lvl != "not_applicable_via_git":
            out.append(lvl)
    return out


def check(project, schemas_dir=HERE, policy_path=None, defaults_path=None, now=None):
    rep = Report()
    now = parse_time(now) if isinstance(now, str) else (now or datetime.datetime.now(datetime.timezone.utc))
    docs, log = load_project(project, schemas_dir, rep)
    policy = json.load(open(policy_path, encoding="utf-8")) if policy_path else None
    defaults = json.load(open(defaults_path, encoding="utf-8")) if defaults_path else None

    # ------------------------------------------------------------------ ids
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
    approvals = {i: d for i, (_, d) in by["approvals"].items()}
    auths = {i: d for i, (_, d) in by["authorizations"].items()}
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

    # ------------------------------------------------------------------ requisitos e features
    arch_decisions = {}
    for a in approvals.values():
        rr = a.get("resulting_ref")
        if a["status"] == "approved" and rr and rr["kind"] == "architectural_decision":
            arch_decisions[(rr["id"], rr.get("version", 1))] = a

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
                rep.err("PLAN-VERSION", where, "%s: plano espera v%d, contrato esta em v%d" % (tid, item["contract_version"], t["contract_version"]))
            if t["feature_contract_version"] != f["contract_version"]:
                rep.err("PLAN-FEATURE-VERSION", where, "%s foi emitida para a v%d do Feature Contract; a atual e v%d" % (tid, t["feature_contract_version"], f["contract_version"]))
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
                    rep.err("RTM-TASK-NOT-LINKED", where, "%s: a tarefa %s nao declara este requisito (nesta versao)" % (rid, tid))
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

    # ------------------------------------------------------------------ blueprints
    for bid, (_, b) in by["blueprints"].items():
        where = "blueprint " + bid
        f = feats.get(b["feature_id"])
        if f is None:
            rep.err("BP-FEATURE", where, "feature %s nao existe" % b["feature_id"])
            continue
        if b["feature_contract_version"] != f["contract_version"] and b["state"]["status"] != "superseded":
            rep.err("BP-FEATURE-VERSION", where, "baseado na v%d do Feature Contract; a atual e v%d" % (b["feature_contract_version"], f["contract_version"]))
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
            if not any(x.get("primary_key") for x in e["fields"]):
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

    # ------------------------------------------------------------------ dependencias e paralelismo
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
            elif any(overlaps(x, y) for x in pa for y in pb):
                rep.warn("PAR-PATH-OVERLAP", "tarefas %s/%s" % (a, b), "tarefas paralelas com caminhos permitidos que se sobrepoem")

    # ------------------------------------------------------------------ tarefas
    validators = [a for a in agents.values() if a["role"] == "validator" and a["status"] == "active"]
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
                    rep.err("TASK-REQ-VERSION", where, "%s na v%d, requisito atual v%d" % (x["id"], x["version"], r["version"]))
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
                rep.err("PERM-SCOPE-REQUIRED", where, "recursos %s exigem autorizacao de escopo em %s" % (needs_scope, env))
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
                    if au["status"] != "active":
                        rep.err("AUTH-STATUS", where, "%s esta '%s'" % (sid, au["status"]))
                    elif parse_time(au["validity"]["valid_until"]) < now and t["state"]["status"] not in ("completed", "cancelled"):
                        rep.err("AUTH-EXPIRED", where, "%s expirou em %s mas segue 'active'" % (sid, au["validity"]["valid_until"]))
                    if "db_data" in perms.get("resources", []) and perms.get("dataset_classification") != au.get("dataset_classification"):
                        rep.err("AUTH-DATASET", where, "classificacao do dataset difere da autorizacao")

        # estado x relatorio x eventos
        st = t["state"]["status"]
        types = task_types(tid)
        if st in STARTED:
            if f is not None and f["approval"]["plan"]["status"] != "approved":
                rep.err("STATE-UNAPPROVED-PLAN", where, "tarefa '%s' com plano da feature nao aprovado" % st)
            if "task_started" not in types:
                rep.err("STATE-NO-START-EVENT", where, "estado '%s' sem evento task_started" % st)
            for d in graph.get(tid, []):
                if d in tasks and tasks[d]["state"]["status"] != "completed" and not t.get("dependencies", {}).get("parallelizable"):
                    rep.err("STATE-DEP-INCOMPLETE", where, "iniciada com a dependencia %s ainda nao concluida" % d)
        if st in NEEDS_REPORT:
            rp = [r for r in reports if r["task_id"] == tid]
            if not rp:
                rep.err("STATE-NO-REPORT", where, "estado '%s' sem Execution Report" % st)
            elif not any(r["status"] == "executed" for r in rp):
                rep.err("STATE-REPORT-STATUS", where, "estado '%s', mas nenhum relatorio com status 'executed'" % st)
            if "task_executed" not in types:
                rep.err("STATE-NO-EXEC-EVENT", where, "estado '%s' sem evento task_executed" % st)
        if st in ("validated", "completed") and t["validation"]["independent_validator_required"]:
            if "task_validated" not in types:
                rep.err("STATE-NO-VALIDATION", where, "estado '%s' exige validacao independente, sem evento task_validated" % st)
        if st == "completed" and "task_completed" not in types:
            rep.err("STATE-NO-COMPLETE-EVENT", where, "concluida sem evento task_completed")

    # ------------------------------------------------------------------ relatorios
    for r in reports:
        where = "relatorio " + r["report_id"]
        t = tasks.get(r["task_id"])
        if t is None:
            rep.err("REPORT-TASK", where, "tarefa %s nao existe" % r["task_id"])
            continue
        if r["contract_version"] != t["contract_version"]:
            rep.err("REPORT-VERSION", where, "executou a v%d, o contrato esta na v%d" % (r["contract_version"], t["contract_version"]))
        if r["agent"]["agent_id"] != t["assigned_agent"]["agent_id"]:
            rep.err("REPORT-AGENT", where, "entregue por %s, mas a tarefa e de %s" % (r["agent"]["agent_id"], t["assigned_agent"]["agent_id"]))
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

    # ------------------------------------------------------------------ aprovacoes e autorizacoes
    for rid, a in approvals.items():
        where = "aprovacao " + rid
        if a["feature_id"] not in feats:
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
            if req.get("feature_id") and req["feature_id"] != a["feature_id"]:
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
                if au["feature_id"] != a["feature_id"]:
                    rep.err("APPROVAL-AUTH-MISMATCH", where, "autorizacao gerada e de outra feature")

    for aid, au in auths.items():
        where = "autorizacao " + aid
        if au["feature_id"] not in feats:
            rep.err("AUTH-FEATURE", where, "feature %s nao existe" % au["feature_id"])
        elif au.get("kind") == "scope" and au["cycle"] > feats[au["feature_id"]]["cycle"]["number"]:
            rep.err("AUTH-CYCLE", where, "ciclo maior que o da feature")
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
                    else:
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

    # ------------------------------------------------------------------ log
    last = None
    projects = {a["project_id"] for a in approvals.values()}
    for e in log:
        where = "evento %d (%s)" % (e["sequence"], e["event_id"])
        t = parse_time(e["timestamp"])
        if last is not None and t < last:
            rep.err("LOG-TIME-ORDER", where, "timestamp anterior ao do evento anterior")
        last = t
        if e.get("feature_id") and e["feature_id"] not in feats:
            rep.err("LOG-UNKNOWN-FEATURE", where, "feature %s nao existe" % e["feature_id"])
        if e.get("task_id") and e["task_id"] not in tasks:
            rep.err("LOG-UNKNOWN-TASK", where, "tarefa %s nao existe" % e["task_id"])
        if e["actor"]["type"] in ("agent", "validator") and e["actor"]["id"] not in agents:
            rep.err("LOG-UNKNOWN-AGENT", where, "agente %s nao existe" % e["actor"]["id"])
        if e["actor"]["type"] == "validator" and e["actor"]["id"] in agents and agents[e["actor"]["id"]]["role"] != "validator":
            rep.err("LOG-VALIDATOR-ROLE", where, "ator 'validator' com agente de papel %s" % agents[e["actor"]["id"]]["role"])
        tk = tasks.get(e.get("task_id"))
        if tk and e["event_type"] in ("task_started", "task_executed") and e["actor"]["id"] != tk["assigned_agent"]["agent_id"]:
            rep.err("LOG-TASK-ACTOR", where, "%s por %s, mas a tarefa e de %s" % (e["event_type"], e["actor"]["id"], tk["assigned_agent"]["agent_id"]))
        if tk and e["event_type"] == "task_validated" and e["actor"]["id"] == tk["assigned_agent"]["agent_id"]:
            rep.err("VAL-SELF-ATTEST", where, "o executor validou a propria entrega")
        sub = e.get("subject")
        if sub:
            pool = {"feature_contract": feats, "task_contract": tasks, "agent_contract": agents}.get(sub["kind"])
            if pool is not None:
                cur = pool.get(sub["id"])
                if cur is None:
                    rep.err("LOG-SUBJECT", where, "%s %s nao existe" % (sub["kind"], sub["id"]))
                elif sub.get("version", 1) > cur["contract_version"]:
                    rep.err("LOG-SUBJECT", where, "%s %s v%d nao existe (atual v%d)" % (sub["kind"], sub["id"], sub["version"], cur["contract_version"]))
        if e.get("project_id") and projects and e["project_id"] not in projects:
            rep.warn("LOG-PROJECT", where, "projeto %s sem aprovacoes correspondentes" % e["project_id"])

    # ------------------------------------------------------------------ politica x schemas
    if policy is not None:
        def sch(name):
            with open(os.path.join(schemas_dir, name), encoding="utf-8") as fh:
                return json.load(fh)
        for c in pol.check(policy, sch("authorization.schema.v0.1.json"), sch("approval-request.schema.v0.1.json")):
            rep.err("POLICY-SCHEMA", "politica", c)
    else:
        rep.warn("POLICY-SKIPPED", "(validador)", "politica nao fornecida: regras PERM/AUTH-NOT-SCOPABLE e POLICY-SCHEMA puladas")
    return rep


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True)
    ap.add_argument("--schemas", default=HERE)
    ap.add_argument("--policy")
    ap.add_argument("--defaults")
    ap.add_argument("--now")
    ap.add_argument("--json")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args(argv[1:])
    rep = check(a.project, a.schemas, a.policy, a.defaults, a.now)
    for f in sorted(rep.findings, key=lambda x: (x["severity"] != "error", x["rule"])):
        print("[%s] %s | %s | %s" % ("ERRO " if f["severity"] == "error" else "AVISO", f["rule"], f["where"], f["message"]))
    print("%d erro(s), %d aviso(s)" % (rep.count("error"), rep.count("warning")))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(rep.findings, fh, ensure_ascii=False, indent=2)
    return 1 if rep.count("error") or (a.strict and rep.count("warning")) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
