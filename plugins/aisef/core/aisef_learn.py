#!/usr/bin/env python3
"""AISEF: aprendizado continuo revisado (0.8.1). Licoes do projeto a partir de ERROS rotulados, nunca sem o usuario.

    python -I aisef_learn.py propose --project . [--json]
        agrupa, sem modelo, os sinais do log e dos relatorios desde a ultima proposta: reprovacoes (validador e
        precheck), negacoes do gateway, scope_discovery, correcoes e problemas/riscos dos Execution Reports.
        Grava .aisef/learning/proposals.json. O orquestrador (ou um agente Haiku) redige trigger/acao de cada grupo.
    python -I aisef_learn.py accept --project . --proposal P-1 --trigger "..." --action "..." [--tags a,b] [--scope project]
        DECISAO DO USUARIO (o gateway abre o prompt nativo): vira K-NNN.json ativo, com evidencia (ids de eventos),
        confianca inicial pelo tamanho do grupo e revisao registrada.
    python -I aisef_learn.py update --project .
        recalcula a confianca, em codigo: +0.05 quando uma tarefa que recebeu a licao conclui sem reprovacao,
        -0.10 quando uma tarefa que a recebeu e reprovada, -0.02 por semana sem uso; abaixo de 0.2 a licao e aposentada.
    python -I aisef_learn.py list --project . [--json]

Diferencas deliberadas em relacao ao "instinct" do everything-claude-code (lido no codigo dele): sem daemon, sem hook
por chamada, funciona no Windows, revisao humana obrigatoria antes de valer, decaimento implementado, injecao so na
tarefa relevante (pacote de contexto) e tudo dentro do repositorio (o time herda).
"""
import argparse
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_context as ctx  # noqa: E402
import aisef_project as ap  # noqa: E402
import audit_chain  # noqa: E402

INJECT_MIN = 0.5
RETIRE_BELOW = 0.2
UP, DOWN, DECAY_PER_WEEK = 0.05, 0.10, 0.02
STOP = {"para", "com", "sem", "uma", "que", "nao", "dos", "das", "por", "foi", "tarefa", "reprovada", "executada",
        "validada", "precheck", "validador", "gateway", "the", "and", "relatorio"}


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(d):
    return d.astimezone().isoformat(timespec="seconds")


def _parse(ts):
    try:
        d = datetime.datetime.fromisoformat(ts)
        return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError):
        return None


def kdir(project):
    return os.path.join(ap.aisef_dir(project), "knowledge")


def _log(project):
    return audit_chain.read_log_dir(os.path.join(ap.aisef_dir(project), "audit"))


def _key(text):
    words = [w for w in re.findall(r"[a-z]{4,}", (text or "").lower()) if w not in STOP]
    return " ".join(sorted(set(words))[:4]) or "geral"


