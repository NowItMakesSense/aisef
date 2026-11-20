#!/usr/bin/env python3

"""AISEF: configuracao do projeto, caminhos (.aisef e ~/.aisef), gravacao atomica, trava e validacao por schema.

H-01 (0.14): parte do antigo aisef_project.py. Importe pela fachada `aisef_project`, que reexporta tudo."""

import argparse
import base64
import datetime
import fnmatch
import glob
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_catalog  # noqa: E402
import audit_chain  # noqa: E402

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    import audit_signing
    HAS_CRYPTO = True
except ImportError:  # assinatura opcional
    HAS_CRYPTO = False

class _LazySerialization:
    """`cryptography...serialization` custa ~130 ms de import; os hooks so precisam dele fora do caminho quente."""

    def __getattr__(self, name):
        from cryptography.hazmat.primitives import serialization as real
        return getattr(real, name)


serialization = _LazySerialization()
# PKCS8 de uma chave Ed25519 tem sempre este prefixo DER seguido dos 32 bytes da chave
_ED25519_PKCS8_PREFIX = bytes.fromhex("302e020100300506032b657004220420")


def _load_private_key(pem_bytes):
    """Le a chave privada sem importar `serialization` no caso comum (PKCS8 Ed25519 sem senha)."""
    body = b"".join(l for l in pem_bytes.splitlines() if l and not l.startswith(b"-----"))
    der = base64.b64decode(body)
    if len(der) == 48 and der.startswith(_ED25519_PKCS8_PREFIX):
        return Ed25519PrivateKey.from_private_bytes(der[16:])
    return serialization.load_pem_private_key(pem_bytes, password=None)

KEY_ID = "audit-key-1"
SUBDIRS = ["contracts/features", "contracts/tasks", "contracts/agents", "blueprints", "approvals",
           "authorizations", "reports", "audit", "keys", "panel", "knowledge"]


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


def iso_in(**delta):
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(**delta)).astimezone().isoformat(timespec="seconds")


def home_dir():
    return os.environ.get("AISEF_HOME") or os.path.join(os.path.expanduser("~"), ".aisef")


def aisef_dir(project):
    return os.path.join(project, ".aisef")


def load_config(project):
    with open(os.path.join(aisef_dir(project), "config.json"), encoding="utf-8") as fh:
        return json.load(fh)


GIT_DEFAULTS = {"branch_per_feature": False, "delete_branch_after_merge": False, "branch_prefix": "feat/",
                "remote": "origin", "base_branch": "main"}


def git_settings(cfg):
    """Opcoes Git do projeto (config.json -> git). Devolve (valores com padroes, problemas).
    branch_per_feature: criar uma branch ao iniciar cada feature; delete_branch_after_merge: depois do merge
    confirmado do PR, apagar a branch remota e a local (cada exclusao e operacao Git reforcada)."""
    raw = cfg.get("git", {})
    out, problems = dict(GIT_DEFAULTS), []
    if not isinstance(raw, dict):
        return out, ["git deve ser um objeto"]
    for key, value in raw.items():
        if key not in GIT_DEFAULTS:
            problems.append("git.%s: chave desconhecida (aceitas: %s)" % (key, ", ".join(sorted(GIT_DEFAULTS))))
        elif type(value) is not type(GIT_DEFAULTS[key]):
            problems.append("git.%s: esperado %s" % (key, "booleano" if isinstance(GIT_DEFAULTS[key], bool) else "texto"))
        elif isinstance(value, str) and not re.match(r"^[A-Za-z0-9._/-]{1,60}$", value):
            problems.append("git.%s: valor invalido para nome Git (%r)" % (key, value))
        else:
            out[key] = value
    return out, problems


# Graphify (grafo de docs e decisoes): padrao em projeto novo desde a 0.11.0 (o init grava enabled=true; recusar no
# aisef-init grava false). Projeto sem a chave fica como antes (desligado). backend "none" = so o passo estrutural,
# nada vai a provedor de modelo; "ollama" = modelo local; "auto" = o que o Graphify detectar (envia docs).
GRAPHIFY_DEFAULTS = {"enabled": False, "backend": "none", "paths": ["docs", ".aisef"], "graph": "graphify-out/graph.json"}
GRAPHIFY_BACKENDS = ("none", "ollama", "auto")
GRAPHIFY_SOURCE_EXT = (".md", ".json", ".txt", ".rst", ".yaml", ".yml")
GRAPHIFY_SKIP = {"audit", "runtime", "panel", "keys", "session", "telemetry", "graphify-out", "node_modules", ".git"}


