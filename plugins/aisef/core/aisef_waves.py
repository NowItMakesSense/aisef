#!/usr/bin/env python3

"""AISEF: ondas de execucao: conflito de caminhos entre tarefas, dependencias e ciclos.

H-01 (0.14): parte do antigo aisef_project.py. Importe pela fachada `aisef_project`, que reexporta tudo."""

import base64  # noqa: F401
import datetime  # noqa: F401
import fnmatch  # noqa: F401
import glob  # noqa: F401
import json  # noqa: F401
import os
import re  # noqa: F401
import sys
import time  # noqa: F401

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_base  # noqa: E402
import aisef_catalog  # noqa: E402,F401
import audit_chain  # noqa: E402,F401

from aisef_base import *  # noqa: E402,F401,F403
from aisef_base import _ED25519_PKCS8_PREFIX, _LazySerialization, _load_private_key, _plugin_version  # noqa: E402,F401
from aisef_audit_log import *  # noqa: E402,F401,F403
from aisef_audit_log import _anchor, _rotate_if_large, _write_event  # noqa: E402,F401
from aisef_agents import *  # noqa: E402,F401,F403
from aisef_requests import *  # noqa: E402,F401,F403
try:
    from aisef_base import Ed25519PrivateKey, audit_signing  # noqa: E402,F401
except ImportError:
    pass

# ----------------------------------------------------------------------------- ondas de execucao
SATISFIED_STATES = ("completed", "validated")
WAVE_WILDCARDS = "*?[{"


class WaveError(Exception):
    """Grafo de dependencias invalido (ciclo ou dependencia inexistente); `ids` lista as tarefas envolvidas."""

    def __init__(self, message, ids):
        Exception.__init__(self, message)
        self.ids = list(ids)


def _norm_path(p):
    p = p.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.rstrip("/") if len(p) > 1 else p


def _literal_prefix(p):
    for i, ch in enumerate(p):
        if ch in WAVE_WILDCARDS:
            return p[:i], True
    return p, False


def paths_overlap(a, b):
    """Heuristica CONSERVADORA de sobreposicao entre dois padroes de arquivo (na duvida, conflito).

    1. Prefixo literal = trecho antes do primeiro curinga (* ? [ {). Prefixo vazio (ex.: '**') conflita com tudo.
    2. Dois caminhos literais (sem curinga): conflitam se iguais ou se um e diretorio do outro.
    3. Se ao menos um tem curinga: conflita quando um prefixo literal e prefixo (de texto) do outro,
       o que cobre 'compartilham o prefixo antes do primeiro curinga'; e tambem quando o padrao casa (fnmatch)
       com o caminho literal do outro."""
    a, b = _norm_path(a), _norm_path(b)
    pa, wa = _literal_prefix(a)
    pb, wb = _literal_prefix(b)
    if not wa and not wb:
        return a == b or b.startswith(a + "/") or a.startswith(b + "/")
    if not pa or not pb or pa.startswith(pb) or pb.startswith(pa):
        return True
    if not wb and fnmatch.fnmatchcase(b, a):
        return True
    if not wa and fnmatch.fnmatchcase(a, b):
        return True
    return False


def _task_paths(t):
    sc = t.get("scope", {})
    return list(sc.get("paths_allowed", [])) + list(sc.get("exclusive_files", []))


def tasks_conflict(t1, t2):
    """Motivo do conflito entre duas tarefas da mesma onda, ou None. Sem paths declarados = conflito (desconhecido)."""
    p1, p2 = _task_paths(t1), _task_paths(t2)
    if not p1 or not p2:
        return "sem paths declarados (escopo desconhecido)"
    for x in p1:
        for y in p2:
            if paths_overlap(x, y):
                return "paths sobrepostos (%s x %s)" % (x, y)
    shared = set(t1.get("dependencies", {}).get("shared_resources", [])) & set(t2.get("dependencies", {}).get("shared_resources", []))
    if shared:
        return "recurso compartilhado (%s)" % ", ".join(sorted(shared))
    return None


def _find_cycle(deps, start_ids):
    """Devolve a lista de ids de um ciclo alcancavel a partir de start_ids, ou None."""
    color, stack = {}, []

    def visit(n):
        color[n] = 1
        stack.append(n)
        for d in deps.get(n, []):
            if d not in deps:
                continue
            if color.get(d) == 1:
                return stack[stack.index(d):] + [d]
            if d not in color:
                c = visit(d)
                if c:
                    return c
        stack.pop()
        color[n] = 2
        return None

    for n in sorted(start_ids):
        if n not in color:
            c = visit(n)
            if c:
                return c
    return None


