"""Custo estimado do painel (panel_cost): preco por tipo de token, agregados, moeda local e cotacao com cache.
Sem rede: a busca da cotacao e substituida por uma funcao falsa."""

import datetime
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import panel_cost  # noqa: E402

total = fails = 0


def check(name, cond, detail=None):
    global total, fails
    total += 1
    fails += not cond
    print(("OK    " if cond else "FALHA ") + name + ("" if cond or detail is None else "  -> %r" % (detail,)))


os.environ.pop("AISEF_FX_OFFLINE", None)
os.environ.pop("AISEF_CURRENCY", None)
pricing = panel_cost.load_pricing()
op = pricing["models"]["claude-opus-5-5"]
check("tabela de precos tem fonte, data e os quatro precos por modelo",
      pricing.get("source", "").startswith("https://") and pricing.get("as_of") and all(set(v) == {"input", "cache_write", "cache_read", "output"} for v in pricing["models"].values()))
usd = panel_cost.run_usd({"input_tokens": 1_000_000, "output_tokens": 1_000_000, "cache_creation_input_tokens": 1_000_000, "cache_read_input_tokens": 1_000_000}, op)
check("um milhao de cada tipo no Opus 5.5 = entrada + saida + escrita + leitura", abs(usd - (op["input"] + op["output"] + op["cache_write"] + op["cache_read"])) < 1e-9, usd)

d = tempfile.mkdtemp()
aisef = os.path.join(d, ".aisef")
out = os.path.join(d, "panel")
os.makedirs(aisef)
with open(os.path.join(aisef, "config.json"), "w", encoding="utf-8") as fh:
    json.dump({"panel": {"currency": "brl"}}, fh)
tasks = [{"task_id": "T-1", "feature_id": "F-1", "state": {"status": "completed"}},
         {"task_id": "T-2", "feature_id": "F-2", "state": {"status": "in_progress"}}]
M = 1_000_000
runs = [
    {"at": "2026-11-20T12:00:00+00:00", "agent_type": "aisef:implementer", "task_id": "T-1", "usage": {"output_tokens": M, "models": ["claude-opus-5-5"]}},
    {"at": "2026-11-21T12:00:00+00:00", "task_id": "T-2", "usage": {"input_tokens": M, "models": ["claude-sonnet-5-5"]}},
    {"at": "2026-11-21T13:00:00+00:00", "task_id": None, "usage": {"cache_read_input_tokens": M, "models": ["claude-haiku-5-5"]}},
    {"at": "2026-11-21T14:00:00+00:00", "task_id": "T-1", "usage": {"output_tokens": M, "models": ["modelo-sem-preco"]}},
    {"at": "2026-11-21T15:00:00+00:00", "task_id": "T-1"},
]
calls = []


def fake(cur):
    calls.append(cur)
    return {"date": "2026-11-21", "rates": {cur: 5.5}}


now = datetime.datetime(2026, 11, 21, 18, 0, tzinfo=datetime.timezone.utc)
c = panel_cost.cost_summary(aisef, tasks, out, now=now, fetch=fake, pricing=pricing, runs=runs)
exp = 20.0 + 2.0 + 0.01
check("total soma so os modelos com preco", c["available"] and abs(c["total_usd"] - exp) < 1e-6, c.get("total_usd"))
check("modelo sem preco fica de fora e e contado", c["unpriced_runs"] == 1 and c["runs"] == 4, (c["unpriced_runs"], c["runs"]))
check("por modelo, do mais caro ao mais barato", [m["model"] for m in c["by_model"]] == ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"], c["by_model"])
check("por feature: execucao sem fatia entra como 'sem fatia'", {f["feature_id"] for f in c["by_feature"]} == {"F-1", "F-2", "sem fatia"}, c["by_feature"])
check("por papel de agente, do mais caro ao mais barato", [x["agent"] for x in c["by_agent"]][0] == "implementer" and abs(sum(x["usd"] for x in c["by_agent"]) - exp) < 1e-6, c["by_agent"])
check("por dia em ordem", [x["day"] for x in c["by_day"]] == sorted(x["day"] for x in c["by_day"]) and len(c["by_day"]) == 2, c["by_day"])
check("mediana por fatia concluida conta so a concluida (T-1, Opus)", abs(c["per_completed_task_median_usd"] - 20.0) < 1e-6, c["per_completed_task_median_usd"])
check("moeda da config (minuscula vira BRL) e cotacao buscada", c["currency"] == "BRL" and c["rate"] == 5.5 and c["rate_date"] == "2026-11-21" and calls == ["BRL"], (c["currency"], c["rate"], calls))
c2 = panel_cost.cost_summary(aisef, tasks, out, now=now, fetch=fake, pricing=pricing, runs=runs)
check("no mesmo dia a cotacao vem do cache, sem buscar de novo", calls == ["BRL"] and c2["rate"] == 5.5, calls)


def down(cur):
    raise OSError("sem rede")


later = now + datetime.timedelta(days=2)
c3 = panel_cost.cost_summary(aisef, tasks, out, now=later, fetch=down, pricing=pricing, runs=runs)
check("sem rede em outro dia: usa a ultima cotacao guardada e diz isso", c3["rate"] == 5.5 and "ultima guardada" in (c3["rate_source"] or ""), c3["rate_source"])
os.remove(os.path.join(out, "fx-cache.json"))
c4 = panel_cost.cost_summary(aisef, tasks, out, now=later, fetch=down, pricing=pricing, runs=runs)
check("sem rede e sem cache: fica em dolar, sem cotacao inventada", c4["currency"] == "USD" and c4["rate"] is None, (c4["currency"], c4["rate"]))
os.environ["AISEF_FX_OFFLINE"] = "1"
c5 = panel_cost.cost_summary(aisef, tasks, out, now=later, fetch=fake, pricing=pricing, runs=runs)
check("AISEF_FX_OFFLINE=1 nao busca cotacao", calls == ["BRL"] and c5["rate"] is None, calls)
os.environ.pop("AISEF_FX_OFFLINE")
os.remove(os.path.join(aisef, "config.json"))
os.environ["AISEF_CURRENCY"] = "USD"
c6 = panel_cost.cost_summary(aisef, tasks, out, now=later, fetch=fake, pricing=pricing, runs=runs)
check("moeda USD nao busca cotacao (taxa 1)", c6["currency"] == "USD" and c6["rate"] == 1.0 and calls == ["BRL"], (c6["currency"], c6["rate"]))
os.environ.pop("AISEF_CURRENCY")
check("sem uso registrado: available falso", panel_cost.cost_summary(aisef, tasks, out, runs=[])["available"] is False)

print("\n%d verificacoes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
