#!/usr/bin/env python3
"""AISEF audit log: implementacao de referencia da cadeia de hash (RASCUNHO v0.1).

Formato: JSON Lines, um evento por linha, apenas append.
Hash: SHA-256 do JSON canonico do evento SEM o campo "hash" (inclui prev_hash).
JSON canonico: chaves ordenadas, separadores compactos, UTF-8, sem ASCII forcado.

Uso:
    python3 -I audit_chain.py verify <log.jsonl>
    python3 -I audit_chain.py selftest [<audit-event.schema.json>]

Observacoes:
- A cadeia detecta edicao, remocao, insercao e reordenacao. NAO impede que quem controla
  o armazenamento reescreva o log inteiro recalculando os hashes: para isso use assinatura
  ou ancora externa (decisao pendente).
- A deteccao de segredos e heuristica (best effort). A garantia real vem de redigir antes de gravar.
"""
import hashlib
import json
import os
import re
import sys

ALGORITHM = "sha256-canonical-json-v1"
GENESIS_PREV = "0" * 64

SECRET_PATTERNS = [
    ("chave privada", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("token GitHub", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("bearer token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{20,}")),
    ("atribuicao de segredo", re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|access[_-]?token|private[_-]?key)\b\s*[:=]\s*[\"']?[^\s\"',}]{8,}")),
    ("URL com credenciais", re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@")),
]


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def compute_hash(event):
    # A assinatura e feita sobre o hash, portanto nao entra no calculo dele.
    body = {k: v for k, v in event.items() if k not in ("hash", "signature")}
    return hashlib.sha256(canonical(body)).hexdigest()


def find_secrets(event):
    """Retorna descricoes de padroes de segredo encontrados (heuristica)."""
    text = json.dumps({k: v for k, v in event.items() if k not in ("hash", "prev_hash")}, ensure_ascii=False)
    return [name for name, rx in SECRET_PATTERNS if rx.search(text)]


def append_event(log, partial):
    """Acrescenta um evento ao fim de `log` (lista). Preenche sequence, prev_hash, algoritmo e hash."""
    found = find_secrets(partial)
    if found:
        raise ValueError("evento recusado, possivel segredo: " + ", ".join(found))
    if log:
        seq, prev = log[-1]["sequence"] + 1, log[-1]["hash"]
    else:
        seq, prev = 0, GENESIS_PREV
    event = dict(partial)
    event.update({
        "sequence": seq,
        "prev_hash": prev,
        "hash_algorithm": ALGORITHM,
        "secrets_redacted": True,
        "contains_model_reasoning": False,
    })
    event["hash"] = compute_hash(event)
    log.append(event)
    return event


def verify_chain(log):
    """Retorna lista de erros (vazia = cadeia integra)."""
    errors = []
    log_ids = set()
    for i, ev in enumerate(log):
        where = "evento %d (%s)" % (i, ev.get("event_id", "?"))
        log_ids.add(ev.get("log_id"))
        if ev.get("hash_algorithm") != ALGORITHM:
            errors.append(where + ": algoritmo desconhecido")
        if ev.get("sequence") != i:
            errors.append(where + ": sequencia %r esperada %d (lacuna, insercao ou reordenacao)" % (ev.get("sequence"), i))
        expected_prev = GENESIS_PREV if i == 0 else log[i - 1].get("hash")
        if ev.get("prev_hash") != expected_prev:
            errors.append(where + ": prev_hash nao confere com o evento anterior")
        if ev.get("hash") != compute_hash(ev):
            errors.append(where + ": hash nao confere com o conteudo (evento alterado)")
        if i == 0 and ev.get("event_type") != "genesis":
            errors.append(where + ": o primeiro evento deve ser genesis")
        if i > 0 and ev.get("event_type") == "genesis":
            errors.append(where + ": genesis so pode ser o primeiro evento")
    if len(log_ids) > 1:
        errors.append("o arquivo mistura mais de um log_id: %s" % sorted(map(str, log_ids)))
    return errors


def read_log(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def log_segments(audit_dir):
    """Arquivos do log em ordem: segmentos arquivados (archive/log-<primeira>-<ultima>.jsonl) e o atual."""
    archive = os.path.join(audit_dir, "archive")
    segs = []
    if os.path.isdir(archive):
        named = []
        for name in os.listdir(archive):
            m = re.match(r"^log-(\d+)-(\d+)\.jsonl$", name)
            if m:
                named.append((int(m.group(1)), os.path.join(archive, name)))
        segs = [p for _first, p in sorted(named)]
    current = os.path.join(audit_dir, "log.jsonl")
    if os.path.exists(current):
        segs.append(current)
    return segs


def read_log_dir(audit_dir):
    """O log inteiro (todos os segmentos concatenados): a cadeia continua de um segmento para o outro."""
    log = []
    for seg in log_segments(audit_dir):
        log.extend(read_log(seg))
    return log


def selftest(schema_path=None):
    import copy
    ts = "2026-11-05T21:30:00-03:00"
    base = {"schema_version": "0.1.0", "log_id": "PRJ-1", "project_id": "PRJ-1", "timestamp": ts}
    log = []
    steps = [
        dict(event_id="E0", event_type="genesis", actor={"type": "system", "id": "aisef"}, summary="Log criado"),
        dict(event_id="E1", event_type="contract_created", actor={"type": "orchestrator", "id": "orq"}, summary="Task Contract T-001 criado",
             subject={"kind": "task_contract", "id": "T-001", "version": 1}, feature_id="FEAT-001"),
        dict(event_id="E2", event_type="task_started", actor={"type": "agent", "id": "backend-1"}, summary="Tarefa iniciada",
             feature_id="FEAT-001", task_id="T-001"),
        dict(event_id="E3", event_type="task_executed", actor={"type": "agent", "id": "backend-1"}, summary="Execucao concluida",
             feature_id="FEAT-001", task_id="T-001"),
        dict(event_id="E4", event_type="task_validated", actor={"type": "validator", "id": "val-1"}, summary="Criterios verificados",
             feature_id="FEAT-001", task_id="T-001"),
        dict(event_id="E5", event_type="correction", actor={"type": "orchestrator", "id": "orq"}, summary="Correcao do resumo de E3",
             corrects_event_id="E3"),
    ]
    for st in steps:
        append_event(log, {**base, **st})

    results = []

    def check(label, cond):
        results.append(cond)
        print(("OK   " if cond else "FALHA"), label)

    check("cadeia integra aceita", verify_chain(log) == [])

    t = copy.deepcopy(log); t[2]["summary"] = "Tarefa iniciada (editada)"
    check("edicao de conteudo detectada", bool(verify_chain(t)))

    t = copy.deepcopy(log); t[2]["summary"] = "editada"; t[2]["hash"] = compute_hash(t[2])
    check("edicao com hash recalculado so do evento detectada (quebra o encadeamento)", bool(verify_chain(t)))

    t = copy.deepcopy(log); del t[3]
    check("remocao de evento detectada", bool(verify_chain(t)))

    t = copy.deepcopy(log); t[2], t[3] = t[3], t[2]
    check("reordenacao detectada", bool(verify_chain(t)))

    t = copy.deepcopy(log); t.insert(2, copy.deepcopy(t[1]))
    check("insercao/duplicacao detectada", bool(verify_chain(t)))

    t = copy.deepcopy(log)[:-1]
    check("truncar o final NAO e detectado pela cadeia sozinha (limite conhecido, exige checkpoint/ancora)", verify_chain(t) == [])

    t = copy.deepcopy(log)
    for i in range(2, len(t)):
        t[i]["summary"] = t[i]["summary"] + "" if i != 2 else "reescrito"
        t[i]["prev_hash"] = t[i - 1]["hash"]
        t[i]["hash"] = compute_hash(t[i])
    check("reescrita completa recalculando todos os hashes NAO e detectada (limite conhecido, exige assinatura/ancora)", verify_chain(t) == [])

    for label, payload in [
        ("chave privada", {"data": {"x": "-----BEGIN RSA PRIVATE KEY-----\nabc"}}),
        ("senha em texto", {"summary": "usando password=hunter2hunter2 no deploy"}),
        ("token GitHub", {"data": {"t": "ghp_" + "a" * 36}}),
        ("URL com credenciais", {"data": {"u": "postgres://admin:s3nh4forte@db.local/app"}}),
    ]:
        try:
            append_event([], {**base, "event_id": "X", "event_type": "genesis", "actor": {"type": "system", "id": "a"},
                              "summary": "teste de segredo", **payload})
            check("segredo recusado: " + label, False)
        except ValueError:
            check("segredo recusado: " + label, True)

    try:
        append_event([], {**base, "event_id": "X", "event_type": "genesis", "actor": {"type": "system", "id": "a"},
                          "summary": "Leu o arquivo .env sem expor conteudo", "data": {"file": ".env", "content_logged": False}})
        check("evento legitimo que menciona .env sem o conteudo e aceito", True)
    except ValueError:
        check("evento legitimo que menciona .env sem o conteudo e aceito", False)

    if schema_path:
        try:
            import jsonschema
        except ImportError:
            print("(jsonschema ausente: validacao de schema pulada)")
        else:
            schema = json.load(open(schema_path, encoding="utf-8"))
            jsonschema.Draft202012Validator.check_schema(schema)
            v = jsonschema.Draft202012Validator(schema)
            ok = lambda d: not list(v.iter_errors(d))
            check("todos os eventos da cadeia validam no schema", all(ok(e) for e in log))

            def bad(label, mutate, idx):
                e = copy.deepcopy(log[idx]); mutate(e)
                check(label, not ok(e))
            bad("genesis fora da sequencia 0 rejeitado", lambda e: e.__setitem__("sequence", 3), 0)
            bad("evento nao-genesis na sequencia 0 rejeitado", lambda e: e.__setitem__("sequence", 0), 1)
            bad("correcao sem evento corrigido rejeitada", lambda e: e.pop("corrects_event_id"), 5)
            bad("campo de correcao fora de evento de correcao rejeitado", lambda e: e.__setitem__("corrects_event_id", "E1"), 1)
            bad("task_started sem task_id rejeitado", lambda e: e.pop("task_id"), 2)
            bad("task_validated pelo proprio agente executor rejeitado", lambda e: e["actor"].update({"type": "agent"}), 4)
            bad("evento sem redacao de segredos rejeitado", lambda e: e.__setitem__("secrets_redacted", False), 1)
            bad("evento com raciocinio interno do modelo rejeitado", lambda e: e.__setitem__("contains_model_reasoning", True), 1)
            e = copy.deepcopy(log[1]); e.update({"event_type": "approval_granted", "actor": {"type": "agent", "id": "x"}})
            check("aprovacao registrada por agente rejeitada", not ok(e))
            e["actor"] = {"type": "user", "id": "usuario"}
            check("aprovacao registrada pelo usuario aceita", ok(e))

    n_fail = results.count(False)
    print("\n%d verificacoes, %d falhas" % (len(results), n_fail))
    return 0 if n_fail == 0 else 1


def main(argv):
    if len(argv) >= 2 and argv[1] == "verify" and len(argv) == 3:
        errs = verify_chain(read_log(argv[2]))
        print("\n".join(errs) if errs else "cadeia integra")
        return 1 if errs else 0
    if len(argv) >= 2 and argv[1] == "selftest":
        return selftest(argv[2] if len(argv) > 2 else None)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