def compute_waves(tasks, feature=None):
    """Planeja ondas de execucao em paralelo a partir de Task Contracts (dicts).

    Retorna {"waves": [{"wave": n, "tasks": [...]}], "deferred": [{"task", "reason", "wave"}],
             "excluded": [{"task", "status", "reason"}], "satisfied": [ids]}.
    - concluidas (completed/validated) contam como satisfeitas; so 'ready' e executavel; draft, in_progress,
      executed, blocked, rejected e cancelled ficam em `excluded` e quem depende delas fica em `deferred`
      sem onda (wave = None) ate o estado mudar;
    - onda N+1 simula a conclusao da onda N; na mesma onda nao entram tarefas com paths sobrepostos
      (ver paths_overlap) nem mais de uma tarefa quando alguma tem parallelizable == false;
    - `deferred` com wave = N: tarefa elegivel na onda N, adiada para a seguinte (motivo no item);
    - ciclo ou dependencia inexistente levanta WaveError (com os ids)."""
    by_id = {}
    for t in tasks:
        by_id[t["task_id"]] = t
    cand = [t for t in tasks if feature is None or t.get("feature_id") == feature]
    cand_ids = {t["task_id"] for t in cand}
    deps = {tid: list(t.get("dependencies", {}).get("depends_on", [])) for tid, t in by_id.items()}

    # alcance: candidatas e tudo de que dependem (inclusive em outras features)
    reach, todo = set(), sorted(cand_ids)
    while todo:
        n = todo.pop()
        if n in reach:
            continue
        reach.add(n)
        todo.extend(d for d in deps.get(n, []) if d in by_id)
    missing = sorted({(n, d) for n in reach for d in deps.get(n, []) if d not in by_id})
    if missing:
        raise WaveError("dependencia inexistente: " + "; ".join("%s depende de %s" % m for m in missing),
                        sorted({x for m in missing for x in m}))
    cyc = _find_cycle({n: deps[n] for n in reach}, cand_ids)
    if cyc:
        raise WaveError("ciclo de dependencias: " + " -> ".join(cyc), sorted(set(cyc)))

    def status(tid):
        return by_id[tid]["state"]["status"]

    done = {tid for tid in by_id if status(tid) in SATISFIED_STATES}
    out = {"waves": [], "deferred": [], "excluded": [], "satisfied": sorted(t for t in cand_ids if t in done)}
    cand.sort(key=lambda t: t["task_id"])
    sched = {t["task_id"] for t in cand if status(t["task_id"]) == "ready"}
    reasons = {}
    for t in cand:
        tid = t["task_id"]
        if status(tid) not in SATISFIED_STATES and tid not in sched:
            out["excluded"].append({"task": tid, "status": status(tid), "reason": "estado '%s' nao e executavel" % status(tid)})
    changed = True
    while changed:  # quem depende de algo que nunca sera agendado nem esta satisfeito fica sem onda
        changed = False
        for tid in sorted(sched):
            bad = [d for d in deps[tid] if d not in done and d not in sched]
            if bad:
                sched.discard(tid)
                reasons[tid] = "aguarda %s (estado '%s'; nao entra em onda)" % (
                    ", ".join(bad), ", ".join(sorted({status(d) for d in bad})))
                changed = True
    for tid in sorted(reasons):
        out["deferred"].append({"task": tid, "reason": reasons[tid], "wave": None})

    remaining, n = set(sched), 0
    while remaining:
        n += 1
        eligible = sorted(tid for tid in remaining if all(d in done for d in deps[tid]))
        picked = []
        for tid in eligible:
            t = by_id[tid]
            solo = not t.get("dependencies", {}).get("parallelizable", False)
            if solo and not picked:
                picked = [tid]
                break
            if solo:
                out["deferred"].append({"task": tid, "reason": "parallelizable=false: precisa de onda propria", "wave": n})
                continue
            why = None
            for o in picked:
                why = tasks_conflict(by_id[o], t)
                if why:
                    why = "conflito com %s: %s" % (o, why)
                    break
            if why:
                out["deferred"].append({"task": tid, "reason": why, "wave": n})
            else:
                picked.append(tid)
        out["waves"].append({"wave": n, "tasks": [{
            "task_id": tid, "title": by_id[tid]["title"], "feature_id": by_id[tid].get("feature_id"),
            "role": by_id[tid].get("assigned_agent", {}).get("role"),
            "agent_id": by_id[tid].get("assigned_agent", {}).get("agent_id"),
            "paths": _task_paths(by_id[tid]),
        } for tid in picked]})
        done.update(picked)
        remaining.difference_update(picked)
    return out


def load_tasks(project):
    tasks = []
    for f in sorted(glob.glob(os.path.join(aisef_dir(project), "contracts", "tasks", "*.json"))):
        with open(f, encoding="utf-8") as fh:
            tasks.append(json.load(fh))
    return tasks


def format_waves(res):
    lines = []
    for w in res["waves"]:
        lines.append("Onda %d (%d tarefa(s) em paralelo)" % (w["wave"], len(w["tasks"])))
        for t in w["tasks"]:
            lines.append("  %s [%s] %s" % (t["task_id"], t["role"] or "?", t["title"]))
    if not res["waves"]:
        lines.append("Nenhuma tarefa executavel.")
    if res["deferred"]:
        lines.append("Adiadas:")
        for d in res["deferred"]:
            lines.append("  %s%s: %s" % (d["task"], " (onda %d)" % d["wave"] if d["wave"] else "", d["reason"]))
    if res["excluded"]:
        lines.append("Fora das ondas:")
        for e in res["excluded"]:
            lines.append("  %s: %s" % (e["task"], e["reason"]))
    if res["satisfied"]:
        lines.append("Ja concluidas: " + ", ".join(res["satisfied"]))
    return "\n".join(lines)
