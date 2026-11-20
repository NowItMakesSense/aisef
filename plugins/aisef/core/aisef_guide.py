#!/usr/bin/env python3
"""AISEF next: guia de fases (SDD + TDD), revisao de ferramentas, atualizacao do grafo e texto das acoes

H-01 (0.14): saiu de aisef_next.py sem mudar o codigo; aisef_next reexporta tudo."""
import copy
import datetime
import glob
import json
import os
import re
import subprocess
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_project as ap  # noqa: E402
import audit_chain  # noqa: E402


ACCEPTED_FEATURE_STATES = ("closed",)


def _parse(ts):
    try:
        return datetime.datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


def _cmd(script, *args):
    return 'python -I "%s" %s' % (os.path.join(HERE, script), " ".join(args))


# Guia de fases (SDD + TDD). Cada passo cita a skill que o executa. Os nomes do Matt Pocock (plugin
# mattpocock-skills) sao as skills que o modelo pode chamar; to-spec/to-tickets/implement-spec sao so do usuario
# (disable-model-invocation) e por isso o AISEF faz o mesmo papel nas fases Spec e Fatias da aisef-feature.
MATT_EQUIVALENTS = {"/grill-me": "fase Grill (skill grilling)", "/grill-with-docs": "fase Grill + domain-modeling",
                    "/to-spec": "fase Spec da aisef-feature", "/to-tickets": "fase Fatias da aisef-feature",
                    "/implement-spec": "modo continuo (next) com o agente implementer + tdd",
                    "/implement": "modo continuo (next) com o agente implementer + tdd", "/tdd": "skill tdd no implementer",
                    "/code-review": "revisao da feature antes do aceite"}
STEPS = {
    "discovery": ["aisef-discovery: investigar o projeto e gravar .aisef/discovery.md (investigar antes de perguntar)",
                  "aisef-tooling: sugerir skills, plugins e MCPs a partir do discovery"],
    "specify": ["Grill: entrevistar o usuario ate fechar cada ramo da ideia (skill grilling; vocabulario no GLOSSARY.md com domain-modeling)",
                "Spec: aisef-feature fase Spec (solucao, historias, decisoes, seams de teste confirmados com o usuario)",
                "Fatias: aisef-feature fase Fatias (fatias verticais com blocking edges; aisef_new.py feature)",
                "Aprovar o plano: aisef-approve"],
    "approve_plan": ["aisef-approve: apresentar o plano pendente (requisitos, fatias, seams, riscos) e registrar a decisao do usuario"],
    "execute": ["modo continuo: dispatch da onda (implementer com tdd, vermelho antes do verde) -> validador independente -> complete"],
    "review": ["code-review da feature inteira (skill code-review: padroes + aderencia a spec), correcoes como novas tentativas",
               "relatorio final planejado x executado e pedido feature_acceptance (aisef_project.py request)"],
    "decide": ["aisef-approve: levar ao usuario as decisoes pendentes listadas em await_decision"],
    "done": ["Nada pendente. Nova ideia? Comece pelo Grill (skill grilling) e siga Spec -> Fatias."],
}


def tooling_review_due(cfg, approvals, log):
    """Revisao periodica das skills/plugins/MCPs (aisef-tooling secao 8): devida depois de N features aceitas
    (config tooling.review_every, padrao 1) desde a ultima revisao registrada (evidence_recorded com
    data.kind = tooling_review). 0 desliga."""
    every = (cfg.get("tooling") or {}).get("review_every", 1)
    if not isinstance(every, int) or isinstance(every, bool) or every <= 0:
        return False
    reviews = [_parse(e["timestamp"]) for e in log if e["event_type"] == "evidence_recorded"
               and (e.get("data") or {}).get("kind") == "tooling_review"]
    last = max((r for r in reviews if r), default=None)
    accepted = 0
    for a in approvals:
        if a.get("request_type") != "feature_acceptance" or a.get("status") != "approved" or a.get("feature_id") == "FEAT-MAINT":
            continue
        when = _parse((a.get("decision") or {}).get("decided_at") or a.get("created_at"))
        if last is None or (when and when > last):
            accepted += 1
    return accepted >= every


def project_phase(project, feats, tasks, approvals, actions):
    """Em que fase o projeto esta e qual o proximo passo, com a skill certa (inclusive antes da execucao)."""
    kinds = {a["kind"] for a in actions}
    real = {fid: f for fid, f in feats.items() if fid != "FEAT-MAINT"}
    if not os.path.exists(os.path.join(ap.aisef_dir(project), "discovery.md")):
        phase = "discovery"
    elif kinds & {"dispatch", "validate", "complete", "wait", "create_branch"}:
        phase = "execute"
    elif "feature_acceptance" in kinds:
        phase = "review"
    elif any(a.get("request_type") == "plan_approval" for a in actions if a["kind"] == "await_decision"):
        phase = "approve_plan"
    elif "await_decision" in kinds:
        phase = "decide"
    elif not real or all((f.get("state") or {}).get("status") in ACCEPTED_FEATURE_STATES + ("cancelled",) for f in real.values()):
        phase = "specify" if not real else "done"
    else:
        phase = "done"
    compact = phase in ("approve_plan", "review", "decide", "done") and "wait" not in kinds
    return {"phase": phase, "steps": STEPS[phase], "matt_equivalents": MATT_EQUIVALENTS,
            "compact_hint": ("Marco de fase sem agente em voo: bom momento para /compact (o estado esta no disco e o "
                             "AISEF o reinjeta depois)") if compact else None}

