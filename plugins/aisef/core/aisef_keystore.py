#!/usr/bin/env python3
"""Onde fica a chave privada do log (0.17, E-02, ADR 0031): arquivo ou cofre do sistema.

`audit.key_store` no .aisef/config.json:
- "file" (padrao): PEM em ~/.aisef/keys/<projeto>/<chave>.pem, com permissao 600. Qualquer processo do usuario le.
- "os": cofre do sistema. No lugar do PEM fica um marcador <chave>.pem.os (JSON, sem segredo legivel):
  * Windows: DPAPI (CryptProtectData por ctypes). O marcador guarda o blob cifrado, que so abre na conta do
    Windows que o gravou (outra conta, outra maquina ou o disco copiado nao abrem);
  * macOS: Keychain (`security`, segredo pelo stdin de `security -i`, nunca na linha de comando);
  * Linux: Secret Service (`secret-tool`, segredo pelo stdin).

O cofre protege contra copia do arquivo (backup, sincronizacao, disco, outra conta) e contra quem le arquivos soltos.
Nao protege contra codigo rodando na mesma sessao do usuario, que pode pedir ao cofre como o AISEF pede.

    python -I aisef_keystore.py status --project-id PRJ
"""
import base64
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVICE = "aisef"
MARK = ".os"


def _paths(project_id, key_id):
    sys.path.insert(0, HERE)
    import aisef_base
    pem = aisef_base.private_key_path(project_id, key_id)
    return pem, pem + MARK


def _account(project_id, key_id):
    return "%s/%s" % (project_id, key_id)


def store_of(cfg):
    return ((cfg or {}).get("audit") or {}).get("key_store") or "file"


# --- backends do cofre ----------------------------------------------------------------------------------------------

class VaultError(RuntimeError):
    pass


def _dpapi(data, account, protect):
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(raw):
        buf = ctypes.create_string_buffer(raw, len(raw))
        return BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    fn.argtypes = [ctypes.POINTER(BLOB), ctypes.c_void_p, ctypes.POINTER(BLOB), ctypes.c_void_p, ctypes.c_void_p,
                   wintypes.DWORD, ctypes.POINTER(BLOB)]
    fn.restype = wintypes.BOOL
    inb, k1 = blob(data)
    ent, k2 = blob(b"aisef-audit-key:" + account.encode("utf-8"))  # amarra o blob a esta chave deste projeto
    desc = ctypes.c_wchar_p("aisef " + account) if protect else None
    out = BLOB()
    if not fn(ctypes.byref(inb), desc, ctypes.byref(ent), None, None, 1, ctypes.byref(out)):  # 1 = UI_FORBIDDEN
        raise VaultError("DPAPI recusou (%s)" % ctypes.WinError().strerror)
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


def _run(cmd, stdin=None):
    try:
        r = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VaultError("%s falhou (%s)" % (cmd[0], exc))
    if r.returncode != 0:
        raise VaultError("%s saiu %d: %s" % (cmd[0], r.returncode, (r.stderr or r.stdout).strip()[:200]))
    return r.stdout


def backend():
    """Nome do cofre deste sistema, ou None."""
    if sys.platform == "win32":
        return "dpapi"
    if sys.platform == "darwin" and shutil.which("security"):
        return "keychain"
    if sys.platform.startswith("linux") and shutil.which("secret-tool"):
        return "secret-service"
    return None


