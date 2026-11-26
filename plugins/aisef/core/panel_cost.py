"""Custo estimado em dinheiro para o painel, na moeda local.

- Tokens: .aisef/runtime/usage.jsonl (gravado pelo hook SubagentStop), por modelo e por tipo (entrada, saida,
  escrita e leitura de cache).
- Preco: model-pricing.v0.1.json (tabela da API em dolar, com a data e a fonte). Modelo sem preco fica de fora e
  e contado em unpriced_runs; nunca se inventa preco.
- Moeda: .aisef/config.json (panel.currency), senao AISEF_CURRENCY, senao a regiao do sistema (pt_BR -> BRL).
- Cotacao: Frankfurter (taxas de referencia do Banco Central Europeu), uma vez por dia, guardada em
  <out>/fx-cache.json. Sem rede, usa a ultima guardada e diz a data; sem nenhuma, fica em dolar.
  AISEF_FX_OFFLINE=1 desliga a busca (testes, ambiente sem rede).
E estimativa pelo preco de tabela, nao a fatura: o painel diz isso ao lado do numero.
"""

import datetime
import json
import locale
import os
import re
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PRICING = os.path.join(HERE, "model-pricing.v0.1.json")
FX_URL = "https://api.frankfurter.dev/v1/latest?base=USD&symbols=%s"
FX_SOURCE = "BCE via Frankfurter"
REGION_CURRENCY = {
    "BR": "BRL", "US": "USD", "GB": "GBP", "CN": "CNY", "JP": "JPY", "MX": "MXN", "CA": "CAD", "AU": "AUD", "IN": "INR",
    "CH": "CHF", "KR": "KRW", "ZA": "ZAR", "SE": "SEK", "NO": "NOK", "DK": "DKK", "PL": "PLN", "CZ": "CZK", "HU": "HUF",
    "TR": "TRY", "IL": "ILS", "NZ": "NZD", "SG": "SGD", "HK": "HKD", "TH": "THB", "ID": "IDR", "PH": "PHP", "MY": "MYR",
    "RO": "RON", "IS": "ISK",
    **{r: "EUR" for r in ("PT", "ES", "FR", "DE", "IT", "NL", "BE", "AT", "IE", "FI", "GR", "LU", "SK", "SI", "EE", "LV", "LT", "HR", "MT", "CY")},
}
WIN_REGION = {"brazil": "BR", "united states": "US", "united kingdom": "GB", "portugal": "PT", "spain": "ES", "france": "FR",
              "germany": "DE", "italy": "IT", "china": "CN", "japan": "JP", "mexico": "MX", "canada": "CA"}


def load_pricing(path=PRICING):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def run_usd(usage, price):
    """Dolares de uma execucao: cada tipo de token pelo seu preco por milhao."""
    return (float(usage.get("input_tokens") or 0) * price["input"] + float(usage.get("output_tokens") or 0) * price["output"]
            + float(usage.get("cache_creation_input_tokens") or 0) * price["cache_write"]
            + float(usage.get("cache_read_input_tokens") or 0) * price["cache_read"]) / 1e6


def local_currency(aisef_dir):
    try:
        with open(os.path.join(aisef_dir, "config.json"), encoding="utf-8") as fh:
            cur = ((json.load(fh).get("panel") or {}).get("currency") or "").strip().upper()
        if re.fullmatch(r"[A-Z]{3}", cur):
            return cur
    except (OSError, ValueError, AttributeError):
        pass
    env = os.environ.get("AISEF_CURRENCY", "").strip().upper()
    if re.fullmatch(r"[A-Z]{3}", env):
        return env
    name = (locale.getlocale()[0] or "")
    m = re.search(r"[_-]([A-Za-z]{2})$", name)
    region = m.group(1).upper() if m else WIN_REGION.get(name.split("_")[-1].lower(), "")
    return REGION_CURRENCY.get(region, "USD")


