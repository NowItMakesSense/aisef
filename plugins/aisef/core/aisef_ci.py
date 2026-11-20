#!/usr/bin/env python3
"""AISEF CI (0.15, T-01): a verificacao que a GitHub Action aisef-verify roda numa PR. Sem chave privada.

    python -I aisef_ci.py --project . [--pr --base origin/main] [--summary $GITHUB_STEP_SUMMARY] [--json]

Falha (sai 1) quando:
- o log assinado nao confere: cadeia de hash, assinaturas Ed25519 com as chaves PUBLICAS de .aisef/keys/ e o head
  versionado (.aisef/audit/head.json), que detecta corte no fim do log;
- o aisef-check acusa erro (com --strict, tambem aviso);
- com --pr:
  * o log da PR nao contem o ultimo evento do log da branch base, com o mesmo hash (o log so cresce: cortar o fim e
    restaurar um head.json antigo, que tem assinatura valida, e pego aqui);
  * a PR toca uma tarefa (contrato ou arquivo do escopo dela) que esta executada mas nao validada.
O resumo em markdown vai para --summary (o GITHUB_STEP_SUMMARY da Action). Somente stdlib + jsonschema/cryptography.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_project as ap  # noqa: E402
import audit_chain  # noqa: E402

DEFAULTS = os.path.join(HERE, "orchestration-defaults.v0.1.json")
POLICY = os.path.join(HERE, "permission-policy.v0.1.json")


def verify_log(project):
    """(erros, avisos) do log com as chaves publicas e o head versionado do projeto."""
    root = ap.aisef_dir(project)
    log = audit_chain.read_log_dir(os.path.join(root, "audit"))
    if not log:
        return ["sem log em .aisef/audit/"], []
    try:
        import audit_signing
        from cryptography.hazmat.primitives import serialization
    except ImportError:
        return ["a verificacao no CI precisa da biblioteca cryptography (pip install cryptography)"], []
    pubs = {}
    kdir = os.path.join(root, "keys")
    for name in sorted(os.listdir(kdir)) if os.path.isdir(kdir) else []:
        if name.endswith(".pem"):
            with open(os.path.join(kdir, name), "rb") as fh:
                pubs[name[:-4]] = serialization.load_pem_public_key(fh.read())
    if not pubs:
        return ["sem chave publica em .aisef/keys/: o log nao pode ser verificado"], []
    head = None
    hp = os.path.join(root, "audit", "head.json")
    if os.path.exists(hp):
        with open(hp, encoding="utf-8") as fh:
            head = json.load(fh)
    errors, warnings = audit_signing.AuditVerifier(pubs).verify(log, head)
    if head is None:
        errors.append("sem .aisef/audit/head.json versionado: corte no fim do log nao seria detectado")
    return errors, warnings


def git(project, *args):
    r = subprocess.run(["git", "-C", project] + list(args), capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def append_only(project, base):
    """O ultimo evento do log da base continua no log da PR, com o mesmo hash?"""
    raw = git(project, "show", "%s:.aisef/audit/head.json" % base)
    if raw is None:
        return [], ["a base %s nao tem .aisef/audit/head.json: nada a comparar" % base]
    try:
        bh = json.loads(raw)
    except ValueError:
        return ["head.json da base %s ilegivel" % base], []
    log = audit_chain.read_log_dir(os.path.join(ap.aisef_dir(project), "audit"))
    ev = next((e for e in log if e.get("sequence") == bh.get("sequence")), None)
    if ev is None:
        return ["o log da PR nao tem mais o evento %s da base (o log foi cortado)" % bh.get("sequence")], []
    if ev.get("hash") != bh.get("hash"):
        return ["o evento %s da base foi reescrito na PR (hash diferente)" % bh.get("sequence")], []
    return [], []


def touched_tasks(project, base):
    """Tarefas tocadas pela PR: o contrato mudou ou um arquivo do escopo dela mudou."""
    out = git(project, "diff", "--name-only", "%s...HEAD" % base)
    if out is None:
        return None
    files = [f.strip() for f in out.splitlines() if f.strip()]
    import aisef_sysgraph
    hit = set()
    for f in files:
        if f.startswith(".aisef/contracts/tasks/") and f.endswith(".json"):
            hit.add(os.path.basename(f)[:-5])
        elif not f.startswith(".aisef/"):
            hit.update(t["task_id"] for t in aisef_sysgraph.impact_file(project, f)["tasks"])
    return sorted(hit), files


def unvalidated(project, tids):
    """Tarefas executadas sem validacao (estado efetivo do log)."""
    import aisef_next
    res = aisef_next.compute_next(project, git_state={"current": None, "branches": None})
    return [t for t in tids if res["states"].get(t) == "executed"]


def run(project, pr=False, base="origin/main", strict=True, now=None):
    rep = {"log_errors": [], "log_warnings": [], "check_errors": [], "check_warnings": [], "pr": None}
    rep["log_errors"], rep["log_warnings"] = verify_log(project)
    import check_project
    c = check_project.check(project, policy_path=POLICY, defaults_path=DEFAULTS, now=now)
    rep["check_errors"] = ["%s %s: %s" % (f["rule"], f["where"], f["message"]) for f in c.findings if f["severity"] == "error"]
    rep["check_warnings"] = ["%s %s: %s" % (f["rule"], f["where"], f["message"]) for f in c.findings if f["severity"] == "warning"]
    if pr:
        e, w = append_only(project, base)
        tt = touched_tasks(project, base)
        rep["pr"] = {"base": base, "append_only_errors": e, "notes": w,
                     "touched_tasks": tt[0] if tt else [], "files": len(tt[1]) if tt else 0,
                     "unvalidated": unvalidated(project, tt[0]) if tt else []}
        if tt is None:
            rep["pr"]["notes"].append("git diff contra %s falhou: faca o checkout com fetch-depth: 0" % base)
    fail = bool(rep["log_errors"] or rep["check_errors"] or (strict and rep["check_warnings"]) or
                (rep["pr"] and (rep["pr"]["append_only_errors"] or rep["pr"]["unvalidated"])))
    rep["ok"] = not fail
    return rep


def markdown(rep):
    ok = lambda b: "✅" if b else "❌"  # noqa: E731
    L = ["## AISEF verify %s" % ("✅ ok" if rep["ok"] else "❌ falhou"), "",
         "| Verificação | Resultado |", "|---|---|",
         "| Log assinado (cadeia, Ed25519, head) | %s %s |" % (ok(not rep["log_errors"]), "; ".join(rep["log_errors"][:3]) or "íntegro"),
         "| aisef-check | %s %d erro(s), %d aviso(s) |" % (ok(not rep["check_errors"]), len(rep["check_errors"]), len(rep["check_warnings"]))]
    if rep["pr"]:
        p = rep["pr"]
        L.append("| Log só cresce desde %s | %s %s |" % (p["base"], ok(not p["append_only_errors"]),
                                                       "; ".join(p["append_only_errors"]) or "sim"))
        L.append("| Tarefas tocadas validadas | %s %s |" % (ok(not p["unvalidated"]), (
            "sem validação: " + ", ".join(p["unvalidated"])) if p["unvalidated"] else (", ".join(p["touched_tasks"]) or "nenhuma tocada")))
    for title, items in (("Erros do check", rep["check_errors"]), ("Avisos do check", rep["check_warnings"])):
        if items:
            L += ["", "### %s" % title, ""] + ["- %s" % x for x in items[:30]]
    return "\n".join(L) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project", default=".")
    p.add_argument("--pr", action="store_true")
    p.add_argument("--base", default="origin/main")
    p.add_argument("--no-strict", action="store_true", help="avisos do check nao falham")
    p.add_argument("--summary")
    p.add_argument("--now", help="relogio do check (ISO 8601), para projetos de demonstracao com datas fixas")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    rep = run(os.path.abspath(a.project), a.pr, a.base, not a.no_strict, a.now)
    md = markdown(rep)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # console do Windows (cp1252) e os emojis do resumo
    except (AttributeError, ValueError):
        pass
    if a.summary:
        with open(a.summary, "a", encoding="utf-8") as fh:
            fh.write(md)
    print(json.dumps(rep, ensure_ascii=False, indent=2) if a.json else md)
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
