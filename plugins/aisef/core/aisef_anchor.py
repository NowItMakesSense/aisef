#!/usr/bin/env python3
"""Carimbo de tempo RFC 3161 nos marcos do log (0.17, E-03, ADR 0030).

A assinatura Ed25519 prova QUEM escreveu o log; nao prova QUANDO. Quem tem a chave pode reescrever o passado e
reassinar. Um carimbo de uma TSA (autoridade de carimbo de tempo, terceiro independente) sobre o hash do ultimo
evento prova que aquele evento, e pela cadeia de hash tudo antes dele, ja existia naquela data.

    python -I aisef_anchor.py stamp  --project . [--milestone "aceite FEAT-001"] [--url URL]
    python -I aisef_anchor.py verify --project .

- O pedido (TimeStampReq) e montado em DER a mao: SHA-256 = o hash do evento (ja e um SHA-256), nonce aleatorio e
  certReq. Vai por HTTP POST a TSA (`audit.tsa_url` no config.json; o comando stamp usa freetsa.org sem ela).
- A resposta fica em .aisef/audit/timestamps/<sequencia>.tsr (a resposta DER, como o openssl le) com um .json ao lado.
- Roda nos marcos, nunca a cada evento: no aceite de feature (quando `audit.tsa_url` esta configurado) e no
  aisef-verify da PR com --stamp. Sem rede vira aviso e o pedido fica pendente (pending.json) ate o proximo marco.
- Verificacao: o hash e o nonce do token tem que bater com o evento do log. A cadeia de certificados da TSA so e
  conferida com `openssl ts -verify` e `audit.tsa_ca_file`; sem eles, sai um aviso dizendo que ela nao foi conferida.
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TSA = "https://freetsa.org/tsr"
SHA256_OID = "2.16.840.1.101.3.4.2.1"
TSTINFO_OID = "1.2.840.113549.1.9.16.1.4"
SIGNED_DATA_OID = "1.2.840.113549.1.7.2"


# --- DER minimo ---------------------------------------------------------------------------------------------------

def tlv(tag, body):
    n = len(body)
    if n < 0x80:
        size = bytes([n])
    else:
        raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
        size = bytes([0x80 | len(raw)]) + raw
    return bytes([tag]) + size + body


def der_int(value):
    return tlv(0x02, value.to_bytes(value.bit_length() // 8 + 1, "big", signed=True))


def der_oid(dotted):
    parts = [int(x) for x in dotted.split(".")]
    out = bytearray([40 * parts[0] + parts[1]])
    for p in parts[2:]:
        chunk = [p & 0x7F]
        p >>= 7
        while p:
            chunk.append(0x80 | (p & 0x7F))
            p >>= 7
        out += bytes(reversed(chunk))
    return tlv(0x06, bytes(out))


def seq(*items):
    return tlv(0x30, b"".join(items))


def children(buf):
    """[(tag, corpo)] dos elementos DER em sequencia dentro de `buf`."""
    out, i = [], 0
    while i < len(buf):
        tag, n = buf[i], buf[i + 1]
        i += 2
        if n & 0x80:
            k = n & 0x7F
            if not k or k > 4:
                raise ValueError("comprimento DER invalido")
            n = int.from_bytes(buf[i:i + k], "big")
            i += k
        if i + n > len(buf):
            raise ValueError("DER truncado")
        out.append((tag, buf[i:i + n]))
        i += n
    return out


def oid_text(body):
    first = body[0]
    parts, val = [first // 40, first % 40], 0
    for b in body[1:]:
        val = (val << 7) | (b & 0x7F)
        if not b & 0x80:
            parts.append(val)
            val = 0
    return ".".join(str(p) for p in parts)


def _one(buf, tag, what):
    items = children(buf)
    if not items or items[0][0] != tag:
        raise ValueError("resposta da TSA sem %s" % what)
    return items[0][1]


# --- pedido e resposta --------------------------------------------------------------------------------------------

def request(digest, nonce):
    """TimeStampReq em DER: version 1, messageImprint (SHA-256), nonce, certReq TRUE."""
    imprint = seq(seq(der_oid(SHA256_OID), b"\x05\x00"), tlv(0x04, digest))
    return seq(der_int(1), imprint, der_int(nonce), tlv(0x01, b"\xff"))


def parse_request(der):
    """(digest, nonce) de um TimeStampReq (usado pela TSA falsa dos testes)."""
    items = children(_one(der, 0x30, "pedido"))
    digest = children(items[1][1])[1][1]
    nonce = next(int.from_bytes(b, "big", signed=True) for t, b in items[2:] if t == 0x02)
    return digest, nonce


def parse_response(der):
    """TimeStampResp -> {status, digest, hash_oid, nonce, gen_time, serial}. Levanta ValueError se nao der para ler."""
    items = children(_one(der, 0x30, "TimeStampResp"))
    status = int.from_bytes(children(items[0][1])[0][1], "big")
    if status not in (0, 1):
        texts = [b.decode("utf-8", "replace") for t, b in children(items[0][1])[1:] if t == 0x30
                 for t2, b in children(b) if t2 == 0x0C]
        raise ValueError("a TSA recusou o pedido (status %d%s)" % (status, ": " + "; ".join(texts) if texts else ""))
    if len(items) < 2:
        raise ValueError("a TSA respondeu sem token")
    ci = children(items[1][1])
    if oid_text(ci[0][1]) != SIGNED_DATA_OID:
        raise ValueError("token nao e SignedData")
    sd = children(_one(ci[1][1], 0x30, "SignedData"))
    encap = children(sd[2][1])
    if oid_text(encap[0][1]) != TSTINFO_OID:
        raise ValueError("token sem TSTInfo")
    tst = children(_one(_one(encap[1][1], 0x04, "eContent"), 0x30, "TSTInfo"))
    imprint = children(tst[2][1])
    gen = tst[4][1].decode("ascii")
    nonce = next((int.from_bytes(b, "big", signed=True) for t, b in tst[5:] if t == 0x02), None)
    return {"status": status, "hash_oid": oid_text(children(imprint[0][1])[0][1]), "digest": imprint[1][1],
            "serial": int.from_bytes(tst[3][1], "big"), "gen_time": _gen_time(gen), "nonce": nonce}


def _gen_time(text):
    base = text.rstrip("Z").split(".")[0]
    return datetime.datetime.strptime(base, "%Y%m%d%H%M%S").replace(tzinfo=datetime.timezone.utc).isoformat()


def check_token(info, digest, nonce):
    """Problemas do token frente ao que foi pedido (lista vazia = confere)."""
    out = []
    if info["hash_oid"] != SHA256_OID:
        out.append("o token nao usa SHA-256")
    if info["digest"] != digest:
        out.append("o hash do token nao e o do evento")
    if info["nonce"] != nonce:
        out.append("o nonce do token nao e o do pedido (resposta reaproveitada?)")
    return out


# --- carimbar e conferir ------------------------------------------------------------------------------------------

def http_fetch(url, body, timeout):
    import urllib.request
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/timestamp-query",
                                                          "Accept": "application/timestamp-reply",
                                                          "User-Agent": "aisef-anchor"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (URL do config do usuario)
        return resp.read()


def _tsdir(project):
    return os.path.join(project, ".aisef", "audit", "timestamps")


def _cfg(project):
    path = os.path.join(project, ".aisef", "config.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh).get("audit") or {}


def _head(project):
    sys.path.insert(0, HERE)
    import aisef_audit_log
    return aisef_audit_log.last_event(os.path.join(project, ".aisef", "audit"))


def _write(path, data, binary=False):
    tmp = path + ".tmp"
    with open(tmp, "wb" if binary else "w", **({} if binary else {"encoding": "utf-8"})) as fh:
        fh.write(data)
    os.replace(tmp, path)


def stamp(project, milestone="", url=None, fetch=None, now=None, timeout=10):
    """Carimba o ultimo evento. {ok, sequence, file, gen_time} ou {ok: False, warning}; nunca levanta por rede."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    url = url or _cfg(project).get("tsa_url") or DEFAULT_TSA
    head = _head(project)
    if not head:
        return {"ok": False, "warning": "sem log para carimbar"}
    os.makedirs(_tsdir(project), exist_ok=True)
    base = os.path.join(_tsdir(project), "%06d" % head["sequence"])
    if os.path.exists(base + ".json"):
        with open(base + ".json", encoding="utf-8") as fh:
            meta = json.load(fh)
        return {"ok": True, "sequence": head["sequence"], "file": base + ".tsr", "gen_time": meta["gen_time"],
                "already": True}
    digest, nonce = bytes.fromhex(head["hash"]), int.from_bytes(os.urandom(8), "big") >> 1
    try:
        der = (fetch or http_fetch)(url, request(digest, nonce), timeout)
        info = parse_response(der)
        problems = check_token(info, digest, nonce)
        if problems:
            raise ValueError("; ".join(problems))
    except Exception as exc:  # sem rede, TSA fora ou resposta ruim: aviso, nunca trava o marco
        pend = {"milestone": milestone, "sequence": head["sequence"], "tsa_url": url, "error": str(exc)[:300],
                "at": now.isoformat()}
        _write(os.path.join(_tsdir(project), "pending.json"), json.dumps(pend, ensure_ascii=False, indent=2))
        return {"ok": False, "sequence": head["sequence"],
                "warning": "carimbo de tempo NAO obtido em %s (%s); fica pendente para o proximo marco"
                % (url, str(exc)[:200])}
    _write(base + ".tsr", der, binary=True)
    meta = {"sequence": head["sequence"], "event_hash": head["hash"], "nonce": "%x" % nonce, "tsa_url": url,
            "gen_time": info["gen_time"], "serial": "%x" % info["serial"], "milestone": milestone,
            "stamped_at": now.isoformat()}
    _write(base + ".json", json.dumps(meta, ensure_ascii=False, indent=2))
    try:
        os.remove(os.path.join(_tsdir(project), "pending.json"))
    except OSError:
        pass
    return {"ok": True, "sequence": head["sequence"], "file": base + ".tsr", "gen_time": info["gen_time"]}