def fx_rate(currency, out, today, fetch=None):
    """(taxa, data, fonte) de USD para a moeda; None quando nao ha cotacao nenhuma."""
    if currency == "USD":
        return 1.0, None, None
    cache_path = os.path.join(out, "fx-cache.json")
    cached = None
    try:
        with open(cache_path, encoding="utf-8") as fh:
            cached = json.load(fh)
        if cached.get("currency") != currency:
            cached = None
    except (OSError, ValueError):
        cached = None
    if cached and cached.get("fetched_on") == today:
        return cached["rate"], cached.get("date"), FX_SOURCE
    if os.environ.get("AISEF_FX_OFFLINE") != "1":
        try:
            if fetch is None:
                req = urllib.request.Request(FX_URL % currency, headers={"User-Agent": "aisef-panel"})
                with urllib.request.urlopen(req, timeout=4) as r:
                    data = json.loads(r.read().decode("utf-8"))
            else:
                data = fetch(currency)
            rate = float(data["rates"][currency])
            if rate > 0:
                os.makedirs(out, exist_ok=True)
                with open(cache_path, "w", encoding="utf-8") as fh:
                    json.dump({"currency": currency, "rate": rate, "date": data.get("date"), "fetched_on": today}, fh)
                return rate, data.get("date"), FX_SOURCE
        except Exception:  # sem rede, servico fora ou resposta estranha: cai na ultima cotacao guardada
            pass
    if cached:
        return cached["rate"], cached.get("date"), FX_SOURCE + " (ultima guardada)"
    return None


def cost_summary(aisef_dir, tasks, out, now=None, fetch=None, pricing=None, runs=None):
    """Bloco `cost` do painel: total, por modelo, por dia, por feature e mediana por fatia concluida, em dolar,
    mais a moeda local e a cotacao (o painel converte)."""
    pricing = pricing or load_pricing()
    prices = pricing.get("models", {})
    if runs is None:
        import aisef_runtime
        runs = aisef_runtime.read_usage(aisef_dir)
    runs = [r for r in runs if isinstance(r.get("usage"), dict)]
    if not runs:
        return {"available": False, "note": "sem uso registrado (.aisef/runtime/usage.jsonl)"}
    feat = {t["task_id"]: t.get("feature_id") for t in tasks}
    done = {t["task_id"] for t in tasks if (t.get("state") or {}).get("status") == "completed"}
    by_model, by_day, by_feat, by_agent, per_task, unpriced, total = {}, {}, {}, {}, {}, 0, 0.0
    for r in runs:
        model = ((r["usage"].get("models") or [None])[0]) or "?"
        price = prices.get(model)
        if not price:
            unpriced += 1
            continue
        usd = run_usd(r["usage"], price)
        total += usd
        m = by_model.setdefault(model, {"model": model, "usd": 0.0, "runs": 0})
        m["usd"] += usd
        m["runs"] += 1
        try:
            day = datetime.datetime.fromisoformat(str(r.get("at")).replace("Z", "+00:00")).astimezone().date().isoformat()
        except ValueError:
            day = None
        if day:
            by_day[day] = by_day.get(day, 0.0) + usd
        role = str(r.get("agent_type") or "?").split(":")[-1]
        ag = by_agent.setdefault(role, {"usd": 0.0, "runs": 0})
        ag["usd"] += usd
        ag["runs"] += 1
        tid = r.get("task_id")
        fid = feat.get(tid) if tid else None
        key = fid or "sem fatia"
        by_feat[key] = by_feat.get(key, 0.0) + usd
        if tid:
            per_task[tid] = per_task.get(tid, 0.0) + usd
    done_costs = sorted(per_task[t] for t in done if t in per_task)
    currency = local_currency(aisef_dir)
    today = (now or datetime.datetime.now(datetime.timezone.utc)).astimezone().date().isoformat()
    fx = fx_rate(currency, out, today, fetch)
    r2 = lambda x: round(x, 4)  # noqa: E731
    return {
        "available": True, "total_usd": r2(total),
        "per_completed_task_median_usd": r2(done_costs[len(done_costs) // 2]) if done_costs else None,
        "by_model": sorted(({"model": k, "usd": r2(v["usd"]), "runs": v["runs"]} for k, v in by_model.items()), key=lambda x: -x["usd"]),
        "by_day": [{"day": d, "usd": r2(by_day[d])} for d in sorted(by_day)],
        "by_agent": sorted(({"agent": k, "usd": r2(v["usd"]), "runs": v["runs"]} for k, v in by_agent.items()), key=lambda x: -x["usd"]),
        "by_feature": sorted(({"feature_id": k, "usd": r2(v)} for k, v in by_feat.items()), key=lambda x: -x["usd"]),
        "runs": len(runs), "unpriced_runs": unpriced,
        "currency": currency if fx else "USD", "rate": fx[0] if fx else None, "rate_date": fx[1] if fx else None,
        "rate_source": fx[2] if fx else None,
        "prices_as_of": pricing.get("as_of"), "prices_source": pricing.get("source"),
    }
