#!/usr/bin/env python3
"""Avaliacao dos revisores do AISEF com bugs plantados (0.17, M-07). Alimenta a C-05: cortar quem nao se paga.

Cada caso em bench/reviewers/<id>/ tem:
    case.json   id, category, file e bug ({match, description, keywords}) ou null nos casos limpos
    before/     o arquivo antes da mudanca
    after/      o arquivo depois; o revisor recebe o diff e esta pasta

Comandos:
    python tools/bench_reviewers.py --check-fixtures
        Sem modelo. Cada bug esta numa linha unica do arquivo e numa linha que a mudanca acrescentou; categorias e
        casos limpos suficientes; os agentes citados existem. Roda no run_tests.py.

    python tools/bench_reviewers.py --run [--agents a,b] [--cases a,b] [--reps 1] [--model sonnet]
                                    [--claude PATH] [--timeout 600] [--out docs/benchmarks]
        Gasta tokens (decisao do usuario). Roda cada agente nos casos do seu escopo e nos limpos, com `claude -p`, o
        corpo do agente como system prompt e so Read, Grep e Glob. Grava reviewers-<data>.json e .md.

    python tools/bench_reviewers.py --score <reviewers-<data>.json>
        Recalcula as metricas de um resultado gravado (sem modelo).

Metricas por agente: recall (casos com bug do seu escopo em que um achado acerta o arquivo e a linha, +-3, ou cita
uma palavra-chave do bug), falso alarme (casos limpos com achado medium ou mais grave), precisao (achados medium+ que
acertam o bug / achados medium+), custo. Veredito: "paga" com recall >= 0,6 e falso alarme <= 0,25; "cortar?" com
recall < 0,3; "revisar" no resto.
"""
import argparse
import datetime
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES = os.path.join(ROOT, "bench", "reviewers")
AGENTS_DIR = os.path.join(ROOT, "plugins", "aisef", "agents")

CATEGORY_AGENTS = {
    "security": ["security", "code-reviewer"],
    "sql": ["database-reviewer", "code-reviewer"],
    "types": ["type-design-analyzer", "code-reviewer"],
    "silent-failure": ["silent-failure-hunter", "code-reviewer"],
    "weak-test": ["pr-test-analyzer", "code-reviewer"],
    "logic": ["code-reviewer"],
}
LANG_AGENTS = {".py": ["python-reviewer"], ".ts": ["typescript-reviewer"], ".sql": ["database-reviewer"]}
CATEGORIES = set(CATEGORY_AGENTS) | {"clean"}
SEVERITY = {"critical": 4, "critica": 4, "crítica": 4, "high": 3, "alta": 3, "alto": 3, "medium": 2, "media": 2,
            "média": 2, "medio": 2, "médio": 2, "low": 1, "baixa": 1, "baixo": 1, "info": 0, "nit": 0}
LINE_TOLERANCE = 3

PROMPT = """Revise a mudanca abaixo, no seu papel. Os arquivos como ficaram depois da mudanca estao no diretorio atual.
Relate so problemas reais desta mudanca; mudanca correta nao precisa de achado.

```diff
{diff}
```

No fim da resposta, escreva SO um bloco ```json com {{"findings": [{{"file": "caminho", "line": N, "severity":
"critical|high|medium|low", "summary": "uma frase"}}]}}. Lista vazia se nao houver problema."""


def load_cases(only=None):
    out = []
    for cid in sorted(os.listdir(CASES)):
        path = os.path.join(CASES, cid, "case.json")
        if os.path.isfile(path) and (not only or cid in only):
            with open(path, encoding="utf-8") as fh:
                out.append(json.load(fh))
    return out


def _read(cid, side, rel):
    p = os.path.join(CASES, cid, side, rel)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as fh:
        return fh.read().splitlines()


def diff_of(case):
    before, after = _read(case["id"], "before", case["file"]), _read(case["id"], "after", case["file"])
    return "\n".join(difflib.unified_diff(before, after, "a/" + case["file"], "b/" + case["file"], lineterm=""))


def added_lines(case):
    """Numeros (1-based) das linhas do arquivo novo que a mudanca acrescentou ou trocou."""
    before, after = _read(case["id"], "before", case["file"]), _read(case["id"], "after", case["file"])
    out = set()
    for tag, _i1, _i2, j1, j2 in difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
        if tag in ("replace", "insert"):
            out.update(range(j1 + 1, j2 + 1))
    return out


def bug_line(case):
    lines = _read(case["id"], "after", case["file"])
    hits = [i + 1 for i, line in enumerate(lines) if case["bug"]["match"] in line]
    return hits[0] if len(hits) == 1 else None


def agents_for(case):
    ext = os.path.splitext(case["file"])[1]
    if case["category"] == "clean":  # todo revisor passa pelos limpos: e ali que se mede o falso alarme
        return sorted({a for v in CATEGORY_AGENTS.values() for a in v} | set(LANG_AGENTS.get(ext, [])))
    return sorted(set(CATEGORY_AGENTS[case["category"]]) | set(LANG_AGENTS.get(ext, [])))


