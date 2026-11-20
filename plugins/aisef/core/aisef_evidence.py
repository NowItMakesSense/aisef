#!/usr/bin/env python3
"""AISEF evidence (0.15, T-02): pacote de evidencia de uma feature, para auditoria e compliance.

    python -I aisef_evidence.py build  --project . --feature FEAT-001 --out <pasta>
    python -I aisef_evidence.py verify --pack <pasta>          (sem o projeto, so com o pacote)

O pacote junta o que prova a mudanca: Feature Contract (requisitos, spec, RTM, triagem), Task Contracts, Execution
Reports, pedidos e decisoes do Approval Center, os eventos assinados da feature (registros completos do log, com hash e
assinatura Ed25519), as chaves publicas, o resultado do verify do log inteiro e do aisef-check, e uma tabela de
controles: SOC 2 CC8.1 (gestao de mudancas) e ISO/IEC 27001:2022 A.8.32 (gestao de mudancas) e A.5.3 (segregacao de
funcoes), cada um com o status calculado e onde esta a evidencia.

Ele se verifica sozinho: `manifest.json` tem o sha256 de cada arquivo; `verify` recalcula os hashes, recalcula o hash
de cada evento a partir do conteudo e confere a assinatura com a chave publica do pacote. Nao e certificacao: e o
material que o auditor pede, organizado e verificavel.
"""
import argparse
import datetime
import glob
import hashlib
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import audit_chain  # noqa: E402

POLICY = os.path.join(HERE, "permission-policy.v0.1.json")
DEFAULTS = os.path.join(HERE, "orchestration-defaults.v0.1.json")


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def controls(feat, tasks, reports, approvals, events):
    """Tabela de controles com status (met, partial, missing) e onde esta a evidencia."""
    fid = feat["feature_id"]
    plan_ok = (feat.get("approval", {}).get("plan") or {}).get("status") == "approved" or any(
        a.get("request_type") == "plan_approval" and a.get("status") == "approved" for a in approvals)
    accepted = any(a.get("request_type") == "feature_acceptance" and a.get("status") == "approved" for a in approvals) or \
        any(e.get("event_type") == "feature_accepted" for e in events)
    done = [t for t in tasks if (t.get("state") or {}).get("status") in ("completed", "validated")]
    validated_ids = {e.get("task_id") for e in events if e.get("event_type") == "task_validated"}
    tested = [t for t in tasks if any(r.get("task_id") == t["task_id"] and ((r.get("tests") or {}).get("passed") or 0) > 0
                                      for r in reports)]
    tdd = [t for t in tasks if any(r.get("task_id") == t["task_id"] and r.get("tdd_evidence") for r in reports)]
    executors = {e.get("task_id"): e["actor"]["id"] for e in events if e.get("event_type") == "task_executed"}
    validators = {e.get("task_id"): e["actor"]["id"] for e in events if e.get("event_type") == "task_validated"}
    sod_bad = [tid for tid, v in validators.items() if executors.get(tid) == v]
    rtm_ok = bool(feat.get("rtm")) and all(r.get("task_ids") and r.get("criterion_ids") for r in feat["rtm"])
    n = len(tasks)

    def st(ok, part=False):
        return "met" if ok else ("partial" if part else "missing")

    return [
        {"framework": "SOC 2", "control": "CC8.1", "title": "Mudancas autorizadas, documentadas, testadas e aprovadas",
         "checks": [
             {"what": "autorizacao antes da execucao (plano aprovado pelo usuario)", "status": st(plan_ok),
              "evidence": "approvals/ (plan_approval) e o evento approval_granted em audit/events.jsonl"},
             {"what": "documentacao (requisitos com origem, spec e RTM)", "status": st(rtm_ok),
              "evidence": "feature/%s.json (requirements, spec, rtm)" % fid},
             {"what": "testes (relatorios com testes que passaram; TDD quando exigido)",
              "status": st(n and len(tested) == n, bool(tested)),
              "evidence": "reports/ (tests, tdd_evidence): %d de %d tarefa(s) com testes, %d com TDD" % (len(tested), n, len(tdd))},
             {"what": "aprovacao da entrega (validacao independente e aceite do usuario)",
              "status": st(accepted and n and len(validated_ids & {t["task_id"] for t in tasks}) == n, bool(validated_ids)),
              "evidence": "eventos task_validated e feature_accepted em audit/events.jsonl"}]},
        {"framework": "ISO/IEC 27001:2022", "control": "A.8.32", "title": "Gestao de mudancas",
         "checks": [
             {"what": "mudanca segue procedimento definido (fluxo do AISEF: plano, execucao, validacao, aceite)",
              "status": st(plan_ok and accepted, plan_ok),
              "evidence": "feature/%s.json (state), approvals/, audit/events.jsonl" % fid},
             {"what": "rastreabilidade requisito -> tarefa -> criterio -> evidencia", "status": st(rtm_ok),
              "evidence": "feature/%s.json (rtm), tasks/, reports/" % fid},
             {"what": "registro integro e assinado de cada passo", "status": "met" if events else "missing",
              "evidence": "audit/events.jsonl (hash e Ed25519 de cada evento), keys/"}]},
        {"framework": "ISO/IEC 27001:2022", "control": "A.5.3", "title": "Segregacao de funcoes",
         "checks": [
             {"what": "quem executou nao validou", "status": st(validators and not sod_bad, False) if validators else "missing",
              "evidence": "atores de task_executed x task_validated em audit/events.jsonl%s"
                          % (" (violado em %s)" % ", ".join(sod_bad) if sod_bad else "")},
             {"what": "decisoes do Approval Center registradas pelo usuario", "status": st(all(
                 e["actor"]["type"] == "user" for e in events if e.get("event_type") in ("approval_granted", "feature_accepted"))),
              "evidence": "eventos approval_granted e feature_accepted (actor user)"}]},
        {"framework": "AISEF", "control": "DONE", "title": "Tarefas concluidas",
         "checks": [{"what": "tarefas concluidas ou validadas", "status": st(n and len(done) == n, bool(done)),
                     "evidence": "%d de %d" % (len(done), n)}]},
    ]


