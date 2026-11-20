#!/usr/bin/env python3
"""Benchmark de resultado do AISEF (M-03): Claude Code puro x AISEF, medidos por testes escondidos.

Cada tarefa em bench/tasks/<id>/ tem:
    task.json   id, kind, prompt (o pedido, igual para os dois bracos) e test_cmd (roda os testes escondidos)
    repo/       o repositorio inicial que o agente recebe
    hidden/     testes que o agente nunca ve: so entram na pasta depois que ele termina
    solution/   solucao de referencia, usada SO para validar o fixture (--check-fixtures)

Comandos:
    python tools/bench_outcomes.py --check-fixtures
        Sem modelo e sem custo. Para cada tarefa: os testes escondidos FALHAM no repo inicial e PASSAM com a
        solucao de referencia (e os testes visiveis do repo continuam passando). Roda no run_tests.py.

    python tools/bench_outcomes.py --prepare-only [--tasks a,b]
        Sem modelo. Monta as pastas de trabalho dos dois bracos e confere que o AISEF ficou pronto para despachar.

    python tools/bench_outcomes.py --run [--arms plain,aisef] [--reps 3] [--tasks a,b] [--model sonnet]
                                   [--claude PATH] [--timeout 1800] [--out docs/benchmarks]
        Gasta tokens. Roda `claude -p` em cada tarefa x braco x repeticao e grava docs/benchmarks/<data>.md e .json.
        Use em Linux ou WSL (o sandbox nativo do Claude Code nao existe no Windows).

Bracos (aisef-norev = aisef sem revisores especializados antes do validador, para medir o custo deles):
    plain  o repo e o pedido, sem AISEF. acceptEdits + Bash so para python e git de leitura.
    aisef  o mesmo repo com o AISEF iniciado (--plugin-dir plugins/aisef). Como nao ha ninguem para aprovar, o
           harness faz o papel do usuario ANTES do agente comecar: gera a feature a partir do pedido (uma fatia),
           aprova o plano e ativa os agentes. O agente segue em modo continuo ate um stop_reason.

Medidas por execucao: testes escondidos (passaram/total), testes visiveis, tokens e custo (do JSON do claude -p),
tempo, turnos e, no braco aisef, prompts e negacoes do gateway (aisef_project.py metrics).
"""
import argparse
import datetime
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCH = os.path.join(ROOT, "bench", "tasks")
PLUGIN = os.path.join(ROOT, "plugins", "aisef")
CORE = os.path.join(PLUGIN, "core")
PLAIN_TOOLS = ["Read", "Edit", "Write", "Glob", "Grep", "Bash(python:*)", "Bash(python3:*)", "Bash(git status:*)",
               "Bash(git diff:*)", "Bash(ls:*)"]


def load_tasks(only=None):
    out = []
    for name in sorted(os.listdir(BENCH)):
        path = os.path.join(BENCH, name, "task.json")
        if os.path.isfile(path) and (not only or name in only):
            with open(path, encoding="utf-8") as fh:
                t = json.load(fh)
            t["dir"] = os.path.join(BENCH, name)
            out.append(t)
    return out


def copy_tree(src, dst):
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True)


def run_tests(workdir, cmd, timeout=300):
    cmd = [sys.executable if c == "python" else c for c in cmd]
    r = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    text = r.stdout + r.stderr
    m = re.search(r"Ran (\d+) tests?", text)
    ran = int(m.group(1)) if m else 0
    bad = sum(int(x) for x in re.findall(r"(?:failures|errors)=(\d+)", text))
    if r.returncode != 0 and not bad and ran:
        bad = ran  # import quebrado ou similar: tudo conta como falha
    return {"ok": r.returncode == 0, "ran": ran, "passed": max(0, ran - bad) if r.returncode else ran, "tail": text[-1500:]}


def visible_cmd(workdir):
    return ["python", "-m", "unittest", "discover", "-s", "tests", "-t", "."] if os.path.isdir(os.path.join(workdir, "tests")) else None


