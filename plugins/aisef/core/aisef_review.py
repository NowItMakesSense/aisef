#!/usr/bin/env python3
"""AISEF: escolha dos revisores de uma tarefa e estado das revisoes (roteamento em codigo, nao em prosa).

Revisores por tarefa (so papeis do catalogo; so entram na onda os que tem Agent Contract ATIVO no projeto):
- sempre: code-reviewer;
- revisor da linguagem dos arquivos da tarefa (extensao em paths_allowed; sem extensao, as stacks do architecture.json),
  mais o do framework (django, fastapi) quando detectado;
- touches data ou recurso db_schema: database-reviewer;
- risco high/critical: security (e revisao DUPLA do code-reviewer: dois revisores independentes precisam aprovar);
- estilo de arquitetura adotado, ou touches domain: architecture-reviewer;
- tarefa com TDD (fatias): pr-test-analyzer.

O veredito de cada revisor vem do relatorio de avaliacao dele (`review.verdict` no Execution Report). So APPROVE deixa a
tarefa seguir para o validador; WARNING (achado HIGH) e BLOCK (CRITICAL) voltam ao executor.

Uso:
    python3 -I aisef_review.py plan --project REPO --task T-010     (revisores, ativos e sugeridos)
    python3 -I aisef_review.py status --project REPO --task T-010   (quem aprovou, quem falta, quem reprovou)
"""
import argparse
import fnmatch
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_catalog  # noqa: E402

EXT_REVIEWER = {".py": "python-reviewer", ".pyi": "python-reviewer", ".ts": "typescript-reviewer", ".tsx": "typescript-reviewer",
                ".js": "typescript-reviewer", ".jsx": "typescript-reviewer", ".mjs": "typescript-reviewer",
                ".cjs": "typescript-reviewer", ".go": "go-reviewer", ".rs": "rust-reviewer", ".java": "java-reviewer",
                ".kt": "kotlin-reviewer", ".kts": "kotlin-reviewer", ".swift": "swift-reviewer", ".cs": "csharp-reviewer",
                ".fs": "fsharp-reviewer", ".cpp": "cpp-reviewer", ".cc": "cpp-reviewer", ".cxx": "cpp-reviewer",
                ".hpp": "cpp-reviewer", ".h": "cpp-reviewer", ".php": "php-reviewer", ".rb": "ruby-reviewer",
                ".dart": "flutter-reviewer", ".gd": "gdscript-reviewer"}
STACK_REVIEWER = {"python": "python-reviewer", "typescript": "typescript-reviewer", "javascript": "typescript-reviewer",
                  "go": "go-reviewer", "rust": "rust-reviewer", "java": "java-reviewer", "kotlin": "kotlin-reviewer",
                  "swift": "swift-reviewer", "csharp": "csharp-reviewer", "fsharp": "fsharp-reviewer", "cpp": "cpp-reviewer",
                  "php": "php-reviewer", "ruby": "ruby-reviewer", "flutter": "flutter-reviewer", "dart": "flutter-reviewer",
                  "godot": "gdscript-reviewer", "django": "django-reviewer", "fastapi": "fastapi-reviewer",
                  "react": "react-reviewer", "nextjs": "react-reviewer", "vue": "vue-reviewer", "nuxt": "vue-reviewer"}
FRAMEWORK_REVIEWER = {"django": "django-reviewer", "fastapi": "fastapi-reviewer"}
UI_EXT = {".tsx", ".jsx", ".vue", ".svelte", ".dart", ".html", ".css", ".scss"}
UI_STACKS = {"react", "nextjs", "vue", "nuxt", "angular", "svelte", "flutter", "android", "swift"}
STACK_FIXER = {"typescript": "build-error-resolver", "javascript": "build-error-resolver", "python": "python-build-resolver",
               "django": "django-build-resolver", "go": "go-build-resolver", "rust": "rust-build-resolver",
               "java": "java-build-resolver", "kotlin": "kotlin-build-resolver", "swift": "swift-build-resolver",
               "dart": "dart-build-resolver", "flutter": "dart-build-resolver", "cpp": "cpp-build-resolver",
               "pytorch": "pytorch-build-resolver", "harmonyos": "harmonyos-app-resolver"}
VERDICTS = ("APPROVE", "WARNING", "BLOCK")


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _arch(project):
    p = os.path.join(project, ".aisef", "architecture.json")
    return _load(p) if os.path.isfile(p) else {}


def _paths(task):
    sc = task.get("scope") or {}
    return list(sc.get("paths_allowed") or []) + list(sc.get("exclusive_files") or [])


def stacks_of(project, task):
    """Stacks da tarefa: pelas extensoes dos caminhos; sem extensao util, as do projeto."""
    arch = _arch(project)
    proj = [s["id"] for s in arch.get("stacks", [])]
    exts = {os.path.splitext(p.rstrip("*/"))[1].lower() for p in _paths(task)}
    exts.discard("")
    return proj, exts


