#!/usr/bin/env python3
"""AISEF: fim de vida das autorizacoes de escopo (A-01).

Uma autorizacao de escopo declara em `termination_condition` quando acaba (`expiry`, `feature_accepted`), mas nada
encerrava a autorizacao: ela seguia `active` depois de a feature ser aceita e depois de vencer, e o aisef-check passava
a acusar AUTH-EXPIRED. Aqui:

- feature aceita (pedido feature_acceptance aprovado, ou evento feature_accepted no log) -> `closed`;
- prazo vencido (`validity.valid_until` no passado) -> `expired`.

Cada encerramento entra no historico da autorizacao e no log assinado (authorization_closed / authorization_expired).
Idempotente: so mexe no que ainda esta `active`. Roda no aceite da feature (decide), no `next` e no doctor.

    python -I aisef_auth_life.py --project .        (encerra o que ja acabou e lista)
"""
import argparse
import datetime
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_project as ap  # noqa: E402


def _ptime(s):
    try:
        t = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError):
        return None


def accepted_features(project):
    """Features com aceite aprovado, pelos pedidos e pelo log."""
    root = ap.aisef_dir(project)
    out = set()
    for p in glob.glob(os.path.join(root, "approvals", "*.json")):
        try:
            with open(p, encoding="utf-8") as fh:
                r = json.load(fh)
        except (OSError, ValueError):
            continue
        if r.get("request_type") == "feature_acceptance" and r.get("status") == "approved" and r.get("feature_id"):
            out.add(r["feature_id"])
    try:
        import audit_chain
        for ev in audit_chain.read_log_dir(os.path.join(root, "audit")):
            if ev.get("event_type") == "feature_accepted" and ev.get("feature_id"):
                out.add(ev["feature_id"])
    except (ImportError, OSError, ValueError):
        pass
    return out


def close_finished(project, now=None):
    """Encerra as autorizacoes de escopo que ja acabaram. Devolve [(id, novo_status, motivo)]."""
    now = now or datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    root = ap.aisef_dir(project)
    accepted, done = None, []
    for path in sorted(glob.glob(os.path.join(root, "authorizations", "AUTH-*.json"))):
        try:
            with open(path, encoding="utf-8") as fh:
                au = json.load(fh)
        except (OSError, ValueError):
            continue
        if au.get("kind") != "scope" or au.get("status") != "active":
            continue
        term = au.get("termination_condition") or []
        if accepted is None:
            accepted = accepted_features(project)
        fid, until = au.get("feature_id"), _ptime((au.get("validity") or {}).get("valid_until"))
        if "feature_accepted" in term and fid in accepted:
            status, event, why = "closed", "authorization_closed", "%s aceita" % fid
        elif until is not None and until < now:
            status, event, why = "expired", "authorization_expired", "venceu em %s" % au["validity"]["valid_until"]
        else:
            continue
        ev = ap.append(project, {"event_type": event, "actor": {"type": "system", "id": "aisef"},
                                 "summary": "%s %s: %s" % (au["authorization_id"], "encerrada" if status == "closed" else "expirada", why),
                                 "subject": {"kind": "scope_authorization", "id": au["authorization_id"]},
                                 **({"feature_id": fid} if fid else {})})
        au["status"] = status  # o motivo fica no evento do log; o historico aponta para ele
        au.setdefault("history", []).append({"event": status, "at": now.isoformat(), "by": "system",
                                             "event_log_ref": "events/%d" % ev["sequence"]})
        ap.write_json(path, au)
        done.append((au["authorization_id"], status, why))
    return done


def main(argv):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project", required=True)
    a = p.parse_args(argv[1:])
    done = close_finished(a.project)
    for aid, st, why in done:
        print("%s -> %s (%s)" % (aid, st, why))
    if not done:
        print("nenhuma autorizacao de escopo para encerrar")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
