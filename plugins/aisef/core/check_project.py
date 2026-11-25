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
    PROJECT-EMPTY   a pasta nao tem documento AISEF nem log (--project errado nao passa como "0 erros")
    ID-DUP / ID-FILE   id duplicado; nome do arquivo diferente do id
    REQ-HISTORY     historico do requisito inconsistente com a versao atual
    PLAN-*          plano de tarefas x contratos de tarefa (existencia, versao, feature, dependencias, papel)
    RTM-*           rastreabilidade: requisito x tarefa x criterio, nos dois sentidos
    FEAT-*          criterios de aceite da feature, referencias arquiteturais, estado x tarefas
    TRIAGE-*        caminho da triagem (aisef_triage.py): TRIAGE-OVERRIDDEN-DOWN quando o caminho efetivo fica
                    abaixo do calculado; TRIAGE-LEAN-SHAPE quando o lean nao e uma fatia com TDD
    TASK-*          referencias da tarefa (requisitos, criterios, ciclo)
    DEP-*           dependencias inexistentes, ciclos, entre features
    PAR-*           paralelismo: conflito de arquivos entre tarefas simultaneas
    AGENT-*         agente da tarefa (existe, versao, papel, ativo, ambiente, recursos); AGENT-ROLE-UNKNOWN: papel fora
                    do catalogo de agentes (core/agents/catalog.v0.1.json); AGENT-PATH-CEILING:
                    path do escopo que exige recurso fora do teto do agente (mesma classificacao do gateway)
    ARCH-*          .aisef/architecture.json (aisef_detect): schema, estilo adotado aprovado como decisao
                    arquitetural, estilo pendente de decisao, violacoes da regra de dependencia
    CONFIG-GIT      opcoes git do config.json (branch_per_feature, delete_branch_after_merge, branch_prefix...)
    CONFIG-GRAPHIFY opcoes do Graphify no config.json (enabled, backend none|ollama|auto, paths e graph relativos)
    CONFIG-PROFILE  perfil de cerimonia no config.json (solo, team, regulated)
    CONFIG-PARALLEL modo de paralelismo no config.json (paths, worktree)
    TELEMETRY-CHAIN telemetria (.aisef/telemetry, F-05) com a cadeia de hash quebrada (aviso: nao e o log assinado)
    BUDGET-RAISED   Feature Contract com budget acima do limite do projeto (L-01: o contrato so baixa)
    PROFILE-*       perfil regulated: PROFILE-QUICK (sem caminho rapido), PROFILE-TDD (toda tarefa executora com TDD),
                    PROFILE-BLUEPRINT (feature com tarefa de risco alto tem blueprint)
    VAL-*           validacao independente (existe validador, validador diferente do executor); VAL-REVIEW-MISSING: validada sem o
                    APPROVE de todos os revisores ativos de review.reviewers
    PERM-* / AUTH-* permissoes da tarefa x politica e autorizacoes (existe, escopo, ambiente, validade)
                    AUTH-GIT-BRANCH: escopo de push (git_feature_branch) sem branches ou com branch que nao e de feature
    BP-*            blueprint x feature (versao, requisitos, componentes, endpoints, entidades, decisoes aprovadas, cobertura)
    STATE-*         estado da tarefa/feature x relatorios e eventos de auditoria
    REPORT-*        relatorio x contrato (versao, criterios, evidencias, arquivos dentro do escopo, tentativas)
    ROUTE-*         roteamento de modelo: nivel do validador (execution_profile) nunca menor que o do executor
                    (relatorio de avaliacao = relatorio de agente avaliador que nao e o executor da tarefa)
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
import aisef_catalog  # noqa: E402
import audit_chain  # noqa: E402
import check_policy_consistency as pol  # noqa: E402

sys.path.insert(1, os.path.join(os.path.dirname(HERE), "hooks"))
import gateway as gw  # noqa: E402  (mesma classificacao de caminhos do Execution Gateway)

gw_patterns = gw.load_patterns()

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
MAINT_FEATURE = "FEAT-MAINT"  # feature permanente do caminho rapido (aisef_new.MAINT_FEATURE)
DECIDER_EVENTS = {"approval_granted", "approval_rejected", "decision_recorded", "feature_accepted", "authorization_granted"}


def parse_time(s):
    return datetime.datetime.fromisoformat(s)