def check_fixtures():
    problems = []
    cases = load_cases()
    if not 10 <= len(cases) <= 20:
        problems.append("o conjunto deve ter de 10 a 20 casos, tem %d" % len(cases))
    if sum(c["category"] == "clean" for c in cases) < 4:
        problems.append("menos de 4 casos limpos")
    for cat in CATEGORIES - {c["category"] for c in cases}:
        problems.append("categoria sem caso: %s" % cat)
    for c in cases:
        where = c.get("id", "?")
        if c.get("category") not in CATEGORIES:
            problems.append("%s: categoria desconhecida %s" % (where, c.get("category")))
            continue
        if not os.path.basename(os.path.dirname(os.path.join(CASES, where, "case.json"))) == where:
            problems.append("%s: id diferente da pasta" % where)
        if not _read(where, "after", c["file"]):
            problems.append("%s: after/%s ausente ou vazio" % (where, c["file"]))
            continue
        if not diff_of(c):
            problems.append("%s: before e after iguais" % where)
        if (c["category"] == "clean") != (c.get("bug") is None):
            problems.append("%s: caso limpo sem bug e caso com bug fora de 'clean'" % where)
        if c.get("bug"):
            ln = bug_line(c)
            if ln is None:
                problems.append("%s: o trecho do bug nao esta em exatamente uma linha" % where)
            elif ln not in added_lines(c):
                problems.append("%s: a linha %d do bug nao foi acrescentada pela mudanca" % (where, ln))
            if not c["bug"].get("keywords") or not c["bug"].get("description"):
                problems.append("%s: bug sem description ou keywords" % where)
        for a in agents_for(c):
            if not os.path.isfile(os.path.join(AGENTS_DIR, a + ".md")):
                problems.append("%s: agente %s nao existe" % (where, a))
    return cases, problems


# --- resposta e placar ----------------------------------------------------------------------------------------------

def parse_findings(text):
    """Achados do ultimo bloco JSON com "findings" na resposta; None se nao achou bloco legivel."""
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text or "", re.S)
    if not blocks:
        m = re.search(r"(\{\s*\"findings\".*\})", text or "", re.S)
        blocks = [m.group(1)] if m else []
    for raw in reversed(blocks):
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get("findings"), list):
            return [f for f in data["findings"] if isinstance(f, dict)]
    return None


def severity(f):
    return SEVERITY.get(str(f.get("severity", "")).strip().lower(), 2)


def hits_bug(f, case):
    bug = case.get("bug")
    if not bug:
        return False
    fname = str(f.get("file") or "").replace("\\", "/")
    same_file = not fname or fname.endswith(case["file"]) or case["file"].endswith(fname.lstrip("./"))
    try:
        line = int(f.get("line"))
    except (TypeError, ValueError):
        line = None
    want = bug_line(case)
    if same_file and line is not None and want is not None and abs(line - want) <= LINE_TOLERANCE:
        return True
    text = str(f.get("summary") or "").lower()
    return same_file and any(k.lower() in text for k in bug.get("keywords", []))


def score(runs, cases):
    """runs: [{agent, case, findings (lista ou None), cost_usd}] -> {agente: metricas}."""
    by_id = {c["id"]: c for c in cases}
    out = {}
    for r in runs:
        c = by_id.get(r["case"])
        if c is None:
            continue
        m = out.setdefault(r["agent"], {"bug_runs": 0, "detected": 0, "clean_runs": 0, "false_alarms": 0,
                                        "findings": 0, "true_findings": 0, "unparsed": 0, "cost_usd": 0.0})
        m["cost_usd"] += r.get("cost_usd") or 0
        fs = r.get("findings")
        if fs is None:
            m["unparsed"] += 1
            fs = []
        serious = [f for f in fs if severity(f) >= 2]
        m["findings"] += len(serious)
        if c.get("bug"):
            m["bug_runs"] += 1
            hit = [f for f in fs if hits_bug(f, c)]
            m["detected"] += bool(hit)
            m["true_findings"] += sum(1 for f in serious if hits_bug(f, c))
        else:
            m["clean_runs"] += 1
            m["false_alarms"] += bool(serious)
    for m in out.values():
        m["recall"] = round(m["detected"] / m["bug_runs"], 3) if m["bug_runs"] else None
        m["false_alarm_rate"] = round(m["false_alarms"] / m["clean_runs"], 3) if m["clean_runs"] else None
        m["precision"] = round(m["true_findings"] / m["findings"], 3) if m["findings"] else None
        m["cost_usd"] = round(m["cost_usd"], 4)
        m["verdict"] = verdict(m)
    return out


