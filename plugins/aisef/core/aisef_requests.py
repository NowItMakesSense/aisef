#!/usr/bin/env python3

"""AISEF: Approval Center: pedido (request) e decisao do usuario (decide), incluindo a aprovacao reforcada.

H-01 (0.14): parte do antigo aisef_project.py. Importe pela fachada `aisef_project`, que reexporta tudo."""

import base64  # noqa: F401
import datetime  # noqa: F401
import fnmatch  # noqa: F401
import glob  # noqa: F401
import json  # noqa: F401
import os
import re  # noqa: F401
import sys
import time  # noqa: F401

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_base  # noqa: E402
import aisef_catalog  # noqa: E402,F401
import audit_chain  # noqa: E402,F401

from aisef_base import *  # noqa: E402,F401,F403
from aisef_base import _ED25519_PKCS8_PREFIX, _LazySerialization, _load_private_key, _plugin_version  # noqa: E402,F401
from aisef_audit_log import *  # noqa: E402,F401,F403
from aisef_audit_log import _anchor, _rotate_if_large, _write_event  # noqa: E402,F401
from aisef_agents import *  # noqa: E402,F401,F403
try:
    from aisef_base import Ed25519PrivateKey, audit_signing  # noqa: E402,F401
except ImportError:
    pass

CHOICE_STATUS = {"approve": "approved", "select_option": "approved", "reject": "rejected",
                 "request_changes": "changes_requested"}


def request(project, draft_path):
    """Cria um pedido PENDENTE do Approval Center a partir de um rascunho: valida, anexa approval_requested
    e grava o pedido com audit.requested_event_ref ja apontando para o evento. Criar pedido nao e decidir."""
    with open(draft_path, encoding="utf-8") as fh:
        req = json.load(fh)
    if not isinstance(req, dict):
        raise SystemExit("nada foi gravado; o rascunho precisa ser um objeto JSON")
    if req.get("status") != "pending" or "decision" in req or "resulting_ref" in req:
        raise SystemExit("nada foi gravado; request so cria pedido pendente (status 'pending', sem decision/resulting_ref): "
                         "a decisao e do usuario, via decide")
    cfg = load_config(project)
    if req.get("project_id") != cfg["project_id"]:
        raise SystemExit("nada foi gravado; project_id %r difere do projeto (%s)" % (req.get("project_id"), cfg["project_id"]))
    req.setdefault("audit", {})["requested_event_ref"] = "events/pending"
    req["audit"].pop("decided_event_ref", None)
    problems = validate(req, "approval-request.schema.v0.1.json")
    if problems:
        raise SystemExit("nada foi gravado; pedido invalido:\n - " + "\n - ".join(problems))
    rid = req["request_id"]
    path = os.path.join(aisef_dir(project), "approvals", rid + ".json")
    if os.path.exists(path):
        raise SystemExit("nada foi gravado; %s ja existe (pedido nao e sobrescrito: crie outro id)" % rid)
    partial = {"event_type": "approval_requested", "actor": {"type": "orchestrator", "id": "orchestrator"},
               "summary": "%s aguardando decisao: %s" % (rid, req["title"]),
               "data": {"request_id": rid, "request_type": req["request_type"]}}
    if req.get("feature_id"):
        partial["feature_id"] = req["feature_id"]
    if req.get("task_id"):
        partial["task_id"] = req["task_id"]
    ev = append(project, partial)
    req["audit"]["requested_event_ref"] = "events/%d" % ev["sequence"]
    write_json(path, req)
    return req, ev


REINFORCED_GIT_OPS = ("force_push", "history_rewrite", "branch_delete")


def needs_reinforced(req):
    """Pedido cuja aprovacao so vale com uma autorizacao reforcada (o gateway exige a operacao exata)."""
    return req.get("request_type") == "reinforced_approval" or (
        req.get("request_type") == "git_operation" and (req.get("git") or {}).get("operation") in REINFORCED_GIT_OPS)


def reinforced_mismatch(req, auth):
    """Motivo pelo qual o rascunho nao serve como autorizacao reforcada deste pedido, ou None."""
    if auth is None:
        return "falta --authorization com o rascunho da autorizacao reforcada"
    if auth.get("kind") != "reinforced":
        return "a autorizacao precisa ser kind 'reinforced' (veio %r)" % auth.get("kind")
    want = ((req.get("operation") or {}).get("operation") or "").strip()
    if (auth.get("operation") or "").strip() != want:
        return "a operation da autorizacao (%r) difere da operation exata do pedido (%r)" % (auth.get("operation"), want)
    for key in ("feature_id", "task_id"):
        if req.get(key) and auth.get(key) != req.get(key):
            return "%s da autorizacao (%r) difere do pedido (%r)" % (key, auth.get(key), req.get(key))
    return None


