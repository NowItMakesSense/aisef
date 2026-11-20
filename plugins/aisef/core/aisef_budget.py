#!/usr/bin/env python3
"""AISEF budget (0.13, L-01 + L-06): quando o modo continuo deve parar alem de risco critico e tentativas.

- Orcamento por feature (L-01): minutos desde a primeira delegacao, tokens dos subagentes (usage.jsonl) e despachos
  somados. Passou de um limite: `budget_exhausted`, o loop para (logo depois de critical_risk).
- Falta de progresso (L-06): a mesma tarefa reprovada N vezes seguidas pelo mesmo motivo (assinatura da falha) para
  so essa tarefa, com `no_progress`. Subir de modelo sem contexto novo nao ajuda.
- Agente parado (L-06): tarefa em andamento ha mais que o tempo limite vira `stale_agent`.

Limites, nesta ordem (o seguinte vence): orchestration-defaults -> budget; config.json -> budget (protegido: subir
pede a aprovacao do usuario); Feature Contract -> budget (so pode BAIXAR; o check acusa BUDGET-RAISED). Nao ha
limite em dolares: o AISEF nao tem tabela de precos e preco por modelo muda.
"""
import datetime
import hashlib
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULTS_PATH = os.path.join(HERE, "orchestration-defaults.v0.1.json")
KEYS = ("max_minutes", "max_tokens", "max_attempts")
FALLBACK = {"max_minutes": 480, "max_tokens": 5000000, "max_attempts": 30, "agent_timeout_minutes": 60,
            "no_progress_repeats": 2}


def project_limits(cfg):
    """Limites do projeto: padroes do plugin com o config.json por cima."""
    out = dict(FALLBACK)
    try:
        with open(DEFAULTS_PATH, encoding="utf-8") as fh:
            out.update({k: v for k, v in (json.load(fh).get("budget") or {}).items() if k in FALLBACK})
    except (OSError, ValueError):
        pass
    out.update({k: v for k, v in ((cfg or {}).get("budget") or {}).items() if k in FALLBACK and isinstance(v, int) and v > 0})
    return out


def feature_limits(cfg, feature):
    """Limites efetivos da feature: o contrato so baixa (valor maior que o do projeto e ignorado aqui e acusado no check)."""
    out = project_limits(cfg)
    for k, v in ((feature or {}).get("budget") or {}).items():
        if k in KEYS and isinstance(v, int) and 0 < v < out[k]:
            out[k] = v
    return out


def raised(cfg, feature):
    """Chaves em que o Feature Contract tenta subir o limite do projeto (regra BUDGET-RAISED)."""
    lim = project_limits(cfg)
    return [k for k, v in ((feature or {}).get("budget") or {}).items() if k in KEYS and isinstance(v, int) and v > lim[k]]


def _parse(ts):
    try:
        return datetime.datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


def feature_usage(fid, task_ids, log, usage_runs, now):
    """{minutes, tokens, attempts} da feature, para comparar com os limites."""
    first = None
    attempts = 0
    for e in log:
        if e.get("event_type") == "delegation" and (e.get("feature_id") == fid or e.get("task_id") in task_ids):
            attempts += 1
            ts = _parse(e.get("timestamp"))
            first = first or ts
    tokens = 0
    for r in usage_runs:
        if r.get("task_id") in task_ids and isinstance(r.get("usage"), dict):
            u = r["usage"]
            tokens += sum(int(u.get(k) or 0) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens"))
    minutes = round((now - first).total_seconds() / 60, 1) if first else 0
    return {"minutes": minutes, "tokens": tokens, "attempts": attempts}


def exhausted(limits, used):
    """[(chave, usado, limite)] que passaram do limite."""
    pairs = (("max_minutes", "minutes"), ("max_tokens", "tokens"), ("max_attempts", "attempts"))
    return [(k, used[u], limits[k]) for k, u in pairs if used[u] >= limits[k]]


NUM_RE = re.compile(r"\d+")


def failure_signature(event):
    """Assinatura de uma reprovacao: o que falhou, sem numeros (linhas, tempos) nem o id da tentativa."""
    data = event.get("data") or {}
    parts = []
    for key in ("precheck", "failed_tests", "failed_criteria", "findings", "rules"):
        v = data.get(key)
        if isinstance(v, list):
            parts += sorted(str(x) for x in v)
        elif v:
            parts.append(str(v))
    if not parts:
        text = event.get("summary") or ""
        text = text.split(":", 1)[1] if ":" in text else text
        parts.append(text)
    norm = NUM_RE.sub("#", " | ".join(parts).lower()).strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16] if norm else None


def no_progress(log, tid, repeats):
    """As ultimas `repeats` reprovacoes da tarefa tem a mesma assinatura? (sem nenhuma diferente no meio)."""
    sigs = [failure_signature(e) for e in log if e.get("task_id") == tid and e.get("event_type") == "task_rejected"]
    if len(sigs) < repeats:
        return False
    tail = sigs[-repeats:]
    return tail[0] is not None and all(s == tail[0] for s in tail)