GRAPH_MILESTONES = ("approve_plan", "review", "decide", "done")


def graph_refresh(project, cfg, phase, actions):
    """Sugere regenerar o grafo do Graphify (sem modelo) quando ele falta ou esta velho, nos marcos: antes de despachar
    uma onda (o pack le o grafo) e nos marcos de fase (plano, revisao, decisao, fim). None quando nao ha o que fazer."""
    try:
        st = ap.graphify_status(project, cfg)
    except Exception:
        return None
    if not st["enabled"] or (st["exists"] and not st["stale"]):
        return None
    dispatching = any(a["kind"] == "dispatch" for a in actions)
    if not dispatching and phase not in GRAPH_MILESTONES:
        return None
    why = "o grafo ainda nao foi gerado" if not st["exists"] else "%s mudou depois do grafo" % st["newer_source"]
    return {"reason": why, "before_dispatch": dispatching,
            "cmd": "GRAPHIFY_BACKEND=%s python -m graphify update ." % st["backend"]}


def format_next(res):
    lines = ["Proximas acoes%s:" % (" (%s)" % res["feature"] if res["feature"] else "")]
    for a in res["actions"]:
        k = a["kind"]
        if k == "dispatch":
            lines.append("- dispatch (onda %d, %d tarefa(s) em paralelo)" % (a["wave"], len(a["tasks"])))
            for t in a["tasks"]:
                lines.append("    %s [%s] %s (tentativa %d)" % (t["task_id"], t["agent_id"], t["title"], t["attempt"]))
                lines.append("      rota: %s" % t["route_cmd"])
                lines.append("      pack: %s" % t["pack_cmd"])
        elif k in ("validate", "complete"):
            lines.append("- %s %s: %s" % (k, a["task_id"], a.get("route_cmd") or a.get("append_cmd")))
        elif k == "wait":
            lines.append("- wait: em andamento %s" % ", ".join(a["task_ids"]))
        elif k == "await_decision":
            ref = a.get("request_id") or a.get("event_id") or a.get("report_id") or ""
            lines.append("- await_decision [%s] %s %s%s" % (a["source"], ref, a.get("title") or "",
                                                           " (bloqueia %s)" % ", ".join(a["task_ids"]) if a.get("task_ids") else ""))
        elif k == "requirement_changed":
            lines.append("- requirement_changed %s (%s): %s" % (", ".join(a["task_ids"]), ", ".join(a["requirements"]),
                                                               a["hint"] if a["started"] else a["cmd"]))
        elif k == "feature_acceptance":
            lines.append("- feature_acceptance %s: %s" % (a["feature_id"], a["hint"]))
        elif k == "create_branch":
            lines.append("- create_branch %s: %s" % (a["feature_id"], a["command"]))
        elif k == "delete_merged_branch":
            lines.append("- delete_merged_branch %s (%s)" % (a["branch"], a["requires"]))
            for o in a["operations"]:
                lines.append("    %s: %s%s" % (o["scope"], o["command"],
                                               " [pedido %s: %s]" % (o["request"]["request_id"], o["request"]["status"]) if o["request"] else ""))
        else:
            lines.append("- " + k)
    if res["deferred"]:
        lines.append("Fora da onda atual:")
        for d in res["deferred"]:
            lines.append("  %s: %s" % (d["task"], d["reason"]))
    if res.get("wave_error"):
        lines.append("ERRO nas ondas: " + res["wave_error"])
    for w in res.get("warnings", []):
        lines.append("AVISO " + w)
    lines.append("stop_reason: %s%s" % (res["stop_reason"], " (%s)" % res["stop_detail"] if res["stop_detail"] else ""))
    if res.get("guide"):
        lines.append("Fase: %s. Proximo passo:" % res["guide"]["phase"])
        lines += ["  %d. %s" % (i, s_) for i, s_ in enumerate(res["guide"]["steps"], 1)]
        if res["guide"].get("tooling_review_due"):
            lines.append("Revisao das ferramentas devida (aisef-tooling, secao 8): /skill-doctor, custo e uso das skills")
        if res["guide"].get("compact_hint"):
            lines.append(res["guide"]["compact_hint"])
        gr = res["guide"].get("graph_refresh")
        if gr:
            lines.append("Grafo do Graphify: %s. Regenere%s (sem modelo): %s" % (
                gr["reason"], " antes do dispatch" if gr["before_dispatch"] else "", gr["cmd"]))
    return "\n".join(lines)