def signals(project, since_seq=-1):
    """Erros rotulados desde a sequencia `since_seq`: (tipo, evento ou relatorio, texto, tarefa, papel)."""
    out = []
    tasks = {}
    tdir = os.path.join(ap.aisef_dir(project), "contracts", "tasks")
    for n in os.listdir(tdir) if os.path.isdir(tdir) else []:
        if n.endswith(".json"):
            try:
                t = json.load(open(os.path.join(tdir, n), encoding="utf-8"))
                tasks[t["task_id"]] = t
            except (OSError, ValueError, KeyError):
                pass
    for e in _log(project):
        if e["sequence"] <= since_seq:
            continue
        et, data = e["event_type"], e.get("data") or {}
        role = (tasks.get(e.get("task_id") or "", {}).get("assigned_agent") or {}).get("role")
        if et == "task_rejected":
            text = "; ".join(data.get("precheck") or []) or e["summary"]
            out.append(("rejeicao", e["event_id"], text, e.get("task_id"), role))
        elif et == "tool_used" and data.get("gateway") == "deny":
            out.append(("gateway", e["event_id"], data.get("reason") or e["summary"], e.get("task_id"), data.get("subagent")))
        elif et in ("scope_discovery", "correction"):
            out.append((et, e["event_id"], e["summary"], e.get("task_id"), role))
    rdir = os.path.join(ap.aisef_dir(project), "reports")
    for n in sorted(os.listdir(rdir)) if os.path.isdir(rdir) else []:
        if not n.endswith(".json"):
            continue
        try:
            r = json.load(open(os.path.join(rdir, n), encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for f in (r.get("problems") or []) + (r.get("risks") or []):
            text = f.get("description") if isinstance(f, dict) else str(f)
            if text:
                out.append(("relatorio", r.get("report_id"), text, r.get("task_id"),
                            (r.get("agent") or {}).get("role")))
    return out


def proposals_path(project):
    return os.path.join(ap.aisef_dir(project), "learning", "proposals.json")


def propose(project):
    state_path = proposals_path(project)
    since = -1
    if os.path.exists(state_path):
        since = json.load(open(state_path, encoding="utf-8")).get("through_sequence", -1)
    groups = {}
    for kind, ref, text, tid, role in signals(project, since):
        if any(ctx.find_secrets(x) for x in (text or "",)):
            text = "[omitido: possivel segredo]"
        k = (kind, role or "-", _key(text))
        g = groups.setdefault(k, {"kind": kind, "role": role, "key": k[2], "evidence": [], "tasks": set(), "examples": []})
        g["evidence"].append(ref)
        if tid:
            g["tasks"].add(tid)
        if len(g["examples"]) < 3:
            g["examples"].append((text or "")[:200])
    log = _log(project)
    props = []
    for i, g in enumerate(sorted(groups.values(), key=lambda x: -len(x["evidence"])), 1):
        props.append({"id": "P-%d" % i, "kind": g["kind"], "role": g["role"], "key": g["key"], "count": len(g["evidence"]),
                      "evidence": g["evidence"], "tasks": sorted(g["tasks"]), "examples": g["examples"]})
    doc = {"generated_at": _iso(_now()), "through_sequence": log[-1]["sequence"] if log else -1, "proposals": props}
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    ap.write_json(state_path, doc)
    return doc


def initial_confidence(count):
    return 0.4 if count <= 1 else (0.55 if count == 2 else 0.7)


def accept(project, proposal_id, trigger, action, tags=(), scope="project"):
    path = proposals_path(project)
    doc = json.load(open(path, encoding="utf-8"))
    p = next((x for x in doc["proposals"] if x["id"] == proposal_id), None)
    if p is None:
        raise SystemExit("proposta %s nao existe em %s" % (proposal_id, path))
    for label, text in (("trigger", trigger), ("action", action)):
        if ctx.find_secrets(text):
            raise SystemExit("recusado: %s parece conter segredo" % label)
    ev_ids = [x for x in p["evidence"] if re.fullmatch(r"E\d+", str(x))] or p["evidence"]
    entry = {"schema_version": "0.1.0", "id": ctx.next_knowledge_id(ap.aisef_dir(project)),
             "summary": ("Licao: " + trigger)[:200], "detail": "Quando %s: %s" % (trigger, action),
             "source": {"kind": "task", "ref": p["tasks"][0]} if p["tasks"] else {"kind": "decision", "ref": proposal_id},
             "tags": sorted({t.strip() for t in tags if t.strip()} | ({p["role"]} if p["role"] else set())),
             "created_by": "user", "created_at": _iso(_now()), "status": "active",
             "lesson": {"trigger": trigger, "action": action, "scope": scope, "evidence_events": ev_ids,
                        "confidence": initial_confidence(p["count"]), "applied": 0, "succeeded": 0, "failed": 0,
                        "updated_at": _iso(_now()),
                        "review": {"approved_by": "user", "approved_at": _iso(_now()), "proposal": proposal_id}}}
    problems = ap.validate(entry, "knowledge-entry.schema.v0.1.json")
    if problems:
        raise SystemExit("licao invalida, nada gravado:\n - " + "\n - ".join(problems))
    ap.write_json(os.path.join(kdir(project), entry["id"] + ".json"), entry)
    doc["proposals"] = [x for x in doc["proposals"] if x["id"] != proposal_id]
    ap.write_json(path, doc)
    ap.append(project, {"event_type": "evidence_recorded", "actor": {"type": "user", "id": "user"},
                        "summary": "Licao %s aprovada pelo usuario (%s)" % (entry["id"], trigger[:80])})
    return entry


def lessons(project):
    return [e for e in ctx.load_knowledge(ap.aisef_dir(project)) if e.get("lesson")]


def update(project, now=None):
    """Recalcula a confianca de cada licao ativa a partir do log (deterministico). Devolve as mudancas."""
    now = now or _now()
    log = _log(project)
    delegated = {}  # licao -> tarefas que a receberam (dispatch grava em data.lessons do delegation)
    for e in log:
        if e["event_type"] == "delegation":
            for k in (e.get("data") or {}).get("lessons", []):
                delegated.setdefault(k, set()).add(e["task_id"])
    final = {}
    for e in log:
        if e.get("task_id") and e["event_type"] in ("task_completed", "task_rejected"):
            final.setdefault(e["task_id"], []).append(e["event_type"])
    changes = []
    for entry in lessons(project):
        L = entry["lesson"]
        if entry["status"] != "active":
            continue
        before = L["confidence"]
        got = delegated.get(entry["id"], set())
        succeeded = sum(1 for t in got if "task_completed" in final.get(t, []) and "task_rejected" not in final.get(t, []))
        failed = sum(1 for t in got if "task_rejected" in final.get(t, []))
        c = before + UP * (succeeded - L.get("succeeded", 0)) - DOWN * (failed - L.get("failed", 0))
        last = _parse(L.get("updated_at")) or now
        if not got or (succeeded == L.get("succeeded", 0) and failed == L.get("failed", 0)):
            c -= DECAY_PER_WEEK * max(0.0, (now - last).total_seconds() / (7 * 86400))
        c = round(max(0.0, min(0.95, c)), 3)
        L.update(applied=len(got), succeeded=succeeded, failed=failed, confidence=c, updated_at=_iso(now))
        if c < RETIRE_BELOW:
            entry["status"] = "retired"
        if c != before or entry["status"] == "retired":
            ap.write_json(os.path.join(kdir(project), entry["id"] + ".json"), entry)
            changes.append({"id": entry["id"], "from": before, "to": c, "status": entry["status"]})
    return changes


def injectable(entry):
    """So licao aprovada, ativa e com confianca suficiente entra no pacote de contexto."""
    L = entry.get("lesson")
    if not L:
        return entry.get("status", "active") == "active"
    return entry.get("status") == "active" and L.get("confidence", 0) >= INJECT_MIN and (L.get("review") or {}).get("approved_by") == "user"


def main(argv=None):
    a_ = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a_.add_argument("command", choices=["propose", "accept", "update", "list"])
    a_.add_argument("--project", default=".")
    a_.add_argument("--proposal")
    a_.add_argument("--trigger")
    a_.add_argument("--action")
    a_.add_argument("--tags", default="")
    a_.add_argument("--scope", default="project", choices=["slice", "feature", "project"])
    a_.add_argument("--json", action="store_true")
    a = a_.parse_args(argv)
    project = os.path.abspath(a.project)
    if a.command == "propose":
        doc = propose(project)
        if a.json:
            print(json.dumps(doc, ensure_ascii=False, indent=2))
        else:
            print("%d proposta(s) de licao (de erros rotulados desde a ultima rodada):" % len(doc["proposals"]))
            for p in doc["proposals"]:
                print("  %s [%s, %s] x%d: %s" % (p["id"], p["kind"], p["role"] or "-", p["count"], p["examples"][0] if p["examples"] else ""))
        return 0
    if a.command == "accept":
        if not (a.proposal and a.trigger and a.action):
            a_.error("--proposal, --trigger e --action sao obrigatorios")
        e = accept(project, a.proposal, a.trigger, a.action, a.tags.split(","), a.scope)
        print("licao %s ativa (confianca %.2f)" % (e["id"], e["lesson"]["confidence"]))
        return 0
    if a.command == "update":
        ch = update(project)
        print(json.dumps(ch, ensure_ascii=False, indent=2) if a.json else
              "\n".join("%s: %.2f -> %.2f (%s)" % (c["id"], c["from"], c["to"], c["status"]) for c in ch) or "nenhuma mudanca")
        return 0
    rows = [{"id": e["id"], "trigger": e["lesson"]["trigger"], "confidence": e["lesson"]["confidence"],
             "status": e["status"], "applied": e["lesson"].get("applied", 0)} for e in lessons(project)]
    print(json.dumps(rows, ensure_ascii=False, indent=2) if a.json else
          "\n".join("%s %.2f %s [%s] %s" % (r["id"], r["confidence"], r["status"], r["applied"], r["trigger"]) for r in rows) or "nenhuma licao")
    return 0


if __name__ == "__main__":
    sys.exit(main())
