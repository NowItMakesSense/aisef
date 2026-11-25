#!/usr/bin/env python3
"""AISEF deps (0.17, S-05): confere uma dependencia nova antes de ela entrar no projeto.

Tres perguntas, cada uma numa fonte publica:
  1. o pacote existe no registro do ecossistema? Nao existir e o sinal de nome inventado pelo modelo (slopsquatting);
  2. quantos dias tem desde a primeira publicacao? Pacote de poucos dias merece desconfianca;
  3. o OSV (api.osv.dev) tem avisos de vulnerabilidade ou de pacote malicioso para ele?

    python -I aisef_deps.py check <ecossistema> <pacote> [--json] [--timeout 5]
    ecossistemas: pypi, npm, crates, go, nuget, rubygems, packagist

So usa a rede quando alguem roda este comando, ou quando o usuario liga `"dependency_check": "online"` no
.aisef/config.json (o gateway entao confere sozinho e poe o resultado no motivo da pergunta). Saida 0 quando nao
achou problema, 1 quando achou (inexistente, novo demais ou com aviso), 2 quando nao conseguiu conferir.
"""
import argparse
import datetime
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

YOUNG_DAYS = 30
OSV_URL = "https://api.osv.dev/v1/query"
OSV_ECO = {"pypi": "PyPI", "npm": "npm", "crates": "crates.io", "go": "Go", "nuget": "NuGet", "rubygems": "RubyGems",
           "packagist": "Packagist"}
UA = "aisef-deps"


def _q(name):
    return urllib.parse.quote(name, safe="@")


def registry_url(eco, name):
    if eco == "pypi":
        return "https://pypi.org/pypi/%s/json" % _q(name)
    if eco == "npm":
        return "https://registry.npmjs.org/%s" % _q(name).replace("/", "%2F")
    if eco == "crates":
        return "https://crates.io/api/v1/crates/%s" % _q(name)
    if eco == "go":
        esc = "".join("!" + c.lower() if c.isupper() else c for c in name)  # escape de maiusculas do proxy do Go
        return "https://proxy.golang.org/%s/@v/list" % esc
    if eco == "nuget":
        return "https://api.nuget.org/v3/registration5-semver1/%s/index.json" % _q(name.lower())
    if eco == "rubygems":
        return "https://rubygems.org/api/v1/versions/%s.json" % _q(name)
    if eco == "packagist":
        return "https://repo.packagist.org/p2/%s.json" % name.lower()
    raise ValueError("ecossistema desconhecido: %s (use %s)" % (eco, ", ".join(sorted(OSV_ECO))))


def http_fetch(url, data=None, timeout=5):
    """(status, corpo como texto). 404 vira (404, ''); falha de rede levanta OSError."""
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers={"User-Agent": UA, "Accept": "application/json",
                                                          **({"Content-Type": "application/json"} if body else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (URL montada aqui, https fixo)
            return r.status, r.read(2_000_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


def _iso(s):
    if not s:
        return None
    try:
        d = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)


def first_published(eco, text):
    """Data da primeira publicacao, a partir da resposta do registro (None quando o registro nao informa)."""
    if eco == "go":
        return None
    doc = json.loads(text)
    dates = []
    if eco == "pypi":
        dates = [f.get("upload_time_iso_8601") for files in (doc.get("releases") or {}).values() for f in files or []]
    elif eco == "npm":
        dates = [(doc.get("time") or {}).get("created")]
    elif eco == "crates":
        dates = [(doc.get("crate") or {}).get("created_at")]
    elif eco == "nuget":
        dates = [e.get("catalogEntry", {}).get("published") for p in doc.get("items") or [] for e in p.get("items") or []]
    elif eco == "rubygems":
        dates = [v.get("created_at") for v in doc if isinstance(v, dict)] if isinstance(doc, list) else []
    elif eco == "packagist":
        dates = [v.get("time") for vs in (doc.get("packages") or {}).values() for v in vs or []]
    parsed = [d for d in (_iso(x) for x in dates) if d and d.year > 1971]  # nuget usa 1900 para versao despublicada
    return min(parsed) if parsed else None


def check(eco, name, fetch=None, now=None, timeout=5):
    """Resultado: {exists, age_days, vulns, problems, error}. `fetch(url, data=None, timeout=)` e injetavel (testes)."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    fetch = fetch or http_fetch
    out = {"ecosystem": eco, "package": name, "exists": None, "age_days": None, "vulns": None, "problems": [], "error": None}
    try:
        status, text = fetch(registry_url(eco, name), timeout=timeout)
        if status == 404 or (eco == "go" and status == 410):
            out["exists"] = False
            out["problems"].append("nao existe no registro (possivel pacote inventado)")
            return out
        if status != 200:
            out["error"] = "registro respondeu %s" % status
            return out
        out["exists"] = True
        if eco == "go" and not text.strip():
            out["problems"].append("modulo sem versao publicada no proxy do Go")
        first = first_published(eco, text)
        if first:
            out["age_days"] = (now - first).days
            if out["age_days"] < YOUNG_DAYS:
                out["problems"].append("publicado ha %d dias (menos de %d)" % (out["age_days"], YOUNG_DAYS))
        status, text = fetch(OSV_URL, {"package": {"name": name, "ecosystem": OSV_ECO[eco]}}, timeout=timeout)
        if status == 200:
            vulns = json.loads(text or "{}").get("vulns") or []
            out["vulns"] = [v.get("id") for v in vulns]
            mal = [v for v in out["vulns"] if str(v).startswith("MAL-")]
            if mal:
                out["problems"].append("marcado como malicioso no OSV (%s)" % ", ".join(mal[:3]))
            elif vulns:
                out["problems"].append("%d aviso(s) no OSV em alguma versao (%s): confira a versao que vai entrar"
                                       % (len(vulns), ", ".join(out["vulns"][:3])))
        else:
            out["error"] = "OSV respondeu %s" % status
    except (OSError, ValueError) as e:
        out["error"] = str(e)[:200]
    return out


def summary(res):
    """Uma linha curta para o motivo do ask."""
    if res["exists"] is False:
        return res["problems"][0]
    bits = []
    if res["exists"]:
        bits.append("existe" + (", %d dias" % res["age_days"] if res["age_days"] is not None else ""))
    bits += [p for p in res["problems"]]
    if res["vulns"] == [] and not res["error"]:
        bits.append("sem aviso no OSV")
    if res["error"]:
        bits.append("nao conferido: " + res["error"])
    return "; ".join(bits)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="confere registro, idade e OSV de um pacote")
    c.add_argument("ecosystem", choices=sorted(OSV_ECO))
    c.add_argument("package")
    c.add_argument("--json", action="store_true")
    c.add_argument("--timeout", type=float, default=5)
    a = ap.parse_args(argv)
    res = check(a.ecosystem, a.package, timeout=a.timeout)
    print(json.dumps(res, ensure_ascii=False, indent=2) if a.json else "%s:%s -> %s" % (a.ecosystem, a.package, summary(res)))
    if res["problems"]:
        return 1
    return 2 if res["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
