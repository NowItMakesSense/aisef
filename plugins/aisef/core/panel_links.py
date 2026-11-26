"""Ligacoes entre features para a visao geral do painel.

Duas fontes, e o painel diz qual e qual:
- depends_on: o que o Feature Contract declara em dependencies.features;
- derived_from: outra feature que o titulo, o problema ou o objetivo do contrato cita, pelo id da feature
  ("Pendencias da FEAT-005") ou pelo id de uma fatia dela ("Correcoes da revisao da T-001").
So valem ids de features que existem no projeto; a propria feature nunca entra.
"""

import re

_ID = re.compile(r"\b([A-Z][A-Z0-9]*-[A-Z0-9][A-Z0-9-]*)\b")


def feature_links(features, tasks):
    """{feature_id: {"depends_on": [...], "derived_from": [...]}} na ordem em que aparecem."""
    fids = {f["feature_id"] for f in features}
    owner = {t["task_id"]: t.get("feature_id") for t in tasks}
    out = {}
    for f in features:
        fid = f["feature_id"]
        dep = [d for d in (f.get("dependencies") or {}).get("features", []) if d in fids and d != fid]
        text = " ".join(x for x in (f.get("title"), f.get("problem"), f.get("objective")) if isinstance(x, str))
        der = []
        for m in _ID.findall(text):
            src = m if m in fids else owner.get(m)
            if src and src != fid and src not in dep and src not in der:
                der.append(src)
        out[fid] = {"depends_on": list(dict.fromkeys(dep)), "derived_from": der}
    return out


def activity(log):
    """Eventos do log inteiro por dia e hora local, para o mapa de calor do historico: [{"day", "hour", "n"}]."""
    import datetime
    cells = {}
    for e in log:
        try:
            t = datetime.datetime.fromisoformat(str(e.get("timestamp")).replace("Z", "+00:00")).astimezone()
        except ValueError:
            continue
        k = (t.date().isoformat(), t.hour)
        cells[k] = cells.get(k, 0) + 1
    return [{"day": d, "hour": h, "n": n} for (d, h), n in sorted(cells.items())]
