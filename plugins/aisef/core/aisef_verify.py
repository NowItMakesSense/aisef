#!/usr/bin/env python3
"""AISEF verify-loop: verificacao antes de entregar (ideia do verification-loop do ECC), com relatorio PASS/FAIL.

Fases, na ordem: build -> typecheck -> lint -> test (comandos por stack de .aisef/architecture.json, ou detectados na
hora) -> segredos (linhas adicionadas no diff) -> diff (resumo). Ferramenta ausente vira SKIP, nao falha. Os comandos
vem do mapeamento de stacks do plugin (core/detect/stacks.v0.1.json) ou de `.aisef/config.json` -> "verify":
{"<stack>": {"test": "..."}}; nunca de entrada do modelo.

Uso:
    python3 -I aisef_verify.py --project REPO [--only build,test] [--task T-010] [--json] [--timeout 600]
    (--task grava o relatorio em .aisef/evidence/VERIFY-<T>.json para citar como evidencia; sai 1 se alguma fase falhar)
"""
import argparse
import datetime
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_detect  # noqa: E402

PHASES = ("build", "typecheck", "lint", "test")
# Padroes de segredo no diff (so linhas adicionadas). O valor nunca e impresso: so arquivo, linha e o tipo.
SECRET_RES = [
    ("chave AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("chave privada", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("token GitHub", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("token Slack", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("chave Google", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("chave de API (sk-)", re.compile(r"\bsk-(?:ant-|proj-|live_|test_)?[A-Za-z0-9_\-]{20,}")),
    ("senha no codigo", re.compile(r"""(?i)\b(?:password|passwd|senha|secret|api_?key|token)\s*[:=]\s*['"][^'"\s]{8,}['"]""")),
    ("URL com credencial", re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]{3,}@")),
]
PLACEHOLDER = re.compile(r"(?i)example|exemplo|changeme|placeholder|dummy|fake|xxx|<[^>]+>|\$\{|os\.environ|process\.env|getenv")


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


def commands(project):
    """{stack: {fase: comando}} do architecture.json (ou detectado na hora), sobrescrito por config.json -> verify."""
    path = os.path.join(project, ".aisef", "architecture.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            cmds = json.load(fh).get("commands") or {}
    else:
        cmds = aisef_detect.detect(project)["commands"]
    cfg = os.path.join(project, ".aisef", "config.json")
    if os.path.exists(cfg):
        with open(cfg, encoding="utf-8") as fh:
            for stack, over in (json.load(fh).get("verify") or {}).items():
                cmds.setdefault(stack, {}).update(over)
    return cmds


def tool_missing(cmd):
    first = shlex.split(cmd, posix=os.name != "nt")[0].strip("\"'") if cmd.strip() else ""
    if first.startswith(("./", ".\\")):
        return False  # wrapper do projeto (./mvnw, ./gradlew): roda e o resultado diz
    if os.path.isabs(first):
        return not os.path.exists(first)
    return shutil.which(first) is None


def run(cmd, project, timeout):
    if tool_missing(cmd):
        return {"command": cmd, "result": "SKIP", "why": "ferramenta nao encontrada no PATH"}
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=project, shell=True, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"command": cmd, "result": "FAIL", "exit_code": None, "seconds": timeout, "tail": "tempo esgotado"}
    out = (r.stdout + r.stderr).strip().splitlines()
    return {"command": cmd, "result": "PASS" if r.returncode == 0 else "FAIL", "exit_code": r.returncode,
            "seconds": round(time.time() - t0, 1), "tail": "\n".join(out[-15:])[-1500:]}


def git(project, *args):
    try:
        r = subprocess.run(["git", *args], cwd=project, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=60)
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def secret_scan(project):
    diff = git(project, "diff", "--unified=0", "--no-color", "HEAD")
    if diff is None:
        return {"result": "SKIP", "why": "sem git ou sem HEAD", "findings": []}
    findings, cur, line = [], None, 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            cur = raw[6:] if raw.startswith("+++ b/") else None
        elif raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            line = int(m.group(1)) if m else 0
        elif raw.startswith("+") and cur:
            for label, rx in SECRET_RES:
                m = rx.search(raw)
                if m and not PLACEHOLDER.search(raw):
                    findings.append({"file": cur, "line": line, "kind": label})
                    break
            line += 1
    return {"result": "FAIL" if findings else "PASS", "findings": findings[:50]}


def diff_summary(project):
    stat = git(project, "diff", "--shortstat", "HEAD")
    untracked = git(project, "ls-files", "--others", "--exclude-standard")
    if stat is None:
        return {"result": "SKIP", "why": "sem git ou sem HEAD"}
    return {"result": "PASS", "shortstat": stat.strip() or "sem mudancas rastreadas",
            "untracked": len([x for x in (untracked or "").splitlines() if x])}


def verify(project, only=None, timeout=600):
    project = os.path.abspath(project)
    cmds = commands(project)
    phases = [p for p in PHASES if not only or p in only]
    steps = []
    for phase in phases:
        seen = set()
        for stack, c in sorted(cmds.items()):
            cmd = c.get(phase)
            if not cmd or cmd in seen:
                continue
            seen.add(cmd)
            steps.append(dict(run(cmd, project, timeout), phase=phase, stack=stack))
    if not only or "secrets" in only:
        steps.append(dict(secret_scan(project), phase="secrets"))
    if not only or "diff" in only:
        steps.append(dict(diff_summary(project), phase="diff"))
    failed = [s for s in steps if s["result"] == "FAIL"]
    ran = [s for s in steps if s["result"] != "SKIP" and s["phase"] in PHASES]
    verdict = "FAIL" if failed else ("PASS" if ran else "INCOMPLETE")
    return {"generated_at": now_iso(), "verdict": verdict, "steps": steps,
            "note": None if ran or failed else "nenhum comando de build/tipos/lint/teste rodou: configure em .aisef/config.json -> verify"}


def render(rep):
    out = ["verify-loop: %s" % rep["verdict"]]
    for s in rep["steps"]:
        what = s.get("command") or s.get("shortstat") or ("%d achado(s)" % len(s.get("findings", [])) if "findings" in s else "")
        out.append("  %-9s %-5s %s%s" % (s["phase"], s["result"], what, " (%s)" % s["why"] if s.get("why") else ""))
        if s["result"] == "FAIL" and s.get("tail"):
            out += ["      " + x for x in s["tail"].splitlines()[-6:]]
        for f in s.get("findings", [])[:10]:
            out.append("      %s:%d %s (valor omitido)" % (f["file"], f["line"], f["kind"]))
    if rep.get("note"):
        out.append(rep["note"])
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="AISEF verify-loop")
    ap.add_argument("--project", default=".")
    ap.add_argument("--only", default="", help="fases separadas por virgula: build,typecheck,lint,test,secrets,diff")
    ap.add_argument("--task", help="grava .aisef/evidence/VERIFY-<task>.json")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    only = {x for x in a.only.split(",") if x} or None
    rep = verify(a.project, only, a.timeout)
    if a.task:
        rep["task_id"] = a.task
        path = os.path.join(os.path.abspath(a.project), ".aisef", "evidence", "VERIFY-%s.json" % a.task)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(rep, fh, ensure_ascii=False, indent=2)
        print("relatorio: " + os.path.relpath(path, os.path.abspath(a.project)).replace(os.sep, "/"), file=sys.stderr)
    print(json.dumps(rep, ensure_ascii=False, indent=2) if a.json else render(rep))
    return 1 if rep["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
