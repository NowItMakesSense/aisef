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
                ".dart": "flutter-reviewer", ".gd": "gdscript-reviewer", ".vue": "vue-reviewer"}
STACK_REVIEWER = {"python": "python-reviewer", "typescript": "typescript-reviewer", "javascript": "typescript-reviewer",
                  "go": "go-reviewer", "rust": "rust-reviewer", "java": "java-reviewer", "kotlin": "kotlin-reviewer",
                  "swift": "swift-reviewer", "csharp": "csharp-reviewer", "fsharp": "fsharp-reviewer", "cpp": "cpp-reviewer",
                  "php": "php-reviewer", "ruby": "ruby-reviewer", "flutter": "flutter-reviewer", "dart": "flutter-reviewer",
                  "godot": "gdscript-reviewer", "django": "django-reviewer", "fastapi": "fastapi-reviewer",
                  "react": "react-reviewer", "nextjs": "react-reviewer", "vue": "vue-reviewer", "nuxt": "vue-reviewer"}
FRAMEWORK_REVIEWER = {"django": "django-reviewer", "fastapi": "fastapi-reviewer"}
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


def main(argv=None):
    import aisef_dispatch as dsp
    ap = argparse.ArgumentParser(description="AISEF: revisores por tarefa")
    ap.add_argument("command", choices=["plan", "status"])
    ap.add_argument("--project", default=".")
    ap.add_argument("--task", required=True)
    a = ap.parse_args(argv)
    project = os.path.abspath(a.project)
    task = _load(os.path.join(project, ".aisef", "contracts", "tasks", a.task + ".json"))
    out = plan(project, task) if a.command == "plan" else status(project, task, dsp._reports(project, a.task))
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