def graphify_settings(cfg):
    """Opcoes do Graphify (config.json -> graphify). Devolve (valores com padroes, problemas)."""
    raw = cfg.get("graphify", {})
    out, problems = dict(GRAPHIFY_DEFAULTS), []
    if not isinstance(raw, dict):
        return out, ["graphify deve ser um objeto"]
    for key, value in raw.items():
        if key not in GRAPHIFY_DEFAULTS:
            problems.append("graphify.%s: chave desconhecida (aceitas: %s)" % (key, ", ".join(sorted(GRAPHIFY_DEFAULTS))))
        elif key == "enabled" and not isinstance(value, bool):
            problems.append("graphify.enabled: esperado booleano")
        elif key == "backend" and value not in GRAPHIFY_BACKENDS:
            problems.append("graphify.backend: use %s" % ", ".join(GRAPHIFY_BACKENDS))
        elif key == "paths" and not (isinstance(value, list) and value and all(
                isinstance(p, str) and p and not os.path.isabs(p) and ".." not in p.replace("\\", "/").split("/")
                for p in value)):
            problems.append("graphify.paths: lista de caminhos relativos ao projeto, sem '..'")
        elif key == "graph" and not (isinstance(value, str) and value.endswith(".json") and not os.path.isabs(value)
                                     and ".." not in value.replace("\\", "/").split("/")):
            problems.append("graphify.graph: caminho relativo de um .json, sem '..'")
        else:
            out[key] = value
    return out, problems


def graphify_status(project, cfg=None, max_files=5000):
    """Estado do grafo do Graphify: ligado?, existe?, velho? (alguma fonte em `paths` mais nova que o graph.json).
    Barato: so stat, no maximo `max_files` arquivos, pula log, runtime, painel e chaves."""
    cfg = load_config(project) if cfg is None else cfg
    gs, problems = graphify_settings(cfg)
    graph = os.path.join(project, gs["graph"])
    st = {"enabled": gs["enabled"], "backend": gs["backend"], "graph": gs["graph"], "exists": os.path.isfile(graph),
          "stale": False, "newer_source": None, "problems": problems}
    if not (st["enabled"] and st["exists"]):
        return st
    built = os.path.getmtime(graph)
    seen = 0
    for rel in gs["paths"]:
        top = os.path.join(project, rel)
        for dirpath, dirnames, filenames in os.walk(top):
            dirnames[:] = [d for d in dirnames if d not in GRAPHIFY_SKIP]
            for name in filenames:
                if not name.endswith(GRAPHIFY_SOURCE_EXT):
                    continue
                seen += 1
                path = os.path.join(dirpath, name)
                try:
                    if os.path.getmtime(path) > built:
                        st["stale"], st["newer_source"] = True, os.path.relpath(path, project).replace("\\", "/")
                        return st
                except OSError:
                    continue
                if seen >= max_files:
                    return st
    return st


def private_key_path(project_id, key_id=KEY_ID):
    return os.path.join(home_dir(), "keys", project_id, key_id + ".pem")


def anchors_path(project_id):
    return os.path.join(home_dir(), "anchors", project_id + ".jsonl")


def external_head_path(project_id):
    return os.path.join(home_dir(), "heads", project_id + ".json")


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


class Lock:
    """Lock por arquivo exclusivo: varias sessoes/hooks podem anexar ao mesmo log."""

    def __init__(self, path, timeout=10.0):
        self.path, self.timeout = path, timeout

    def __enter__(self):
        deadline = time.time() + self.timeout
        while True:
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except FileExistsError:
                if time.time() > deadline:
                    raise TimeoutError("log de auditoria travado: " + self.path)
                time.sleep(0.05)

    def __exit__(self, *exc):
        os.close(self.fd)
        os.remove(self.path)


def _plugin_version():
    try:
        with open(os.path.join(os.path.dirname(HERE), ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
            return json.load(fh)["version"]
    except (OSError, ValueError, KeyError):
        return "0.0.0"


PROFILES = ("solo", "team", "regulated")  # L-04: projeto novo e solo; antigo vira team no migrate


def validate(doc, schema_file):
    """Valida contra o schema quando jsonschema existe; sem ela, o aisef-check pega depois."""
    try:
        import jsonschema
    except ImportError:
        return []
    with open(os.path.join(HERE, schema_file), encoding="utf-8") as fh:
        schema = json.load(fh)
    v = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    return ["%s: %s" % ("/".join(map(str, e.absolute_path)) or "(raiz)", e.message) for e in v.iter_errors(doc)]