def hidden_result(workdir, task):
    shutil.rmtree(os.path.join(workdir, "hidden"), ignore_errors=True)
    copy_tree(os.path.join(task["dir"], "hidden"), os.path.join(workdir, "hidden"))
    open(os.path.join(workdir, "hidden", "__init__.py"), "a").close()  # discover com -t . exige pacote
    return run_tests(workdir, task["test_cmd"])


# ---------------------------------------------------------------------------- fixtures
def check_fixtures(tasks):
    problems = []
    for t in tasks:
        with tempfile.TemporaryDirectory() as d:
            copy_tree(os.path.join(t["dir"], "repo"), d)
            before = hidden_result(d, t)
            if before["ok"]:
                problems.append("%s: os testes escondidos ja passam no repo inicial (a tarefa nao mede nada)" % t["id"])
            copy_tree(os.path.join(t["dir"], "solution"), d)
            after = hidden_result(d, t)
            if not after["ok"]:
                problems.append("%s: a solucao de referencia nao passa nos testes escondidos:\n%s" % (t["id"], after["tail"]))
            vis = visible_cmd(d)
            if vis and not run_tests(d, vis)["ok"]:
                problems.append("%s: a solucao de referencia quebra os testes visiveis" % t["id"])
            print("%-22s %-9s escondidos: inicial %d/%d, referencia %d/%d" % (
                t["id"], t["kind"], before["passed"], before["ran"], after["passed"], after["ran"]))
    return problems


# ---------------------------------------------------------------------------- preparo dos bracos
def git(workdir, *args):
    subprocess.run(["git", *args], cwd=workdir, capture_output=True, check=True)


def prepare(task, arm, base):
    workdir = os.path.join(base, "%s-%s" % (task["id"], arm))
    os.makedirs(workdir)
    copy_tree(os.path.join(task["dir"], "repo"), workdir)
    git(workdir, "init", "-q", "-b", "main")
    git(workdir, "-c", "user.email=bench@aisef.local", "-c", "user.name=bench", "add", "-A")
    git(workdir, "-c", "user.email=bench@aisef.local", "-c", "user.name=bench", "commit", "-q", "-m", "inicial")
    env = dict(os.environ, AISEF_HOME=os.path.join(base, "aisef-home-" + task["id"]))
    if arm.startswith("aisef"):
        prepare_aisef(task, workdir, env, reviewers=arm != "aisef-norev")
    return workdir, env


