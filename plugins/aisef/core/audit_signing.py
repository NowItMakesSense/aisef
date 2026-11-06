#!/usr/bin/env python3
"""AISEF audit log: assinatura Ed25519 por evento + registro de cabeca assinado (RASCUNHO v0.1).

Decisao do usuario: assinar cada evento com uma chave que o agente e o armazenamento nao conhecem.

Papeis:
- AuditSigner   : componente separado, unico dono da chave privada. Assina cada evento e mantem o
                  'head' assinado (ultima sequencia + hash). Agentes e o armazenamento do log nunca o tocam.
- AuditVerifier : so conhece chaves PUBLICAS. Nao consegue assinar nada.

O que isto fecha, em relacao a cadeia de hash sozinha:
- Reescrita completa recalculando hashes: falha, pois quem reescreve nao tem a chave para assinar.
- Truncar o final do log: detectado comparando com o head assinado, desde que o head fique guardado
  FORA do armazenamento do log (com o Audit Signer ou em outro local).

Limites que continuam valendo (documentados, nao escondidos):
- Se o atacante tambem controla o Audit Signer ou a chave privada, nada disto protege.
- Se o head for guardado no mesmo lugar que o log, quem trunca o log tambem pode devolver um head antigo
  (rollback). O verificador so detecta se tiver um head mais recente do que o do log.
- Rotacao e revogacao de chaves: o verificador aceita um conjunto de key_id e uma lista de revogados;
  a politica de rotacao ainda nao foi definida.

Uso:
    python3 -I audit_signing.py selftest <audit-event.schema.json>
"""
import base64
import copy
import json
import os
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
# `serialization` custa ~130 ms de import e so serve para PEM: importado sob demanda (o hook roda a cada chamada).

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_chain  # noqa: E402

EVENT_DOMAIN = b"aisef-audit-event-v1"
HEAD_DOMAIN = b"aisef-audit-head-v1"


def _event_message(log_id, sequence, event_hash):
    return b"|".join([EVENT_DOMAIN, str(log_id).encode(), str(sequence).encode(), event_hash.encode()])


def _head_message(log_id, sequence, event_hash):
    return b"|".join([HEAD_DOMAIN, str(log_id).encode(), str(sequence).encode(), event_hash.encode()])


def _b64(raw):
    return base64.b64encode(raw).decode("ascii")


class AuditSigner:
    """Dono da chave privada. Em producao roda isolado (processo/servico proprio)."""

    def __init__(self, key_id, private_key=None):
        self.key_id = key_id
        self._private = private_key or Ed25519PrivateKey.generate()
        self.head = None

    def public_key(self):
        return self._private.public_key()

    def public_key_pem(self):
        from cryptography.hazmat.primitives import serialization
        return self._private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)

    def append(self, log, partial):
        """Acrescenta, assina o evento e atualiza o head assinado."""
        event = audit_chain.append_event(log, partial)
        sig = self._private.sign(_event_message(event["log_id"], event["sequence"], event["hash"]))
        event["signature"] = {"algorithm": "ed25519", "key_id": self.key_id, "value": _b64(sig)}
        head_sig = self._private.sign(_head_message(event["log_id"], event["sequence"], event["hash"]))
        self.head = {
            "log_id": event["log_id"], "sequence": event["sequence"], "hash": event["hash"],
            "key_id": self.key_id, "signature": _b64(head_sig),
        }
        return event


