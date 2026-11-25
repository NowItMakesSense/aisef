#!/usr/bin/env python3
"""AISEF: estado do projeto alvo em <repo>/.aisef (v0.1).

O plugin guarda codigo, schemas e politica; o projeto guarda so dados. Este modulo cria a estrutura,
anexa eventos ao log de auditoria e verifica a integridade.

Chaves e head ficam FORA do projeto (ADR 0005: o head nao pode ficar no mesmo armazenamento
do log, e agentes nunca tocam a chave privada):
    ~/.aisef/keys/<project_id>/audit-key-1.pem   chave PRIVADA do Audit Signer
    ~/.aisef/heads/<project_id>.json             head assinado de referencia
No projeto ficam a chave PUBLICA (.aisef/keys/) e uma copia do head (.aisef/audit/head.json) para o painel.
Sem a biblioteca cryptography, o init recusa (0.13, D5) e diz como instalar; projetos antigos sem assinatura
continuam lendo com cadeia de hash (aviso no verify).

Uso:
    python3 -I aisef_project.py init   --project REPO --project-id ID [--name N] [--environment dev|staging|prod]
                                       [--profile solo|team|regulated]   (padrao solo, L-04)
    python3 -I aisef_project.py append --project REPO --type EVENT_TYPE --summary TEXTO
                                       [--actor TIPO] [--actor-id ID] [--feature F] [--task T] [--data JSON]
    python3 -I aisef_project.py decide --project REPO --request APR-NNN --choice approve|reject|request_changes|select_option
                                       [--option OPT-X] [--note TEXTO] [--ack impact_read,rollback_read,diff_reviewed]
                                       [--authorization rascunho.json]
    python3 -I aisef_project.py agents --project REPO [--activate] [--roles backend,qa]
        (sem --activate: cria os drafts dos papeis que se aplicam ao projeto pelo catalogo, ou os de --roles)
    python3 -I aisef_project.py verify-loop --project REPO [--task T-010]
        (aisef_verify: build, tipos, lint, testes por stack, segredos no diff e resumo; PASS/FAIL; --task grava a evidencia)
    python3 -I aisef_project.py practices --project REPO [--apply]
        (boas praticas aplicaveis ao projeto: common + linguagens + estilo de arquitetura; --apply grava em .claude/rules/aisef/)
    python3 -I aisef_project.py detect --project REPO
        (aisef_detect: grava .aisef/architecture.json, registra no log e cria os drafts dos papeis da stack detectada)
    python3 -I aisef_project.py waves --project REPO [--feature FEAT-x] [--json]
    python3 -I aisef_project.py next --project REPO [--feature FEAT-x] [--json]
    python3 -I aisef_project.py dispatch --project REPO [--feature FEAT-x] [--dry-run]   (onda: prompts + delegation)
    python3 -I aisef_project.py validate-wave --project REPO [--feature FEAT-x] [--dry-run]   (um validador por onda)
    python3 -I aisef_project.py precheck --project REPO --task T-x [--json]   (checagem deterministica, sem modelo)
    python3 -I aisef_project.py request --project REPO --file rascunho.json
    python3 -I aisef_project.py verify --project REPO
    python3 -I aisef_project.py status --project REPO
"""