def decide(project, request_id, choice, option=None, note=None, ack=(), authorization_draft=None):
    """Registra a decisao do USUARIO sobre um pedido pendente do Approval Center.

    Uma unica chamada grava a decisao, a autorizacao gerada (escopo ou reforcada) e o evento de
    auditoria. O gateway exige o prompt nativo de permissao para este comando: e ali que o usuario decide.
    """
    root = aisef_dir(project)
    req_path = os.path.join(root, "approvals", request_id + ".json")
    with open(req_path, encoding="utf-8") as fh:
        req = json.load(fh)
    if req.get("status") != "pending":
        raise SystemExit("%s nao esta pendente (status %s): decisao nao muda, crie um novo pedido" % (request_id, req.get("status")))
    when = now_iso()
    req["status"] = CHOICE_STATUS[choice]
    req["decision"] = {"choice": choice, "decided_by": "user", "decided_at": when}
    if option:
        req["decision"]["selected_option_id"] = option
    if note:
        req["decision"]["note"] = note
    if ack:
        req["decision"]["acknowledged"] = list(ack)

    auth, auth_path = None, None
    if authorization_draft and req["status"] == "approved":
        with open(authorization_draft, encoding="utf-8") as fh:
            auth = json.load(fh)
    if req["status"] == "approved" and needs_reinforced(req):
        # aprovar sem a autorizacao reforcada geraria um pedido aprovado inutil: o gateway continuaria negando
        problem = reinforced_mismatch(req, auth)
        if problem:
            raise SystemExit("nada foi gravado; %s exige aprovacao reforcada: %s" % (request_id, problem))
    if auth is not None:
        if auth.get("kind") == "scope":
            with open(os.path.join(HERE, "permission-policy.v0.1.json"), encoding="utf-8") as fh:
                max_days = json.load(fh).get("scope_authorization_schema_ref", {}).get("validity_max_days")
            v = auth.get("validity", {})
            span = (datetime.datetime.fromisoformat(v["valid_until"]) - datetime.datetime.fromisoformat(v["valid_from"])).total_seconds()
            if max_days is not None and span > max_days * 86400:
                raise SystemExit("nada foi gravado; escopo de %.1f dias excede o maximo da politica (%d dias)" % (span / 86400, max_days))
            auth.update({"status": "active", "granted_by": "user", "granted_at": when})
            auth.setdefault("history", []).append({"event": "granted", "at": when, "by": "user"})
            auth_id, kind = auth["authorization_id"], "scope_authorization"
        elif auth.get("kind") == "reinforced":
            auth.update({"status": "approved", "decided_by": "user", "decided_at": when})
            auth_id, kind = auth["approval_id"], "reinforced_approval"
        else:
            raise SystemExit("autorizacao com kind desconhecido: %r" % auth.get("kind"))
        req["resulting_ref"] = {"kind": kind, "id": auth_id}
        auth_path = os.path.join(root, "authorizations", auth_id + ".json")
        if os.path.exists(auth_path):
            raise SystemExit("%s ja existe; autorizacoes nao sao sobrescritas" % auth_path)

    req.setdefault("audit", {})["decided_event_ref"] = "events/pending"
    problems = validate(req, "approval-request.schema.v0.1.json")
    if auth:
        problems += ["autorizacao: " + p for p in validate(auth, "authorization.schema.v0.1.json")]
    if problems:
        raise SystemExit("nada foi gravado; documento invalido:\n - " + "\n - ".join(problems))

    etype = "approval_granted" if req["status"] == "approved" else "approval_rejected"
    partial = {"event_type": etype, "actor": {"type": "user", "id": "user"},
               "summary": "%s: %s" % (request_id, req["status"]),
               "data": {"request_id": request_id, "request_type": req.get("request_type"), "choice": choice}}
    if req.get("feature_id"):
        partial["feature_id"] = req["feature_id"]
    ev = append(project, partial)
    if auth:
        append(project, {"event_type": "authorization_granted", "actor": {"type": "user", "id": "user"},
                         "summary": "%s concedida" % req["resulting_ref"]["id"], "caused_by": ev["event_id"],
                         "subject": {"kind": req["resulting_ref"]["kind"], "id": req["resulting_ref"]["id"]}})
        write_json(auth_path, auth)
    req["audit"]["decided_event_ref"] = "events/%d" % ev["sequence"]
    write_json(req_path, req)
    if req.get("request_type") == "plan_approval" and req["status"] == "approved" and req.get("feature_id"):
        reflect_plan_approval(project, req["feature_id"], when)
    return req


def reflect_plan_approval(project, feature_id, when):
    """Plano aprovado pelo usuario: o Feature Contract passa a 'approved_for_execution' e as tarefas em draft a 'ready'."""
    root = aisef_dir(project)
    fpath = os.path.join(root, "contracts", "features", feature_id + ".json")
    if not os.path.exists(fpath):
        return
    with open(fpath, encoding="utf-8") as fh:
        feature = json.load(fh)
    feature["approval"]["plan"] = {"status": "approved", "granularity": "feature", "approved_by": "user", "approved_at": when}
    if feature["state"]["status"] in ("discovery", "planning", "awaiting_plan_approval"):
        feature["state"]["status"] = "approved_for_execution"
    write_json(fpath, feature)
    for t in feature.get("task_plan", []):
        tpath = os.path.join(root, "contracts", "tasks", t["task_id"] + ".json")
        if os.path.exists(tpath):
            with open(tpath, encoding="utf-8") as fh:
                task = json.load(fh)
            if task["state"]["status"] == "draft":
                task["state"]["status"] = "ready"
                write_json(tpath, task)