# F-07: como corrigir cada regra. `cmd` e um comando pronto (CORE = pasta core do plugin); `hint` e o passo a fazer.
# Regras sem entrada aqui saem sem correcao sugerida. Nas regras de versao, o comando e por feature.
REBASE = "python -I <CORE>/aisef_new.py rebase-req --project . --feature %s"
FIX_HINTS = {
    "VAL-NO-VALIDATOR": {"cmd": "python -I <CORE>/aisef_project.py agents --project . --roles validator",
                         "hint": "cria o draft do validator; a ativacao e decisao do usuario (agents --activate)"},
    "AGENT-PATH-CEILING": {"hint": "divida a tarefa ou troque o assigned_agent por um papel com esse recurso no teto"},
    "DESIGN-MISSING": {"hint": "rode a skill aisef-design para propor e aprovar a autoridade de design"},
    "STATE-UNAPPROVED-PLAN": {"hint": "leve o plan_approval da feature ao usuario (aisef-approve) antes de executar"},
    "STATE-PLAN-NO-EVENT": {"hint": "registre a decisao pelo aisef-approve (decide), que grava o approval_granted do usuario"},
    "STATE-NO-START-EVENT": {"hint": "o agente da tarefa registra: aisef_project.py append --type task_started --actor agent --actor-id <papel> --task <T>"},
    "STATE-NO-REPORT": {"hint": "o executor grava o Execution Report em reports/RPT-*.json; sem ele, a tarefa volta a in_progress"},
    "STATE-NO-VALIDATION": {"cmd": "python -I <CORE>/aisef_project.py validate-wave --project .",
                            "hint": "valide antes de concluir (validador independente)"},
    "STATE-NO-COMPLETE-EVENT": {"hint": "registre: aisef_project.py append --type task_completed --task <T> (orquestrador)"},
    "STATE-DEP-INCOMPLETE": {"hint": "pause a tarefa (task_paused) ate a dependencia concluir"},
    "STATE-FEATURE-TASKS": {"hint": "conclua as tarefas pendentes ou volte o estado da feature"},
    "STATE-CLOSED-NO-ACCEPT": {"hint": "o aceite e do usuario: pedido feature_acceptance pelo aisef-approve"},
    "TRIAGE-OVERRIDDEN-DOWN": {"hint": "suba o caminho no contrato (path) ate o calculado; descer nao e permitido"},
    "CONFIG-PROFILE": {"hint": "use solo, team ou regulated em config.json -> profile"},
    "TDD-EVIDENCE-UNBACKED": {"hint": "rode o teste de novo pelo shell (o hook grava o resultado) e declare no ciclo o mesmo comando e o horario da execucao"},
}


class Report:
    def __init__(self):
        self.findings = []

    def add(self, severity, rule, where, message, fix=None):
        f = {"severity": severity, "rule": rule, "where": where, "message": message}
        fix = fix or FIX_HINTS.get(rule)
        if fix:
            f["fix"] = dict(fix)
        self.findings.append(f)

    def err(self, rule, where, message, fix=None):
        self.add("error", rule, where, message, fix)

    def warn(self, rule, where, message, fix=None):
        self.add("warning", rule, where, message, fix)

    def fixes(self, core=None):
        """Comandos de correcao sem repeticao, na ordem dos achados (com <CORE> trocado pelo caminho real)."""
        out = []
        for f in self.findings:
            c = (f.get("fix") or {}).get("cmd")
            if c:
                c = c.replace("<CORE>", core) if core else c
                if c not in out:
                    out.append(c)
        return out

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


def aisef_project_git_settings(aisef_root):
    """Opcoes git do config.json (prefixo e branch base), com os padroes. aisef_root e a pasta .aisef."""
    import aisef_project
    try:
        with open(os.path.join(aisef_root, "config.json"), encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError):
        cfg = {}
    return aisef_project.git_settings(cfg if isinstance(cfg, dict) else {})[0]


def write_like_levels(policy, resource, env):
    out = []
    for action, val in policy["matrix"].get(resource, {}).items():
        if action.startswith("$") or action in READ_ACTIONS:
            continue
        lvl = val.get(env) if isinstance(val, dict) else val
        if lvl and lvl != "not_applicable_via_git":
            out.append(lvl)
    return out


def resolve_project(project):
    """Aceita a raiz do repositorio (como os demais comandos, `--project .`) ou a propria pasta .aisef."""
    inner = os.path.join(project, ".aisef")
    if os.path.isfile(os.path.join(inner, "config.json")) and not os.path.isfile(os.path.join(project, "config.json")):
        return inner
    return project