def reviewers_for(project, task):
    """Lista ordenada de papeis revisores da tarefa (antes de filtrar por contrato ativo)."""
    proj_stacks, exts = stacks_of(project, task)
    out = ["code-reviewer"]
    langs = [EXT_REVIEWER[e] for e in sorted(exts) if e in EXT_REVIEWER]
    if not langs:
        langs = [STACK_REVIEWER[s] for s in proj_stacks if s in STACK_REVIEWER and s not in FRAMEWORK_REVIEWER
                 and s not in ("react", "nextjs", "vue", "nuxt")]
    out += langs
    if "python-reviewer" in out:
        out += [FRAMEWORK_REVIEWER[s] for s in proj_stacks if s in FRAMEWORK_REVIEWER]
    ui_task = "ui" in (task.get("touches") or []) or exts & UI_EXT
    if ui_task:  # revisores de UI so relatam; o visual continua com o frontend e a autoridade de design
        if set(proj_stacks) & {"react", "nextjs"}:
            out.append("react-reviewer")
        if set(proj_stacks) & {"vue", "nuxt"} or ".vue" in exts:
            out.append("vue-reviewer")
        if set(proj_stacks) & UI_STACKS or exts & UI_EXT:
            out.append("a11y-architect")
    touches = set(task.get("touches") or [])
    resources = set((task.get("permissions") or {}).get("resources") or [])
    if "data" in touches or "db_schema" in resources:
        out.append("database-reviewer")
    risk = (task.get("risk") or {}).get("level", "low")
    if risk in ("high", "critical"):
        out.append("security")
    arch = _arch(project)
    if (arch.get("approved") or {}).get("styles") or "domain" in touches:
        out.append("architecture-reviewer")
    if (task.get("tests") or {}).get("tdd_required"):
        out.append("pr-test-analyzer")
    known = aisef_catalog.role_ids()
    return [r for r in dict.fromkeys(out) if r in known and r != (task.get("assigned_agent") or {}).get("role")]


def dual_review(task):
    return (task.get("risk") or {}).get("level", "low") in ("high", "critical")


def active_roles(project):
    adir = os.path.join(project, ".aisef", "contracts", "agents")
    out = set()
    for name in os.listdir(adir) if os.path.isdir(adir) else []:
        if name.endswith(".json"):
            try:
                doc = _load(os.path.join(adir, name))
            except (OSError, ValueError):
                continue
            if doc.get("status") == "active":
                out.add(doc.get("role") or name[:-5])
    return out


def plan(project, task):
    """Revisores que entram (contrato ativo) e os que faltam ativar. Tarefa sem o campo `review` (anterior ao
    roteamento de revisores) nao ganha revisao nova: `computed` mostra o que seria escolhido."""
    wanted = (task["review"].get("reviewers") or []) if "review" in task else []
    act = active_roles(project)
    return {"reviewers": [r for r in wanted if r in act], "inactive": [r for r in wanted if r not in act],
            "dual": bool((task.get("review") or {}).get("dual_review")), "computed": reviewers_for(project, task)}


def fixer_for(project, task):
    """Corretor de build da stack da tarefa, se o contrato dele estiver ativo."""
    proj_stacks, exts = stacks_of(project, task)
    by_ext = {".py": "python", ".ts": "typescript", ".tsx": "typescript", ".js": "javascript", ".go": "go", ".rs": "rust",
              ".java": "java", ".kt": "kotlin", ".swift": "swift", ".dart": "dart", ".cpp": "cpp", ".cc": "cpp"}
    stacks = [by_ext[e] for e in sorted(exts) if e in by_ext] or proj_stacks
    act = active_roles(project)
    for s in (["django"] if "django" in proj_stacks and "python" in stacks else []) + stacks:
        f = STACK_FIXER.get(s)
        if f and f in act:
            return f
    return None


def status(project, task, reports):
    """Estado das revisoes a partir dos relatorios de avaliacao da versao atual do contrato."""
    p = plan(project, task)
    by_role = {}
    for r in reports:
        rev = r.get("review") or {}
        role = r["agent"].get("role") or r["agent"]["agent_id"]
        if rev.get("verdict") in VERDICTS and r.get("contract_version") == task.get("contract_version"):
            by_role.setdefault(role, []).append(rev["verdict"])
    approved, pending, rejected = [], [], []
    for role in p["reviewers"]:
        need = 2 if (p["dual"] and role == "code-reviewer") else 1
        got = by_role.get(role, [])
        if any(v != "APPROVE" for v in got):
            rejected.append({"role": role, "verdicts": got})
        elif len(got) >= need:
            approved.append(role)
        else:
            pending.append({"role": role, "missing": need - len(got)})
    return {"approved": approved, "pending": pending, "rejected": rejected, "inactive": p["inactive"], "dual": p["dual"]}