class AuditVerifier:
    """So chaves publicas. Nao assina."""

    def __init__(self, public_keys, revoked=()):
        self.public_keys = dict(public_keys)
        self.revoked = set(revoked)

    def _check(self, key_id, signature_b64, message):
        if key_id in self.revoked:
            return "chave revogada: " + key_id
        pub = self.public_keys.get(key_id)
        if pub is None:
            return "key_id desconhecido: " + key_id
        try:
            pub.verify(base64.b64decode(signature_b64), message)
        except (InvalidSignature, ValueError):
            return "assinatura invalida"
        return None

    def verify(self, log, head=None):
        """Retorna (erros, avisos). Inclui a verificacao da cadeia de hash."""
        errors = list(audit_chain.verify_chain(log))
        warnings = []
        for i, ev in enumerate(log):
            where = "evento %d (%s)" % (i, ev.get("event_id", "?"))
            sig = ev.get("signature")
            if not sig:
                errors.append(where + ": sem assinatura")
                continue
            if sig.get("algorithm") != "ed25519":
                errors.append(where + ": algoritmo de assinatura desconhecido")
                continue
            problem = self._check(sig.get("key_id"), sig.get("value", ""),
                                  _event_message(ev.get("log_id"), ev.get("sequence"), ev.get("hash", "")))
            if problem:
                errors.append(where + ": " + problem)
        if head is None:
            warnings.append("sem head assinado: truncamento do final do log nao pode ser detectado")
            return errors, warnings
        problem = self._check(head.get("key_id"), head.get("signature", ""),
                              _head_message(head.get("log_id"), head.get("sequence"), head.get("hash", "")))
        if problem:
            errors.append("head: " + problem)
            return errors, warnings
        if not log:
            errors.append("log vazio, mas existe head assinado (truncamento total)")
            return errors, warnings
        last = log[-1]
        if last.get("log_id") != head.get("log_id"):
            errors.append("head pertence a outro log_id")
        elif last.get("sequence", -1) < head["sequence"]:
            errors.append("log truncado: termina na sequencia %s, head assinado esta em %s"
                          % (last.get("sequence"), head["sequence"]))
        elif last.get("sequence") == head["sequence"]:
            if last.get("hash") != head["hash"]:
                errors.append("hash do ultimo evento nao confere com o head assinado")
        else:
            match = next((e for e in log if e.get("sequence") == head["sequence"]), None)
            if match is None or match.get("hash") != head["hash"]:
                errors.append("evento da sequencia do head ausente ou com hash diferente")
            else:
                warnings.append("head atrasado: ha %d evento(s) apos o head (assinados individualmente)"
                                % (last["sequence"] - head["sequence"]))
        return errors, warnings