import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# H-01 (0.14): o codigo esta dividido por responsabilidade; esta fachada reexporta tudo (quem faz
# `import aisef_project as ap` continua igual) e guarda a CLI.
from aisef_base import *  # noqa: E402,F401,F403
from aisef_audit_log import *  # noqa: E402,F401,F403
from aisef_agents import *  # noqa: E402,F401,F403
from aisef_requests import *  # noqa: E402,F401,F403
from aisef_waves import *  # noqa: E402,F401,F403
from aisef_base import _ED25519_PKCS8_PREFIX, _LazySerialization, _load_private_key, _plugin_version  # noqa: E402,F401
from aisef_audit_log import _anchor, _rotate_if_large, _write_event  # noqa: E402,F401
from aisef_waves import _find_cycle, _literal_prefix, _norm_path, _task_paths  # noqa: E402,F401
from aisef_base import HAS_CRYPTO  # noqa: E402,F401


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["init", "append", "decide", "agents", "settings", "rotate-key", "anchor",
                                        "verify", "status", "waves", "next", "request", "dispatch", "validate-wave",
                                        "precheck", "mode", "metrics", "detect", "practices", "verify-loop"])
    ap.add_argument("--since", help="metrics: so eventos e pedidos a partir desta data (ISO 8601)")
    ap.add_argument("--no-check", action="store_true", help="metrics: nao roda o aisef-check")
    ap.add_argument("--set", choices=["ask", "exec"], help="mode: troca o modo da sessao (decisao do usuario)")
    ap.add_argument("--dry-run", action="store_true", help="dispatch/validate-wave: mostra sem registrar nada no log")
    ap.add_argument("--json", action="store_true", help="waves/next: saida em JSON")
    ap.add_argument("--file", help="request: rascunho JSON do pedido (status pending)")
    ap.add_argument("--apply", action="store_true", help="settings: grava as regras em .claude/settings.json; "
                                                         "practices: grava as boas praticas em .claude/rules/aisef/")
    ap.add_argument("--project", default=os.getcwd())
    ap.add_argument("--project-id")
    ap.add_argument("--name")
    ap.add_argument("--environment", default="dev", choices=["dev", "staging", "prod"])
    ap.add_argument("--profile", default="solo", choices=list(PROFILES))
    ap.add_argument("--type")
    ap.add_argument("--summary")
    ap.add_argument("--actor", default="orchestrator", choices=["user", "orchestrator", "agent", "validator", "system"])
    ap.add_argument("--actor-id", default="aisef")
    ap.add_argument("--feature")
    ap.add_argument("--task")
    ap.add_argument("--data")
    ap.add_argument("--corrects", help="append de 'correction': id do evento corrigido (o original nunca muda)")
    ap.add_argument("--request")
    ap.add_argument("--choice", choices=sorted(CHOICE_STATUS))
    ap.add_argument("--option")
    ap.add_argument("--note")
    ap.add_argument("--ack", default="", help="impact_read,rollback_read,diff_reviewed")
    ap.add_argument("--authorization", help="rascunho JSON da autorizacao gerada (escopo ou reforcada)")
    ap.add_argument("--activate", action="store_true", help="agents: ativa os Agent Contracts em draft (decisao do usuario)")
    ap.add_argument("--adopt", default="", help="detect: estilos adotados (ids separados por virgula), com --request de "
                                                "architecture_decision ja aprovado pelo usuario")
    ap.add_argument("--roles", default="", help="agents: lista separada por virgula (padrao: todos)")
    a = ap.parse_args(argv)
    project = os.path.abspath(a.project)
    import aisef_git
    project = aisef_git.aisef_root(project)  # L-02a: dentro de um worktree, vale o .aisef principal

    if a.command == "init":
        if not a.project_id:
            ap.error("--project-id e obrigatorio")
        signed = init(project, a.project_id, a.name, a.environment, a.profile)
        print("AISEF iniciado em %s (log %s)" % (aisef_dir(project), "assinado com Ed25519" if signed else "SEM assinatura: instale cryptography"))
        return 0
    if a.command == "append":
        if not (a.type and a.summary):
            ap.error("--type e --summary sao obrigatorios")
        partial = {"event_type": a.type, "actor": {"type": a.actor, "id": a.actor_id}, "summary": a.summary}
        if a.feature:
            partial["feature_id"] = a.feature
        if a.task:
            partial["task_id"] = a.task
        if a.data:
            partial["data"] = json.loads(a.data)
        problem = check_append_actor(project, a.type, a.actor, a.actor_id, a.task, a.corrects)
        if problem:
            ap.error(problem)
        if a.corrects:
            partial["corrects_event_id"] = a.corrects
        ev = append(project, partial)
        print("evento %s (sequencia %d) registrado" % (ev["event_id"], ev["sequence"]))
        if a.type == "feature_accepted":  # E-03: marco com carimbo de tempo RFC 3161 (se audit.tsa_url)
            import aisef_anchor
            res = aisef_anchor.milestone(project, "aceite %s" % (a.feature or ""))
            if res:
                print(("carimbo de tempo: %s" % res["gen_time"]) if res["ok"] else "AVISO: " + res["warning"])
        return 0
    if a.command == "settings":
        path, added = native_settings(project, a.apply)
        total = len(added["ask"]) + len(added["deny"]) + len(added["settings"])
        if not total:
            print("%s ja tem todas as regras do AISEF" % path)
        else:
            print("%s %d regra(s) em %s:" % ("gravadas" if a.apply else "faltam (use --apply para gravar)", total, path))
            for k in ("ask", "deny", "settings"):
                for r in added[k]:
                    print("  %s %s" % (k, r))
        return 0
    if a.command == "waves":
        try:
            res = compute_waves(load_tasks(project), a.feature)
        except WaveError as e:
            print(json.dumps({"error": str(e), "ids": e.ids}, ensure_ascii=False) if a.json else "ERRO: %s" % e)
            return 1
        print(json.dumps(res, ensure_ascii=False, indent=2) if a.json else format_waves(res))
        return 0
    if a.command == "request":
        if not a.file:
            ap.error("--file e obrigatorio (rascunho do pedido, fora de .aisef/)")
        req, ev = request(project, a.file)
        print("%s pendente gravado (approval_requested: %s, sequencia %d)" % (req["request_id"], ev["event_id"], ev["sequence"]))
        return 0
    if a.command == "next":
        import aisef_next
        res = aisef_next.compute_next(project, a.feature)
        print(json.dumps(res, ensure_ascii=False, indent=2) if a.json else aisef_next.format_next(res))
        return 0
    if a.command == "metrics":
        import aisef_metrics
        res = aisef_metrics.compute_metrics(project, a.feature, a.since, run_check=not a.no_check)
        print(json.dumps(res, ensure_ascii=False, indent=2) if a.json else aisef_metrics.format_metrics(res))
        return 0
    if a.command == "mode":
        path = os.path.join(aisef_dir(project), "session", "mode.json")
        if a.set:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            write_json(path, {"mode": a.set, "set_at": now_iso(), "set_by": "user"})
            append(project, {"event_type": "evidence_recorded", "actor": {"type": "user", "id": "user"},
                             "summary": "Modo da sessao: %s" % a.set, "data": {"kind": "session_mode", "mode": a.set}})
        cur = "exec"
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                cur = json.load(fh).get("mode", "exec")
        print("modo: %s%s" % (cur, " (so leitura: nada e editado nem executado; saia com /aisef:modo exec)" if cur == "ask" else ""))
        return 0
    if a.command in ("dispatch", "validate-wave", "precheck"):
        import aisef_dispatch as dsp
        if a.command == "precheck":
            if not a.task:
                ap.error("--task e obrigatorio")
            problems = dsp.precheck(project, a.task)
            print(json.dumps({"task_id": a.task, "problems": problems}, ensure_ascii=False, indent=2) if a.json
                  else ("%s: precheck ok" % a.task if not problems else "%s: precheck falhou\n - %s" % (a.task, "\n - ".join(problems))))
            return 1 if problems else 0
        fn = dsp.dispatch_wave if a.command == "dispatch" else dsp.validation_wave
        res = fn(project, a.feature, dry_run=a.dry_run)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    if a.command == "rotate-key":
        print("nova chave: %s" % rotate_key(project))
        return 0
    if a.command == "anchor":
        a_ = anchor(project)
        print("ancora gravada: sequencia %d em %s" % (a_["sequence"], anchors_path(load_config(project)["project_id"])))
        return 0
    if a.command == "verify-loop":
        import aisef_verify
        return aisef_verify.main(["--project", project] + (["--task", a.task] if a.task else []))
    if a.command == "practices":
        import aisef_practices
        if a.apply:
            done, kept = aisef_practices.apply(project)
            print("gravados: %s" % (", ".join(done) or "nada mudou"))
            if kept:
                print("mantidos (modificados no projeto): %s" % ", ".join(kept))
            if done:
                append(project, {"event_type": "evidence_recorded", "actor": {"type": "system", "id": "aisef_practices"},
                                 "summary": "Boas praticas instaladas em .claude/rules/aisef/: %d arquivo(s)" % len(done)})
        else:
            for r in aisef_practices.plan(project):
                print("%-24s %s" % (r["state"], r["target"]))
            print("(--apply grava em .claude/rules/aisef/; o gateway pede aprovacao)")
        return 0
    if a.command == "detect":
        import aisef_detect
        if a.adopt:
            adopted = adopt_styles(project, [x for x in a.adopt.split(",") if x], a.request)
            print("estilo adotado: %s (%s)" % (", ".join(adopted["styles"]), adopted["request_id"]))
            created = write_agent_drafts(project)
            print("drafts de Agent Contract criados para o estilo: %s" % (", ".join(created) or "nenhum novo"))
            return 0
        doc = aisef_detect.detect(project)
        aisef_detect.write(project, doc)
        created = write_agent_drafts(project)
        append(project, {"event_type": "evidence_recorded", "actor": {"type": "system", "id": "aisef_detect"},
                         "summary": "Deteccao de stack e arquitetura: %s; estilos: %s" % (
                             ", ".join(s["id"] for s in doc["stacks"]) or "nenhuma",
                             ", ".join("%s %.2f" % (s["id"], s["confidence"]) for s in doc["styles"]) or "nenhum")})
        print(aisef_detect.summary(doc))
        print("drafts de Agent Contract criados para a stack: %s (ativar e decisao do usuario: agents --activate --roles ...)"
              % (", ".join(created) or "nenhum novo"))
        return 0
    if a.command == "agents":
        roles = [x for x in a.roles.split(",") if x] or None
        if a.activate:
            done = activate_agents(project, roles)
            print("ativados: %s" % (", ".join(done) or "nenhum (ja ativos ou inexistentes)"))
        else:
            created = write_agent_drafts(project, roles)
            print("drafts criados: %s" % (", ".join(created) or "nenhum (ja existiam)"))
        return 0
    if a.command == "decide":
        if not (a.request and a.choice):
            ap.error("--request e --choice sao obrigatorios")
        req = decide(project, a.request, a.choice, a.option, a.note,
                     [x for x in a.ack.split(",") if x], a.authorization)
        print("%s -> %s%s" % (a.request, req["status"],
                              " (gerou %s)" % req["resulting_ref"]["id"] if req.get("resulting_ref") else ""))
        return 0
    errors, warnings = verify(project)
    for w in warnings:
        print("aviso:", w)
    for e in errors:
        print("ERRO:", e)
    if a.command == "status":
        cfg = load_config(project)
        print(json.dumps({"project_id": cfg["project_id"], "environment": cfg["environment"],
                          "audit_ok": not errors}, ensure_ascii=False))
    else:
        print("integridade ok" if not errors else "%d erro(s) de integridade" % len(errors))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
