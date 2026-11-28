#!/usr/bin/env python3
"""Testes da A-01: autorizacao de escopo deixa de ficar 'active' quando a feature e aceita ou quando vence.
Antes, `termination_condition` era so declarativo: nada encerrava a autorizacao, e o aisef-check acusava AUTH-EXPIRED."""
import datetime
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
work = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
os.environ["AISEF_HOME"] = os.path.join(work, "home")
import aisef_auth_life as life  # noqa: E402
import aisef_project as ap  # noqa: E402
import check_project as cp  # noqa: E402

POL = os.path.join(HERE, "permission-policy.v0.1.json")
DEF = os.path.join(HERE, "orchestration-defaults.v0.1.json")
fails = total = 0
NOW = datetime.datetime(2026, 11, 27, 22, 0, tzinfo=datetime.timezone.utc)


def check(name, cond, extra=None):
    global fails, total
    total += 1
    print(("OK    " if cond else "FALHA ") + name + ("" if cond or extra is None else "  -> %s" % (extra,)))
    fails += not cond


def auth(aid, fid, until):
    return {"schema_version": "0.1.0", "kind": "scope", "authorization_id": aid, "project_id": "PRJ-L", "feature_id": fid,
            "cycle": 1, "environment": "dev", "resources": ["repo_code"], "operations": ["edit_files"],
            "excludes_destructive_operations": True, "limits": {"max_operations": 100},
            "validity": {"valid_from": "2026-11-20T10:00:00+00:00", "valid_until": until},
            "termination_condition": ["expiry", "feature_accepted"],
            "stop_conditions": ["scope_exceeded", "environment_changed", "unexpected_risk", "architectural_decision_needed",
                                "mandatory_approval_needed"], "policy_version": "0.1.0", "revocable": True,
            "status": "active", "granted_by": "user", "granted_at": "2026-11-20T10:00:00+00:00",
            "history": [{"event": "granted", "at": "2026-11-20T10:00:00+00:00", "by": "user"}]}


def path(aid):
    return os.path.join(proj, ".aisef", "authorizations", aid + ".json")


def load(aid):
    with open(path(aid), encoding="utf-8") as fh:
        return json.load(fh)


try:
    proj = os.path.join(work, "p")
    os.makedirs(proj)
    ap.init(proj, "PRJ-L", "life", "dev")
    os.makedirs(os.path.join(proj, ".aisef", "authorizations"), exist_ok=True)
    docs = {"AUTH-001": auth("AUTH-001", "FEAT-001", "2026-12-31T00:00:00+00:00"),   # feature aceita, prazo longe
            "AUTH-002": auth("AUTH-002", "FEAT-002", "2026-11-27T20:00:00+00:00"),   # venceu
            "AUTH-003": auth("AUTH-003", "FEAT-002", "2026-12-31T00:00:00+00:00")}   # segue valendo
    for aid, d in docs.items():
        ap.write_json(path(aid), d)
    ap.append(proj, {"event_type": "feature_accepted", "actor": {"type": "user", "id": "user"}, "feature_id": "FEAT-001",
                     "summary": "FEAT-001 aceita"})

    done = life.close_finished(proj, NOW)
    check("feature aceita encerra a autorizacao dela (closed)", ("AUTH-001", "closed", "FEAT-001 aceita") in done, done)
    check("prazo vencido marca a autorizacao como expired", any(d[0] == "AUTH-002" and d[1] == "expired" for d in done), done)
    check("autorizacao dentro do prazo e de feature aberta continua active", load("AUTH-003")["status"] == "active")
    h = load("AUTH-001")["history"][-1]
    check("historico ganha o evento e aponta para o log", h["event"] == "closed" and h["event_log_ref"].startswith("events/"))
    import audit_chain
    log = audit_chain.read_log_dir(os.path.join(proj, ".aisef", "audit"))
    types = [e["event_type"] for e in log]
    check("log assinado registra authorization_closed e authorization_expired",
          "authorization_closed" in types and "authorization_expired" in types)
    check("log continua integro", not ap.verify(proj)[0])
    check("idempotente: rodar de novo nao muda nada", life.close_finished(proj, NOW) == [])
    r = cp.check(os.path.join(proj, ".aisef"), HERE, POL, DEF, now=NOW)
    bad = [f for f in r.findings if f["rule"] in ("SCHEMA", "AUTH-EXPIRED", "AUTH-STATUS", "AUTH-HISTORY", "AUTH-NOT-CLOSED")]
    check("autorizacoes encerradas passam no schema e no check (sem AUTH-EXPIRED)", bad == [], bad)

    # rede do check: autorizacao ainda 'active' de feature aceita vira aviso
    d = load("AUTH-003"); d["feature_id"] = "FEAT-001"; ap.write_json(path("AUTH-003"), d)
    r = cp.check(os.path.join(proj, ".aisef"), HERE, POL, DEF)
    check("check avisa AUTH-NOT-CLOSED para autorizacao ativa de feature aceita",
          any(f["rule"] == "AUTH-NOT-CLOSED" for f in r.findings), [f["rule"] for f in r.findings])
finally:
    shutil.rmtree(work, ignore_errors=True)

print("\n%d testes, %d falhas" % (total, fails))
sys.exit(1 if fails else 0)
