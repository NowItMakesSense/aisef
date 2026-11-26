"""Ligacoes entre features da visao geral do painel (panel_links): dependencia declarada e feature citada no contrato."""

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import panel_links  # noqa: E402

total = fails = 0


def check(name, cond, detail=None):
    global total, fails
    total += 1
    fails += not cond
    print(("OK    " if cond else "FALHA ") + name + ("" if cond or detail is None else "  -> %r" % (detail,)))


features = [
    {"feature_id": "FEAT-001", "title": "Base de experiencia", "problem": "Sem base unica de CV.", "objective": "Ter um CV mestre."},
    {"feature_id": "FEAT-002", "title": "Correcoes da revisao da T-001", "problem": "A T-001 deixou concorrencia.", "objective": "Corrigir."},
    {"feature_id": "FEAT-003", "title": "Pendencias da FEAT-002", "problem": "Sobrou trabalho da FEAT-002 e da FEAT-999.",
     "objective": "Fechar.", "dependencies": {"features": ["FEAT-001", "FEAT-404", "FEAT-003"]}},
    {"feature_id": "FEAT-004", "title": "Nada a ver com FEAT-004", "problem": "Cita so a si mesma e a T-404.", "objective": "Isolada."},
    {"feature_id": "FEAT-005", "title": "Declarada e citada", "problem": "Depende da FEAT-001.", "objective": "x",
     "dependencies": {"features": ["FEAT-001", "FEAT-001"]}},
]
tasks = [{"task_id": "T-001", "feature_id": "FEAT-001"}, {"task_id": "T-002", "feature_id": "FEAT-002"}]
L = panel_links.feature_links(features, tasks)

check("feature sem citacao nem dependencia fica sem ligacao", L["FEAT-001"] == {"depends_on": [], "derived_from": []}, L["FEAT-001"])
check("fatia de outra feature citada vira derivada da dona da fatia (T-001 -> FEAT-001)", L["FEAT-002"]["derived_from"] == ["FEAT-001"], L["FEAT-002"])
check("dependencia declarada so com features que existem e sem a propria", L["FEAT-003"]["depends_on"] == ["FEAT-001"], L["FEAT-003"])
check("feature citada pelo id vira derivada; id inexistente fica de fora", L["FEAT-003"]["derived_from"] == ["FEAT-002"], L["FEAT-003"])
check("citar a si mesma ou fatia que nao existe nao cria ligacao", L["FEAT-004"] == {"depends_on": [], "derived_from": []}, L["FEAT-004"])
check("declarada e citada conta uma vez so, como declarada", L["FEAT-005"] == {"depends_on": ["FEAT-001"], "derived_from": []}, L["FEAT-005"])
check("contrato sem dependencies nao quebra", "FEAT-001" in L and len(L) == len(features))

t0 = datetime.datetime(2026, 11, 21, 9, 15, tzinfo=datetime.timezone.utc)
log = [{"timestamp": (t0 + datetime.timedelta(minutes=m)).isoformat()} for m in (0, 10, 40, 70)] + [{"timestamp": "quebrado"}]
A = panel_links.activity(log)
loc = t0.astimezone()
check("atividade: log inteiro por dia e hora local, timestamp invalido ignorado",
      sum(c["n"] for c in A) == 4 and A[0] == {"day": loc.date().isoformat(), "hour": loc.hour, "n": 3} and len(A) == 2, A)

print("\n%d verificacoes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