def selftest(schema_path):
    ts = "2026-11-05T22:00:00-03:00"
    base = {"schema_version": "0.1.0", "log_id": "PRJ-1", "project_id": "PRJ-1", "timestamp": ts}
    signer = AuditSigner("audit-key-1")
    verifier = AuditVerifier({"audit-key-1": signer.public_key()})
    log = []
    steps = [
        dict(event_id="E0", event_type="genesis", actor={"type": "system", "id": "aisef"}, summary="Log criado"),
        dict(event_id="E1", event_type="contract_created", actor={"type": "orchestrator", "id": "orq"},
             summary="Task Contract T-001 criado", subject={"kind": "task_contract", "id": "T-001", "version": 1},
             feature_id="FEAT-001"),
        dict(event_id="E2", event_type="task_started", actor={"type": "agent", "id": "backend-1"},
             summary="Tarefa iniciada", feature_id="FEAT-001", task_id="T-001"),
        dict(event_id="E3", event_type="task_executed", actor={"type": "agent", "id": "backend-1"},
             summary="Execucao concluida", feature_id="FEAT-001", task_id="T-001"),
        dict(event_id="E4", event_type="task_validated", actor={"type": "validator", "id": "val-1"},
             summary="Criterios verificados", feature_id="FEAT-001", task_id="T-001"),
    ]
    for st in steps:
        signer.append(log, {**base, **st})
    head = signer.head

    results = []

    def check(label, cond):
        results.append(cond)
        print(("OK   " if cond else "FALHA"), label)

    errs, warns = verifier.verify(log, head)
    check("log assinado integro, com head, aceito", errs == [] and warns == [])

    t = copy.deepcopy(log); t[2]["summary"] = "editado"
    check("edicao de conteudo detectada", bool(verifier.verify(t, head)[0]))

    # Atacante com acesso ao armazenamento, SEM a chave: reescreve e recalcula todos os hashes.
    t = copy.deepcopy(log)
    t[2]["summary"] = "reescrito pelo atacante"
    for i in range(2, len(t)):
        t[i]["prev_hash"] = t[i - 1]["hash"]
        t[i]["hash"] = audit_chain.compute_hash(t[i])
    check("cadeia reescrita e recalculada ESTA consistente (hash sozinho nao basta)",
          audit_chain.verify_chain(t) == [])
    errs, _ = verifier.verify(t, head)
    check("reescrita completa recalculando hashes detectada pela assinatura", bool(errs))
    check("  ... e o erro e de assinatura", any("assinatura invalida" in e for e in errs))

    attacker = AuditSigner("audit-key-1")  # mesma key_id, chave privada diferente
    t = copy.deepcopy(log)
    t[2]["summary"] = "reescrito e assinado com chave falsa"
    for i in range(2, len(t)):
        t[i]["prev_hash"] = t[i - 1]["hash"]
        t[i]["hash"] = audit_chain.compute_hash(t[i])
        t[i]["signature"] = {"algorithm": "ed25519", "key_id": "audit-key-1", "value": _b64(
            attacker._private.sign(_event_message(t[i]["log_id"], t[i]["sequence"], t[i]["hash"])))}
    check("assinatura com chave falsa (mesmo key_id) detectada", bool(verifier.verify(t, head)[0]))

    t = copy.deepcopy(log)[:-1]
    errs, warns = verifier.verify(t, head)
    check("truncar o final detectado pelo head assinado", any("truncado" in e for e in errs))
    errs, warns = verifier.verify(t, None)
    check("sem head, truncar NAO e detectado, mas ha aviso explicito (limite conhecido)",
          errs == [] and any("sem head" in w for w in warns))

    t = copy.deepcopy(log)[:2]
    old_head = None
    errs, warns = verifier.verify(t, head)
    check("truncar quase tudo detectado", bool(errs))

    t = copy.deepcopy(log)
    t[3]["signature"] = copy.deepcopy(t[2]["signature"])
    check("assinatura copiada de outro evento (replay) detectada", bool(verifier.verify(t, head)[0]))

    t = copy.deepcopy(log); del t[2]["signature"]
    check("evento sem assinatura detectado", bool(verifier.verify(t, head)[0]))

    t = copy.deepcopy(log); t[2]["signature"]["key_id"] = "outra-chave"
    check("key_id desconhecido detectado", bool(verifier.verify(t, head)[0]))

    rev = AuditVerifier({"audit-key-1": signer.public_key()}, revoked={"audit-key-1"})
    check("chave revogada rejeitada", bool(rev.verify(log, head)[0]))

    bad_head = dict(head); bad_head["sequence"] = head["sequence"] + 5
    check("head adulterado detectado (assinatura do head)", any("head" in e for e in verifier.verify(log, bad_head)[0]))

    other = AuditSigner("audit-key-2")
    check("verificador so com chave publica de outro signer rejeita o log",
          bool(AuditVerifier({"audit-key-1": other.public_key()}).verify(log, head)[0]))

    extra = copy.deepcopy(log)
    signer.append(extra, {**base, "event_id": "E5", "event_type": "task_completed",
                          "actor": {"type": "orchestrator", "id": "orq"}, "summary": "Tarefa concluida",
                          "feature_id": "FEAT-001", "task_id": "T-001"})
    errs, warns = verifier.verify(extra, head)
    check("head atrasado gera aviso, nao erro (eventos seguem assinados)",
          errs == [] and any("atrasado" in w for w in warns))

    pem = signer.public_key_pem()
    from cryptography.hazmat.primitives import serialization
    reloaded = AuditVerifier({"audit-key-1": serialization.load_pem_public_key(pem)})
    check("verificador carregado de PEM publico funciona", reloaded.verify(log, head)[0] == [])

    try:
        signer.append([], {**base, "event_id": "X", "event_type": "genesis", "actor": {"type": "system", "id": "a"},
                           "summary": "senha", "data": {"x": "password=hunter2hunter2"}})
        check("Audit Signer tambem recusa segredo antes de assinar", False)
    except ValueError:
        check("Audit Signer tambem recusa segredo antes de assinar", True)

    try:
        import jsonschema
    except ImportError:
        print("(jsonschema ausente: validacao de schema pulada)")
    else:
        schema = json.load(open(schema_path, encoding="utf-8"))
        signed_profile = copy.deepcopy(schema)
        signed_profile["required"] = list(schema["required"]) + ["signature"]
        v = jsonschema.Draft202012Validator(signed_profile)
        check("todos os eventos validam no perfil de producao (assinatura obrigatoria)",
              all(not list(v.iter_errors(e)) for e in log))
        e = copy.deepcopy(log[1]); e.pop("signature")
        check("evento sem assinatura rejeitado no perfil de producao", bool(list(v.iter_errors(e))))
        e = copy.deepcopy(log[1]); e["signature"]["algorithm"] = "hmac-sha256"
        check("algoritmo diferente de ed25519 rejeitado", bool(list(v.iter_errors(e))))
        e = copy.deepcopy(log[1]); e["signature"]["value"] = "curta"
        check("assinatura malformada rejeitada", bool(list(v.iter_errors(e))))
        base_v = jsonschema.Draft202012Validator(schema)
        check("eventos assinados tambem validam no schema base", all(not list(base_v.iter_errors(e)) for e in log))

    n_fail = results.count(False)
    print("\n%d verificacoes, %d falhas" % (len(results), n_fail))
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "selftest":
        sys.exit(selftest(sys.argv[2]))
    print(__doc__)
    sys.exit(2)