def available():
    """(ok, motivo). O Secret Service precisa de um chaveiro rodando (gnome-keyring, KWallet) na sessao."""
    name = backend()
    if not name:
        return False, {"darwin": "comando security nao encontrado"}.get(
            sys.platform, "secret-tool nao encontrado (instale libsecret-tools e um chaveiro, ex.: gnome-keyring)")
    if name == "secret-service":
        # sem D-Bus ou sem chaveiro o secret-tool reclama no stderr; busca sem resultado sai 1 calada
        try:
            r = subprocess.run(["secret-tool", "lookup", "service", SERVICE, "account", "aisef-probe"],
                               capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, "secret-tool falhou (%s)" % exc
        if r.stderr.strip():
            return False, "Secret Service sem chaveiro na sessao: %s" % r.stderr.strip()[:200]
    return True, name


def _put(name, account, secret):
    """Grava o segredo (texto) no cofre; devolve o marcador."""
    if name == "dpapi":
        return {"backend": name, "blob": base64.b64encode(_dpapi(secret.encode(), account, True)).decode()}
    if name == "keychain":
        line = 'add-generic-password -U -a "%s" -s "%s" -w "%s"\n' % (account, SERVICE, secret)
        _run(["security", "-i"], stdin=line)
    elif name == "secret-service":
        _run(["secret-tool", "store", "--label", "AISEF " + account, "service", SERVICE, "account", account],
             stdin=secret)
    else:
        raise VaultError("cofre desconhecido: %s" % name)
    return {"backend": name}


def _get(marker, account):
    name = marker.get("backend")
    if name == "dpapi":
        if sys.platform != "win32":
            raise VaultError("a chave esta no DPAPI do Windows; so abre la, na mesma conta")
        return _dpapi(base64.b64decode(marker["blob"]), account, False).decode()
    if name == "keychain":
        return _run(["security", "find-generic-password", "-a", account, "-s", SERVICE, "-w"]).strip()
    if name == "secret-service":
        out = _run(["secret-tool", "lookup", "service", SERVICE, "account", account]).strip()
        if not out:
            raise VaultError("o Secret Service nao tem a chave %s" % account)
        return out
    raise VaultError("cofre desconhecido no marcador: %s" % name)


def _drop(marker, account):
    name = marker.get("backend")
    try:
        if name == "keychain":
            _run(["security", "delete-generic-password", "-a", account, "-s", SERVICE])
        elif name == "secret-service":
            _run(["secret-tool", "clear", "service", SERVICE, "account", account])
    except VaultError:
        pass


# --- API usada pelo log ---------------------------------------------------------------------------------------------

def locate(project_id, key_id):
    """"file", "os" ou None."""
    pem, mark = _paths(project_id, key_id)
    if os.path.exists(pem):
        return "file"
    if os.path.exists(mark):
        return "os"
    return None


def read(project_id, key_id):
    """O PEM da chave privada (bytes), ou None se ela nao existe. Cofre que nao abre levanta VaultError."""
    pem, mark = _paths(project_id, key_id)
    if os.path.exists(pem):
        with open(pem, "rb") as fh:
            return fh.read()
    if not os.path.exists(mark):
        return None
    try:
        with open(mark, encoding="utf-8") as fh:
            marker = json.load(fh)
    except (OSError, ValueError) as exc:
        raise VaultError("marcador do cofre ilegivel: %s (%s)" % (mark, exc))
    return base64.b64decode(_get(marker, _account(project_id, key_id)))


def _private(path):
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def write(project_id, key_id, pem_bytes, store="file"):
    """Grava a chave no arquivo ou no cofre. Devolve onde ficou."""
    pem, mark = _paths(project_id, key_id)
    os.makedirs(os.path.dirname(pem), exist_ok=True)
    if store == "os":
        ok, why = available()
        if not ok:
            raise VaultError("audit.key_store = os, mas este sistema nao tem cofre utilizavel: %s" % why)
        marker = _put(why, _account(project_id, key_id), base64.b64encode(pem_bytes).decode())
        tmp = mark + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(marker, fh)
        _private(tmp)
        os.replace(tmp, mark)
        return "os"
    with open(pem, "wb") as fh:
        fh.write(pem_bytes)
    _private(pem)
    return "file"


def remove(project_id, key_id):
    pem, mark = _paths(project_id, key_id)
    if os.path.exists(mark):
        try:
            with open(mark, encoding="utf-8") as fh:
                _drop(json.load(fh), _account(project_id, key_id))
        except (OSError, ValueError):
            pass
        os.remove(mark)
    if os.path.exists(pem):
        os.remove(pem)


def local_keys(project_id):
    """Chaves privadas deste projeto nesta maquina (dono e streams), arquivo ou cofre."""
    pem, _ = _paths(project_id, "x")
    d = os.path.dirname(pem)
    names = set()
    for n in os.listdir(d) if os.path.isdir(d) else []:
        if n.endswith(".pem"):
            names.add(n[:-4])
        elif n.endswith(".pem" + MARK):
            names.add(n[:-len(".pem" + MARK)])
    return sorted(names)


def move(project_id, key_id, to):
    """Leva uma chave para `to` ("file" ou "os"), confere a ida e volta e so entao apaga a origem."""
    where = locate(project_id, key_id)
    if where is None:
        raise VaultError("chave %s/%s nao encontrada" % (project_id, key_id))
    if where == to:
        return False
    pem_bytes = read(project_id, key_id)
    pem, mark = _paths(project_id, key_id)
    if to == "os":
        write(project_id, key_id, pem_bytes, "os")
        os.rename(pem, pem + ".bak")  # tira o arquivo do caminho antes de conferir: a leitura tem que vir do cofre
        try:
            if read(project_id, key_id) != pem_bytes:
                raise VaultError("a chave lida do cofre nao e a mesma gravada")
        except Exception:
            os.rename(pem + ".bak", pem)
            raise
        os.remove(pem + ".bak")  # o PEM sai do disco (sem garantia de apagamento fisico; ver ADR 0031)
    else:
        with open(mark, encoding="utf-8") as fh:
            marker = json.load(fh)
        write(project_id, key_id, pem_bytes, "file")
        _drop(marker, _account(project_id, key_id))
        os.remove(mark)
    return True


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["status"])
    p.add_argument("--project-id", required=True)
    a = p.parse_args(argv)
    ok, why = available()
    print("cofre deste sistema: %s" % (why if ok else "indisponivel (%s)" % why))
    for k in local_keys(a.project_id):
        print("  %s: %s" % (k, locate(a.project_id, k)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