def build(project, feature_id, out, now=None):
    root = os.path.join(project, ".aisef")
    fpath = os.path.join(root, "contracts", "features", feature_id + ".json")
    if not os.path.exists(fpath):
        raise SystemExit("feature %s nao existe" % feature_id)
    if os.path.exists(out) and os.listdir(out):
        raise SystemExit("%s ja existe e nao esta vazia" % out)
    feat = _load(fpath)
    tids = {i["task_id"] for i in feat.get("task_plan", [])}
    tasks = [t for t in (_load(p) for p in sorted(glob.glob(os.path.join(root, "contracts", "tasks", "*.json"))))
             if t.get("task_id") in tids]
    reports = [r for r in (_load(p) for p in sorted(glob.glob(os.path.join(root, "reports", "*.json"))))
               if r.get("task_id") in tids]
    approvals = [a for a in (_load(p) for p in sorted(glob.glob(os.path.join(root, "approvals", "*.json"))))
                 if a.get("feature_id") == feature_id]
    log = audit_chain.read_log_dir(os.path.join(root, "audit"))
    events = [e for e in log if e.get("feature_id") == feature_id or e.get("task_id") in tids]

    import aisef_project
    import check_project
    verr, vwarn = aisef_project.verify(project)
    rep = check_project.check(project, policy_path=POLICY, defaults_path=DEFAULTS, now=now)

    _write(os.path.join(out, "feature", feature_id + ".json"), feat)
    for t in tasks:
        _write(os.path.join(out, "tasks", t["task_id"] + ".json"), t)
    for r in reports:
        _write(os.path.join(out, "reports", (r.get("report_id") or r["task_id"]) + ".json"), r)
    for a in approvals:
        _write(os.path.join(out, "approvals", a["request_id"] + ".json"), a)
    os.makedirs(os.path.join(out, "audit"), exist_ok=True)
    with open(os.path.join(out, "audit", "events.jsonl"), "w", encoding="utf-8", newline="\n") as fh:
        for e in events:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    for pem in glob.glob(os.path.join(root, "keys", "*.pem")):
        os.makedirs(os.path.join(out, "keys"), exist_ok=True)
        shutil.copy(pem, os.path.join(out, "keys", os.path.basename(pem)))
    ctl = controls(feat, tasks, reports, approvals, events)
    _write(os.path.join(out, "controls.json"), ctl)
    _write(os.path.join(out, "checks.json"), {
        "log_verify": {"errors": verr, "warnings": vwarn},
        "aisef_check": {"errors": rep.count("error"), "warnings": rep.count("warning"),
                        "findings": [f for f in rep.findings if f["severity"] == "error"][:50]}})
    with open(os.path.join(out, "README.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render(feat, tasks, events, ctl, verr, rep))
    files = sorted(os.path.relpath(os.path.join(dp, f), out).replace("\\", "/")
                   for dp, _d, fs in os.walk(out) for f in fs)
    _write(os.path.join(out, "manifest.json"), {
        "feature_id": feature_id, "project_id": (aisef_project.load_config(project) or {}).get("project_id"),
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "files": {f: _sha(os.path.join(out, f)) for f in files}})
    return out


def render(feat, tasks, events, ctl, verr, rep):
    icon = {"met": "atendido", "partial": "parcial", "missing": "faltando"}
    L = ["# Pacote de evidência: %s" % feat["feature_id"], "", "**%s**: %s" % (feat.get("title"), feat.get("objective")), "",
         "- Requisitos: %d; tarefas: %d; eventos assinados da feature: %d" % (len(feat.get("requirements", [])), len(tasks), len(events)),
         "- Log assinado do projeto: %s" % ("íntegro" if not verr else "COM ERROS: " + "; ".join(verr[:3])),
         "- aisef-check: %d erro(s), %d aviso(s)" % (rep.count("error"), rep.count("warning")), "",
         "Verifique este pacote sem o projeto: `python -I <plugin>/core/aisef_evidence.py verify --pack <esta pasta>`.", "",
         "## Controles", "", "| Framework | Controle | Verificação | Status | Evidência |", "|---|---|---|---|---|"]
    for c in ctl:
        for k in c["checks"]:
            L.append("| %s | %s %s | %s | %s | %s |" % (c["framework"], c["control"], c["title"], k["what"], icon[k["status"]],
                                                     k["evidence"]))
    L += ["", "Mapeamento indicativo para apoiar a auditoria; não substitui a avaliação do auditor."]
    return "\n".join(L) + "\n"


def verify(pack):
    """Problemas do pacote (lista vazia = integro e autentico)."""
    out = []
    try:
        man = _load(os.path.join(pack, "manifest.json"))
    except (OSError, ValueError):
        return ["manifest.json ausente ou ilegivel"]
    present = sorted(os.path.relpath(os.path.join(dp, f), pack).replace("\\", "/")
                     for dp, _d, fs in os.walk(pack) for f in fs if f != "manifest.json")
    for f in present:
        if f not in man["files"]:
            out.append("arquivo fora do manifesto: %s" % f)
    for f, h in man["files"].items():
        p = os.path.join(pack, f)
        if not os.path.exists(p):
            out.append("arquivo do manifesto ausente: %s" % f)
        elif _sha(p) != h:
            out.append("arquivo alterado: %s" % f)
    try:
        import audit_signing
        from cryptography.hazmat.primitives import serialization
        pubs = {}
        for pem in glob.glob(os.path.join(pack, "keys", "*.pem")):
            with open(pem, "rb") as fh:
                pubs[os.path.basename(pem)[:-4]] = serialization.load_pem_public_key(fh.read())
        ver = audit_signing.AuditVerifier(pubs)
    except ImportError:
        return out + ["a verificacao das assinaturas precisa da biblioteca cryptography"]
    try:
        with open(os.path.join(pack, "audit", "events.jsonl"), encoding="utf-8") as fh:
            events = [json.loads(line) for line in fh if line.strip()]
    except (OSError, ValueError):
        return out + ["audit/events.jsonl ausente ou ilegivel"]
    for e in events:
        where = "evento %s" % e.get("event_id")
        if audit_chain.compute_hash(e) != e.get("hash"):
            out.append(where + ": conteudo nao confere com o hash")
            continue
        sig = e.get("signature") or {}
        problem = ver._check(sig.get("key_id"), sig.get("value", ""),
                             audit_signing._event_message(e.get("log_id"), e.get("sequence"), e.get("hash", "")))
        if problem:
            out.append(where + ": " + problem)
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["build", "verify"])
    p.add_argument("--project", default=".")
    p.add_argument("--feature")
    p.add_argument("--out")
    p.add_argument("--pack")
    p.add_argument("--now", help="relogio do aisef-check (ISO 8601), para projetos com datas fixas")
    a = p.parse_args(argv)
    if a.command == "build":
        if not (a.feature and a.out):
            p.error("build pede --feature e --out")
        print("pacote em %s" % build(os.path.abspath(a.project), a.feature, os.path.abspath(a.out), a.now))
        return 0
    if not a.pack:
        p.error("verify pede --pack")
    problems = verify(os.path.abspath(a.pack))
    for x in problems:
        print("ERRO " + x)
    print("pacote: %d problema(s)" % len(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