def _core(script, *args, env, cwd):
    r = subprocess.run([sys.executable, "-I", os.path.join(CORE, script), *args], cwd=cwd, env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise SystemExit("falhou %s %s:\n%s%s" % (script, " ".join(args), r.stdout[-800:], r.stderr[-800:]))
    return r.stdout


def prepare_aisef(task, workdir, env, reviewers=True):
    """Faz o papel do usuario antes do agente: init, agentes ativos, feature de uma fatia e plano aprovado."""
    pid = "PRJ-BENCH-" + re.sub(r"[^A-Z0-9]", "", task["id"].upper())[:20]
    _core("aisef_project.py", "init", "--project", ".", "--project-id", pid, "--name", task["id"], env=env, cwd=workdir)
    cfg_path = os.path.join(workdir, ".aisef", "config.json")
    with open(cfg_path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    cfg["graphify"] = {"enabled": False}  # fixture pequeno: o grafo nao rende (G-05 mede isso a parte)
    with open(cfg_path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    _core("aisef_project.py", "agents", "--project", ".", "--activate", env=env, cwd=workdir)
    _core("aisef_project.py", "settings", "--project", ".", "--apply", env=env, cwd=workdir)
    with open(os.path.join(workdir, ".aisef", "discovery.md"), "w", encoding="utf-8") as fh:
        fh.write("# Discovery\n\nRepositorio pequeno de benchmark. Pedido do usuario na feature FEAT-BENCH.\n")
    brief = {"id": "FEAT-BENCH", "title": task["id"], "objective": task["prompt"][:200], "problem": task["prompt"][:200],
             "requirements": {"REQ-001": task["prompt"]}, "scope_in": ["o pedido do REQ-001, neste repositorio"],
             "scope_out": ["qualquer mudanca fora do pedido"],
             "tasks": [{"id": "T-001", "kind": "slice", "title": task["id"], "reqs": ["REQ-001"], "touches": ["domain"],
                        "criteria": {"AC-1": "O pedido do REQ-001 esta implementado, com testes que falharam antes e passam depois"},
                        "paths": ["*.py", "tests/*"], "test_cmd": "python -m unittest discover -s tests -t ."}]}
    if not reviewers:  # braco aisef-norev: o mesmo fluxo sem a revisao especializada antes do validador (A-05)
        brief["tasks"][0]["review"] = {"reviewers": []}
    bpath = os.path.join(workdir, ".aisef", "bench-brief.json")
    with open(bpath, "w", encoding="utf-8") as fh:
        json.dump(brief, fh)
    _core("aisef_new.py", "feature", "--project", ".", "--brief", bpath, env=env, cwd=workdir)
    os.remove(bpath)
    pending = [f for f in os.listdir(os.path.join(workdir, ".aisef", "approvals")) if f.endswith(".json")]
    for name in pending:
        with open(os.path.join(workdir, ".aisef", "approvals", name), encoding="utf-8") as fh:
            req = json.load(fh)
        if req.get("status") == "pending" and req.get("request_type") == "plan_approval":
            _core("aisef_project.py", "decide", "--project", ".", "--request", req["request_id"], "--choice", "approve",
                  "--note", "aprovado pelo harness do benchmark (faz o papel do usuario)", env=env, cwd=workdir)


def aisef_ready(workdir, env):
    out = _core("aisef_project.py", "next", "--project", ".", "--json", env=env, cwd=workdir)
    res = json.loads(out)
    return any(a["kind"] == "dispatch" for a in res["actions"]), res


# ---------------------------------------------------------------------------- execucao
AISEF_PROMPT = ("Este projeto usa o AISEF. A feature FEAT-BENCH ja esta especificada e o plano foi aprovado pelo usuario. "
                "Nao ha usuario disponivel nesta sessao: siga o AISEF em modo continuo (aisef_project.py next, dispatch, "
                "validacao, complete) ate o next devolver um stop_reason, sem commit nem push. Pedido original do usuario:\n\n")


def run_claude(claude, workdir, env, arm, prompt, model, timeout):
    cmd = [claude, "-p", (AISEF_PROMPT + prompt) if arm.startswith("aisef") else prompt, "--output-format", "json",
           "--permission-mode", "acceptEdits", "--no-session-persistence", "--model", model]
    if arm.startswith("aisef"):
        cmd += ["--plugin-dir", PLUGIN, "--allowedTools", *PLAIN_TOOLS, "Agent", "Bash(python -I:*)"]
    else:
        cmd += ["--allowedTools", *PLAIN_TOOLS]
    start = datetime.datetime.now()
    try:
        r = subprocess.run(cmd, cwd=workdir, env=dict(env, CLAUDE_PROJECT_DIR=workdir, CLAUDE_CODE_DISABLE_BACKGROUND_TASKS="1"), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        out, err = r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        out, err = "", "timeout"
    secs = (datetime.datetime.now() - start).total_seconds()
    try:
        data = json.loads(out)
    except ValueError:
        data = {}
    usage = data.get("usage") or {}
    return {"seconds": round(secs, 1), "cost_usd": data.get("total_cost_usd"), "turns": data.get("num_turns"),
            "is_error": data.get("is_error", not data), "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"), "cache_read_tokens": usage.get("cache_read_input_tokens"),
            "cache_write_tokens": usage.get("cache_creation_input_tokens"), "stderr": err[-400:],
            **({"stdout_head": out[:400]} if not data or data.get("is_error") else {})}


CONTINUE_PROMPT = ("Continue o AISEF em modo continuo a partir do estado atual: rode aisef_project.py next e siga as "
                   "acoes (dispatch, validate-wave com os revisores de `reviews` em paralelo e depois o validador, complete) "
                   "ate o next devolver um stop_reason. Sem commit nem push.")
PENDING_KINDS = ("dispatch", "validate", "complete")


def run_aisef_until_stop(claude, workdir, env, arm, prompt, model, timeout, max_rounds=6):
    """`claude -p` encerra quando o turno principal termina, mesmo com o fluxo no meio (ex.: logo depois do implementer).
    O harness retoma a sessao enquanto o `next` tiver dispatch, validacao ou conclusao pendente, e soma custo e tempo."""
    total = run_claude(claude, workdir, env, arm, prompt, model, timeout)
    total["rounds"] = 1
    for _ in range(max_rounds - 1):
        try:
            res = json.loads(_core("aisef_project.py", "next", "--project", ".", "--json", env=env, cwd=workdir))
        except (ValueError, SystemExit):
            break
        if not any(a["kind"] in PENDING_KINDS for a in res["actions"]):
            break
        more = run_claude(claude, workdir, env, arm, CONTINUE_PROMPT, model, timeout)
        total["rounds"] += 1
        for k in ("seconds", "cost_usd", "turns", "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"):
            if more.get(k) is not None:
                total[k] = round((total.get(k) or 0) + more[k], 6)
        total["is_error"] = total["is_error"] or more["is_error"]
    return total


def gateway_counts(workdir, env):
    try:
        out = _core("aisef_project.py", "metrics", "--project", ".", "--json", "--no-check", env=env, cwd=workdir)
        m = json.loads(out)
        return {"gateway_asked": m["noise"]["gateway_asked"], "gateway_denied": m["noise"]["gateway_denied"],
                "approval_requests": m["attention"]["approval_requests"]}
    except SystemExit:
        return {}


def summarize(results):
    rows = {}
    for r in results:
        rows.setdefault((r["task"], r["arm"]), []).append(r)
    lines = ["| Tarefa | Braco | Testes escondidos (media) | Execucoes 100% | Custo US$ (mediana) | Tempo s (mediana) |",
             "|---|---|---|---|---|---|"]
    for (task, arm), rs in sorted(rows.items()):
        rate = statistics.mean(r["hidden"]["passed"] / r["hidden"]["ran"] if r["hidden"]["ran"] else 0 for r in rs)
        full = sum(1 for r in rs if r["hidden"]["ok"])
        cost = [r["claude"]["cost_usd"] for r in rs if r["claude"]["cost_usd"] is not None]
        lines.append("| %s | %s | %d%% | %d/%d | %s | %s |" % (
            task, arm, round(rate * 100), full, len(rs), "%.2f" % statistics.median(cost) if cost else "-",
            statistics.median(r["claude"]["seconds"] for r in rs)))
    by_arm = {}
    for r in results:
        by_arm.setdefault(r["arm"], []).append(r)
    lines += ["", "| Braco | Execucoes 100% | Custo total US$ |", "|---|---|---|"]
    for arm, rs in sorted(by_arm.items()):
        lines.append("| %s | %d/%d | %.2f |" % (arm, sum(1 for r in rs if r["hidden"]["ok"]), len(rs),
                                               sum(r["claude"]["cost_usd"] or 0 for r in rs)))
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check-fixtures", action="store_true")
    p.add_argument("--prepare-only", action="store_true")
    p.add_argument("--run", action="store_true")
    p.add_argument("--tasks", default="")
    p.add_argument("--arms", default="plain,aisef")
    p.add_argument("--reps", type=int, default=3)
    p.add_argument("--model", default="sonnet")
    p.add_argument("--claude", default=shutil.which("claude") or "claude")
    p.add_argument("--timeout", type=int, default=1800)
    p.add_argument("--out", default=os.path.join(ROOT, "docs", "benchmarks"))
    a = p.parse_args(argv)
    tasks = load_tasks(set(filter(None, a.tasks.split(","))))
    if not tasks:
        print("nenhuma tarefa em %s" % BENCH)
        return 1
    if a.check_fixtures:
        problems = check_fixtures(tasks)
        for x in problems:
            print("FALHA " + x)
        print("%d tarefa(s), %d problema(s)" % (len(tasks), len(problems)))
        return 1 if problems else 0
    if a.prepare_only:
        base = tempfile.mkdtemp(prefix="aisef-bench-")
        bad = 0
        for t in tasks:
            prepare(t, "plain", base)
            wd, env = prepare(t, "aisef", base)
            ok, res = aisef_ready(wd, env)
            bad += not ok
            print("%-22s plain ok, aisef %s" % (t["id"], "pronto para despachar" if ok else
                                                "NAO pronto: %s" % [x["kind"] for x in res["actions"]]))
        shutil.rmtree(base, ignore_errors=True)
        return 1 if bad else 0
    if not a.run:
        p.print_help()
        return 0
    arms = [x for x in a.arms.split(",") if x in ("plain", "aisef", "aisef-norev")]
    results = []
    fails_in_row = 0
    base = tempfile.mkdtemp(prefix="aisef-bench-")
    stop = False
    for rep in range(1, a.reps + 1):
        if stop:
            break
        for t in tasks:
            if stop:
                break
            for arm in arms:
                run_base = os.path.join(base, "r%d" % rep)
                os.makedirs(run_base, exist_ok=True)
                wd, env = prepare(t, arm, run_base)
                print("[%d/%d] %s %s ..." % (rep, a.reps, t["id"], arm), flush=True)
                cl = (run_aisef_until_stop if arm.startswith("aisef") else run_claude)(
                    a.claude, wd, env, arm, t["prompt"], a.model, a.timeout)
                vis = visible_cmd(wd)
                res = {"task": t["id"], "kind": t["kind"], "arm": arm, "rep": rep, "claude": cl,
                       "visible": run_tests(wd, vis) if vis else None, "hidden": hidden_result(wd, t)}
                if arm.startswith("aisef"):
                    res["aisef"] = gateway_counts(wd, env)
                    rdir = os.path.join(wd, ".aisef", "reports")
                    res["aisef"]["review_reports"] = len([f for f in os.listdir(rdir) if "-REV-" in f and f.endswith(".json")]) if os.path.isdir(rdir) else 0
                    states = json.loads(_core("aisef_project.py", "next", "--project", ".", "--json", env=env, cwd=wd)).get("states", {})
                    res["aisef"]["task_states"] = states
                res["hidden"].pop("tail", None)
                if res["visible"]:
                    res["visible"].pop("tail", None)
                results.append(res)
                fails_in_row = fails_in_row + 1 if cl["is_error"] and not cl["cost_usd"] else 0
                if fails_in_row >= 3:
                    print("3 execucoes seguidas sem resposta do claude (custo 0): parando. Ultima saida: %r"
                          % (cl.get("stdout_head") or cl["stderr"])[:300], flush=True)
                    stop = True
                    break
                print("    escondidos %d/%d, US$ %s, %ss" % (res["hidden"]["passed"], res["hidden"]["ran"],
                                                          cl["cost_usd"], cl["seconds"]), flush=True)
    os.makedirs(a.out, exist_ok=True)
    stamp = datetime.date.today().isoformat()
    with open(os.path.join(a.out, "outcomes-%s.json" % stamp), "w", encoding="utf-8") as fh:
        json.dump({"model": a.model, "reps": a.reps, "results": results}, fh, indent=2)
    table = summarize(results)
    with open(os.path.join(a.out, "outcomes-%s.md" % stamp), "w", encoding="utf-8") as fh:
        fh.write("# Benchmark de resultado (%s)\n\nModelo: %s. Repeticoes: %d. Gerado por `tools/bench_outcomes.py`.\n\n%s\n"
                 % (stamp, a.model, a.reps, table))
    print(table)
    shutil.rmtree(base, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
