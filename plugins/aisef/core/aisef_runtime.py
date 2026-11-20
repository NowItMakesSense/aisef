#!/usr/bin/env python3
"""AISEF runtime (0.11.0): o que os hooks de subagente e o painel compartilham.

- `match_parents`: liga cada SubagentStart ao disparo (PreToolUse Agent|Task) que o originou.
- `task_from_description`: o `dispatch` descreve cada agente como "T-xxx: titulo"; daqui sai a tarefa.
- `transcript_usage`: soma os tokens de um transcript de subagente (o SubagentStop entrega
  `agent_transcript_path`; a documentacao do Claude Code nao traz `usage` no proprio hook).
- `usage_path` / `read_usage`: historico local de uso por subagente em .aisef/runtime/usage.jsonl.

Somente stdlib: e importado por hooks que rodam a cada evento.
"""
import json
import os
import re

TASK_RE = re.compile(r"^\s*(T-[A-Za-z0-9._-]+)\s*:")
USAGE_FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def role(agent_type):
    return (agent_type or "").split(":")[-1]


def task_from_description(description):
    m = TASK_RE.match(description or "")
    return m.group(1) if m else None


def match_parents(events):
    """Liga cada `start` ao `spawn` que o disparou: o mais antigo ainda livre, do mesmo papel, ate o start.

    Devolve {agent_id: (parent_id, description, inferred, model, task_id)}. `inferred` e verdadeiro quando os
    candidatos tinham pais diferentes (nao ha como saber qual deles disparou)."""
    spawns = [dict(e, used=False) for e in events if e.get("event") == "spawn"]
    parents = {}
    for e in events:
        if e.get("event") != "start" or e.get("agent_id") in parents:
            continue  # o mesmo agente comecando de novo nao consome outro disparo (F-04)
        r = role(e.get("agent_type"))
        cands = [s for s in spawns if not s["used"] and role(s.get("subagent_type")) == r
                 and (s.get("at") or "") <= (e.get("at") or "~")]
        if not cands:
            parents[e.get("agent_id")] = (None, None, True, None, None)  # sem registro do disparo
            continue
        pick = cands[0]
        pick["used"] = True
        inferred = len({c.get("parent_id") for c in cands}) > 1
        parents[e.get("agent_id")] = (pick.get("parent_id"), (pick.get("description") or "")[:200] or None, inferred,
                                      pick.get("model"), pick.get("task_id"))
    return parents


def transcript_usage(path):
    """Soma o uso de tokens das mensagens do assistente num transcript JSONL do Claude Code.

    Cada mensagem pode aparecer em varias linhas (streaming): conta uma vez por `message.id`, ficando com a ultima.
    Devolve None se o arquivo nao existe ou nao tem uso registrado."""
    if not path:
        return None
    path = os.path.expanduser(path)
    per_msg, models = {}, {}
    try:
        with open(path, encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                msg = rec.get("message") if isinstance(rec, dict) else None
                if not isinstance(msg, dict) or not isinstance(msg.get("usage"), dict):
                    continue
                if rec.get("type") not in (None, "assistant") and msg.get("role") != "assistant":
                    continue
                per_msg[msg.get("id") or "line-%d" % i] = (msg["usage"], msg.get("model"))
    except OSError:
        return None
    if not per_msg:
        return None
    total = {k: 0 for k in USAGE_FIELDS}
    for usage, model in per_msg.values():
        for k in USAGE_FIELDS:
            v = usage.get(k)
            if isinstance(v, int):
                total[k] += v
        if model:
            models[model] = models.get(model, 0) + 1
    total["messages"] = len(per_msg)
    total["models"] = sorted(models, key=lambda m: -models[m])
    return total


def usage_path(aisef_dir):
    return os.path.join(aisef_dir, "runtime", "usage.jsonl")


def read_usage(aisef_dir):
    out = []
    try:
        with open(usage_path(aisef_dir), encoding="utf-8") as fh:
            for line in fh:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def billable_tokens(u):
    """Tokens que pesam no custo: entrada + saida + escrita de cache (a leitura de cache e reportada a parte)."""
    return sum(u.get(k) or 0 for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens"))