def apply_effective_states(docs, log):
    """Estado efetivo da tarefa = contrato combinado com o ultimo evento de ciclo de vida do log, a mesma regra do
    `next` (aisef_next.effective_state). Sem isso, um contrato que ficou em 'ready' depois do task_completed era
    checado como tarefa aberta (teto de paths, autorizacao de escopo, dependencias incompletas)."""
    import aisef_next as nx
    last = {}
    for e in log:
        if e.get("task_id") and e.get("event_type") in nx.EVENT_STATE:
            last[e["task_id"]] = nx.EVENT_STATE[e["event_type"]]
    for _, t in docs["tasks"]:
        st = t.get("state") or {}
        if t.get("task_id") in last and "status" in st:
            st["status"] = nx.effective_state(st["status"], last[t["task_id"]])


RULE_GROUPS = [
    ("check_rules_1", "rules_ids"),  # ids
    ("check_rules_1", "rules_requisitos_e_features"),  # requisitos e features
    ("check_rules_1", "rules_blueprints"),  # blueprints
    ("check_rules_1", "rules_dependencias_e_paralelismo"),  # dependencias e paralelismo
    ("check_rules_1", "rules_config"),  # config (0.5.0)
    ("check_rules_2", "rules_tarefas"),  # tarefas
    ("check_rules_2", "rules_relatorios"),  # relatorios
    ("check_rules_2", "rules_sdd_tdd"),  # SDD + TDD (fatias, spec e red-green)
    ("check_rules_4", "rules_tdd_no_log"),  # E-01: evidencia de TDD cruzada com o log assinado
    ("check_rules_2", "rules_autoridade_de_design_arquitetura_detecta"),  # autoridade de design (0.6.1) / arquitetura detectada (aisef_detect)
    ("check_rules_2", "rules_roteamento_de_modelo"),  # roteamento de modelo (execution_profile)
    ("check_rules_2", "rules_aprovacoes_e_autorizacoes"),  # aprovacoes e autorizacoes
    ("check_rules_3", "rules_telemetria"),  # telemetria (F-05)
    ("check_rules_3", "rules_log"),  # log
    ("check_rules_3", "rules_politica_x_schemas"),  # politica x schemas
    ("check_rules_3", "rules_memoria_de_projeto"),  # memoria de projeto (0.4.0)
]


def check(project, schemas_dir=HERE, policy_path=None, defaults_path=None, now=None):
    """Roda os grupos de regras de RULE_GROUPS em ordem (H-01: as regras ficam em check_rules_*.py)."""
    rep = Report()
    now = parse_time(now) if isinstance(now, str) else (now or datetime.datetime.now(datetime.timezone.utc))
    project = resolve_project(project)
    docs, log = load_project(project, schemas_dir, rep)
    if not log and not any(docs.values()) and not rep.findings:
        rep.err("PROJECT-EMPTY", project, "nenhum documento AISEF nem log de auditoria: confira o --project (raiz do repo ou .aisef)")
    apply_effective_states(docs, log)
    policy = json.load(open(policy_path, encoding="utf-8")) if policy_path else None
    defaults = json.load(open(defaults_path, encoding="utf-8")) if defaults_path else None

    _cx = dict(locals())
    import importlib
    for mod, func in RULE_GROUPS:
        getattr(importlib.import_module(mod), func)(_cx)
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
    ap.add_argument("--fix", action="store_true", help="lista no fim os comandos de correcao sugeridos (F-07)")
    a = ap.parse_args(argv[1:])
    rep = check(a.project, a.schemas, a.policy, a.defaults, a.now)
    for f in sorted(rep.findings, key=lambda x: (x["severity"] != "error", x["rule"])):
        print("[%s] %s | %s | %s" % ("ERRO " if f["severity"] == "error" else "AVISO", f["rule"], f["where"], f["message"]))
        if f.get("fix"):
            fx = f["fix"]
            print("        correcao: %s" % "; ".join(x for x in (fx.get("cmd", "").replace("<CORE>", HERE), fx.get("hint")) if x))
    print("%d erro(s), %d aviso(s)" % (rep.count("error"), rep.count("warning")))
    if a.fix and rep.fixes():
        print("\nComandos de correcao (rode na ordem e confira de novo):")
        for c in rep.fixes(HERE):
            print("  " + c)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(rep.findings, fh, ensure_ascii=False, indent=2)
    return 1 if rep.count("error") or (a.strict and rep.count("warning")) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