def milestone(project, name):
    """Gancho dos marcos: carimba so quando o projeto configurou `audit.tsa_url`. None quando desligado."""
    if not _cfg(project).get("tsa_url"):
        return None
    return stamp(project, milestone=name)


def _openssl_verify(tsr, event_hash, cfg):
    ca = cfg.get("tsa_ca_file")
    exe = shutil.which("openssl")
    if not (ca and exe):
        return None
    cmd = [exe, "ts", "-verify", "-in", tsr, "-digest", event_hash, "-CAfile", ca]
    if cfg.get("tsa_cert_file"):
        cmd += ["-untrusted", cfg["tsa_cert_file"]]
    env = dict(os.environ)
    if env.get("OPENSSL_CONF") and not os.path.exists(env["OPENSSL_CONF"]):
        env.pop("OPENSSL_CONF")  # instalador alheio (ex.: PostgreSQL no Windows) deixa apontando para arquivo inexistente
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return r.returncode == 0, (r.stdout + r.stderr).strip()[-200:]


def verify_tokens(project, log):
    """(erros, avisos) dos carimbos guardados frente ao log: o evento carimbado continua la, com o mesmo hash?"""
    tdir = _tsdir(project)
    if not os.path.isdir(tdir):
        return [], []
    by_seq = {ev["sequence"]: ev for ev in log}
    cfg, errors, warnings, unchained = _cfg(project), [], [], 0
    for name in sorted(os.listdir(tdir)):
        if not name.endswith(".json") or name == "pending.json":
            continue
        where = "carimbo %s" % name[:-5]
        try:
            with open(os.path.join(tdir, name), encoding="utf-8") as fh:
                meta = json.load(fh)
            with open(os.path.join(tdir, name[:-5] + ".tsr"), "rb") as fh:
                info = parse_response(fh.read())
            problems = check_token(info, bytes.fromhex(meta["event_hash"]), int(meta["nonce"], 16))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append("%s ilegivel (%s)" % (where, exc))
            continue
        errors += ["%s: %s" % (where, p) for p in problems]
        ev = by_seq.get(meta["sequence"])
        if ev is None:
            errors.append("%s: o evento %s nao existe mais no log (truncado?)" % (where, meta["sequence"]))
        elif ev["hash"] != meta["event_hash"]:
            errors.append("%s: o evento %s foi reescrito depois do carimbo de %s" % (where, meta["sequence"], info["gen_time"]))
        res = _openssl_verify(os.path.join(tdir, name[:-5] + ".tsr"), meta["event_hash"], cfg)
        if res is None:
            unchained += 1
        elif not res[0]:
            errors.append("%s: openssl ts -verify recusou a cadeia da TSA (%s)" % (where, res[1]))
    if unchained:
        warnings.append("%d carimbo(s) com hash e nonce conferidos, mas a cadeia de certificados da TSA nao foi "
                        "conferida (precisa de openssl e audit.tsa_ca_file)" % unchained)
    pend = os.path.join(tdir, "pending.json")
    if os.path.exists(pend):
        try:
            with open(pend, encoding="utf-8") as fh:
                p = json.load(fh)
            warnings.append("carimbo de tempo pendente desde %s (%s): rode aisef_anchor.py stamp" % (p.get("at"), p.get("error")))
        except (OSError, ValueError):
            warnings.append("carimbo de tempo pendente (pending.json ilegivel)")
    return errors, warnings


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=("stamp", "verify"))
    p.add_argument("--project", default=".")
    p.add_argument("--milestone", default="manual")
    p.add_argument("--url")
    a = p.parse_args(argv)
    project = os.path.abspath(a.project)
    if a.command == "stamp":
        res = stamp(project, a.milestone, a.url)
        print(("carimbo do evento %s: %s (%s)" % (res["sequence"], res["gen_time"], res["file"])) if res["ok"]
              else "AVISO: " + res["warning"])
        return 0 if res["ok"] else 2
    sys.path.insert(0, HERE)
    import audit_chain
    errors, warnings = verify_tokens(project, audit_chain.read_stream(os.path.join(project, ".aisef", "audit")))
    for e in errors:
        print("ERRO  " + e)
    for w in warnings:
        print("AVISO " + w)
    if not errors:
        print("carimbos conferem com o log")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