def verdict(m):
    if m["recall"] is None:
        return "sem casos"
    if m["recall"] < 0.3:
        return "cortar?"
    if m["recall"] >= 0.6 and (m["false_alarm_rate"] or 0) <= 0.25:
        return "paga"
    return "revisar"


def render(scores, meta):
    pct = lambda v: "-" if v is None else "%d%%" % round(v * 100)  # noqa: E731
    L = ["# Revisores com bugs plantados (M-07): %s" % meta["date"], "",
         "Modelo `%s`, %d repeticao(oes), %d caso(s). Gerado por `tools/bench_reviewers.py`." % (
             meta["model"], meta["reps"], meta["cases"]), "",
         "| Agente | Recall | Falso alarme | Precisao | Sem JSON | Custo (US$) | Veredito |", "|---|---|---|---|---|---|---|"]
    for a in sorted(scores):
        m = scores[a]
        L.append("| %s | %s (%d/%d) | %s (%d/%d) | %s | %d | %.2f | %s |" % (
            a, pct(m["recall"]), m["detected"], m["bug_runs"], pct(m["false_alarm_rate"]), m["false_alarms"],
            m["clean_runs"], pct(m["precision"]), m["unparsed"], m["cost_usd"], m["verdict"]))
    L += ["", "Recall: casos com bug do escopo do agente em que um achado acertou o arquivo e a linha (+-%d) ou citou "
          "o bug. Falso alarme: casos limpos com achado medium ou mais grave. Veredito: paga (recall >= 60%%, falso "
          "alarme <= 25%%), cortar? (recall < 30%%), revisar." % LINE_TOLERANCE]
    return "\n".join(L) + "\n"


# --- execucao (gasta tokens) ----------------------------------------------------------------------------------------

def agent_prompt(agent):
    with open(os.path.join(AGENTS_DIR, agent + ".md"), encoding="utf-8") as fh:
        text = fh.read()
    return text.split("---", 2)[2].strip() if text.startswith("---") else text


def run_one(claude, agent, case, model, timeout):
    work = tempfile.mkdtemp(prefix="aisef-rev-")
    try:
        shutil.copytree(os.path.join(CASES, case["id"], "after"), work, dirs_exist_ok=True)
        cmd = [claude, "-p", PROMPT.format(diff=diff_of(case)), "--output-format", "json", "--no-session-persistence",
               "--model", model, "--append-system-prompt", agent_prompt(agent), "--allowedTools", "Read", "Grep", "Glob"]
        try:
            r = subprocess.run(cmd, cwd=work, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=timeout)
            out = r.stdout
        except subprocess.TimeoutExpired:
            out = ""
        try:
            data = json.loads(out)
        except ValueError:
            data = {}
        return {"agent": agent, "case": case["id"], "findings": parse_findings(data.get("result", "")),
                "cost_usd": data.get("total_cost_usd"), "is_error": data.get("is_error", not data)}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check-fixtures", action="store_true")
    p.add_argument("--run", action="store_true")
    p.add_argument("--score")
    p.add_argument("--agents")
    p.add_argument("--cases")
    p.add_argument("--reps", type=int, default=1)
    p.add_argument("--model", default="sonnet")
    p.add_argument("--claude", default=shutil.which("claude") or "claude")
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--out", default=os.path.join(ROOT, "docs", "benchmarks"))
    a = p.parse_args(argv)
    if a.check_fixtures:
        cases, problems = check_fixtures()
        for x in problems:
            print("ERRO " + x)
        print("%d caso(s) de revisor, %d problema(s)" % (len(cases), len(problems)))
        return 1 if problems else 0
    if a.score:
        with open(a.score, encoding="utf-8") as fh:
            data = json.load(fh)
        print(render(score(data["runs"], load_cases()), data["meta"]))
        return 0
    if not a.run:
        p.error("use --check-fixtures, --run ou --score")
    cases = load_cases(set(a.cases.split(",")) if a.cases else None)
    only = set(a.agents.split(",")) if a.agents else None
    runs = []
    for c in cases:
        for agent in agents_for(c):
            if only and agent not in only:
                continue
            for _ in range(a.reps):
                r = run_one(a.claude, agent, c, a.model, a.timeout)
                runs.append(r)
                print("%-24s %-28s %s" % (agent, c["id"], "sem JSON" if r["findings"] is None else
                                          "%d achado(s)" % len(r["findings"])))
    date = datetime.date.today().isoformat()
    meta = {"date": date, "model": a.model, "reps": a.reps, "cases": len(cases)}
    os.makedirs(a.out, exist_ok=True)
    base = os.path.join(a.out, "reviewers-%s" % date)
    scores = score(runs, cases)
    with open(base + ".json", "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"meta": meta, "runs": runs, "scores": scores}, fh, ensure_ascii=False, indent=2)
    with open(base + ".md", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render(scores, meta))
    print(render(scores, meta))
    return 0


if __name__ == "__main__":
    sys.exit(main())