def record(project, task_id, role, verdict, counts, summary, findings_text="", model=None, effort=None, level=None, suffix=""):
    """Grava o relatorio de avaliacao do revisor (o revisor nao tem Write: chama isto via `python -I`, sem editar codigo).
    Gera o JSON valido pelo schema execution-report, com `review`, e o relatorio legivel com hash."""
    import datetime
    import hashlib
    if verdict not in VERDICTS:
        raise SystemExit("veredito invalido: %s (use %s)" % (verdict, "/".join(VERDICTS)))
    if role not in aisef_catalog.evaluator_roles():
        raise SystemExit("%s nao e papel avaliador do catalogo" % role)
    if verdict == "APPROVE" and (counts.get("critical") or counts.get("high")):
        raise SystemExit("APPROVE nao combina com achado CRITICAL ou HIGH (use WARNING ou BLOCK)")
    adir = os.path.join(project, ".aisef")
    task = _load(os.path.join(adir, "contracts", "tasks", task_id + ".json"))
    rid = "RPT-%s-REV-%s%s" % (task_id, role, suffix)
    now = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")
    md_rel = "reports/%s.md" % rid
    md = "# Revisao %s de %s\n\nVeredito: **%s**\n\nAchados: %s\n\n%s\n\n%s\n" % (
        role, task_id, verdict, ", ".join("%s %d" % (k, v) for k, v in counts.items()), summary, findings_text)
    os.makedirs(os.path.join(adir, "reports"), exist_ok=True)
    with open(os.path.join(adir, md_rel), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(md)
    doc = {"schema_version": "0.1.0", "report_id": rid, "task_id": task_id, "contract_version": task["contract_version"],
           "feature_id": task["feature_id"],
           "agent": {"agent_id": role, "agent_contract_version": 1, "role": role},
           "status": "executed", "timing": {"started_at": now, "finished_at": now},
           "attempts": {"fix_attempts_used": 0, "specialist_consultations_used": 0},
           "files": {"created": [], "modified": [], "deleted": []},
           "changes": [{"summary": "revisao %s: %s" % (role, verdict), "reason": summary[:200] or "revisao"}],
           "tests": {"executed": 0, "passed": 0, "failed": 0, "skipped": 0},
           "evidence": [{"id": "EV-REV", "type": "report", "ref": md_rel, "secrets_redacted": True}],
           "criteria_results": [{"criterion_id": c["id"], "required": c.get("required", True), "result": "not_verifiable", "evidence_ids": [], "notes": "revisao: o criterio e verificado pelo validador"} for c in task["acceptance_criteria"]], "problems": [], "risks": [], "pending": [], "limitations": [],
           "intervention": {"needed": False},
           "technical_report": {"ref": md_rel, "sha256": hashlib.sha256(md.encode("utf-8")).hexdigest()},
           "integrity": {"created_at": now, "event_log_ref": "audit/log.jsonl"},
           "review": {"verdict": verdict, "findings": {k: int(counts.get(k, 0)) for k in ("critical", "high", "medium", "low")}}}
    if model:
        doc["execution_profile"] = {"model": model, "effort": effort or "medium", "level": int(level or 0)}
    try:
        import jsonschema
        with open(os.path.join(HERE, "execution-report.schema.v0.1.json"), encoding="utf-8") as fh:
            errs = sorted(jsonschema.Draft202012Validator(json.load(fh)).iter_errors(doc), key=lambda e: list(e.path))
        if errs:
            raise SystemExit("relatorio invalido: " + "; ".join("%s: %s" % ("/".join(map(str, e.path)), e.message) for e in errs[:5]))
    except ImportError:
        pass
    with open(os.path.join(adir, "reports", rid + ".json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    return rid


def main(argv=None):
    import aisef_dispatch as dsp
    ap = argparse.ArgumentParser(description="AISEF: revisores por tarefa")
    ap.add_argument("command", choices=["plan", "status", "record"])
    ap.add_argument("--project", default=".")
    ap.add_argument("--task", required=True)
    ap.add_argument("--role", help="record: papel do revisor (ex.: code-reviewer)")
    ap.add_argument("--verdict", choices=VERDICTS, help="record: APPROVE | WARNING | BLOCK")
    for k in ("critical", "high", "medium", "low"):
        ap.add_argument("--" + k, type=int, default=0)
    ap.add_argument("--summary", default="", help="record: resumo de uma ou duas frases")
    ap.add_argument("--findings-file", help="record: arquivo com a tabela de achados (texto); opcional")
    ap.add_argument("--suffix", default="", help="record: -A ou -B na revisao dupla")
    ap.add_argument("--model")
    ap.add_argument("--effort")
    ap.add_argument("--level", type=int)
    a = ap.parse_args(argv)
    project = os.path.abspath(a.project)
    if a.command == "record":
        if not (a.role and a.verdict):
            ap.error("record exige --role e --verdict")
        text = ""
        if a.findings_file:
            with open(a.findings_file, encoding="utf-8") as fh:
                text = fh.read()
        rid = record(project, a.task, a.role, a.verdict, {k: getattr(a, k) for k in ("critical", "high", "medium", "low")},
                     a.summary, text, a.model, a.effort, a.level, a.suffix)
        print("gravado .aisef/reports/%s.json" % rid)
        return 0
    task = _load(os.path.join(project, ".aisef", "contracts", "tasks", a.task + ".json"))
    out = plan(project, task) if a.command == "plan" else status(project, task, dsp._reports(project, a.task))
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
