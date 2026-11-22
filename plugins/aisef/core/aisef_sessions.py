#!/usr/bin/env python3
"""AISEF sessions: outra sessao do Claude Code trabalhando no mesmo projeto (outra pasta/worktree ou a mesma).

Sem isso, duas sessoes refaziam o mesmo trabalho sem saber uma da outra, e um `git add -A` podia levar para o commit o
trabalho da outra. Cada worktree grava no .aisef do repositorio principal (L-02a), entao as sessoes se enxergam aqui:

- `touch`: batimento da sessao (o gateway, a cada chamada) e os arquivos que ela editou (o hook de auditoria).
  Fica em .aisef/runtime/sessions/<session_id>.json, fora do Git. Subagentes herdam o session_id da sessao-mae, e as
  worktrees das fatias da propria sessao ficam marcadas como dela: nao sao "outra sessao".
- `overlap`: o arquivo que esta sessao vai editar foi editado por outra e ainda esta alterado sem commit la.
- `concurrent`: mudancas sem commit de outras sessoes (e de worktrees recentes sem sessao conhecida), para mostrar ao
  usuario antes de commit, push, PR ou merge.

Uso:
    python3 -I aisef_sessions.py status --project REPO [--session ID] [--diff]

Somente stdlib. Le o .git direto quando pode; `git` so roda para conferir o estado de outra worktree.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys

ACTIVE_S = 30 * 60          # sessao com batimento ha menos que isso: ativa agora
RECENT_S = 12 * 3600        # sessao vista ha menos que isso: as mudancas sem commit dela ainda contam
UNKNOWN_RECENT_S = 2 * 3600  # worktree sem sessao registrada: so conta se alguem mexeu nela ha pouco
KEEP_DAYS = 7
MAX_FILES = 300
HEARTBEAT_S = 20            # batimento sem arquivo novo: grava no maximo a cada 20 s


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(t):
    return t.isoformat(timespec="seconds")


def _parse(s):
    try:
        d = datetime.datetime.fromisoformat((s or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)


def _key(path):
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _dir(project):
    d = os.path.join(project, ".aisef", "runtime", "sessions")
    os.makedirs(d, exist_ok=True)
    gi = os.path.join(project, ".aisef", "runtime", ".gitignore")
    if not os.path.exists(gi):
        with open(gi, "w", encoding="utf-8") as fh:
            fh.write("*\n")
    return d


def _safe_id(sid):
    return "".join(c for c in str(sid) if c.isalnum() or c in "-_")[:80]


def worktree_of(path):
    """Pasta da worktree (a que tem o `.git`, diretorio ou arquivo) que contem `path`, ou None."""
    d = os.path.abspath(path or ".")
    if not os.path.isdir(d):
        d = os.path.dirname(d)
    while True:
        if os.path.exists(os.path.join(d, ".git")):
            return os.path.normpath(d)
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def _rel(path, wt):
    try:
        return os.path.relpath(os.path.abspath(path), wt).replace("\\", "/")
    except ValueError:
        return None


def _load(fp):
    try:
        with open(fp, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _save(fp, rec):
    tmp = fp + ".tmp%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, ensure_ascii=False)
    os.replace(tmp, fp)


def touch(project, session_id, cwd=None, file=None, now=None):
    """Batimento da sessao; com `file`, marca o arquivo editado (caminho relativo a worktree dele)."""
    if not session_id:
        return None
    now = now or _now()
    d = _dir(project)
    fp = os.path.join(d, _safe_id(session_id) + ".json")
    rec = _load(fp)
    if rec is None:
        rec = {"session_id": session_id, "started_at": _iso(now), "worktrees": {}, "files": {}}
        _prune(d, now)
    wt_cwd = worktree_of(cwd) if cwd else None
    last = _parse(rec.get("last_at"))
    if not file and last and (now - last).total_seconds() < HEARTBEAT_S and \
            (not wt_cwd or wt_cwd in rec.get("worktrees", {})):
        return rec  # nada novo: poupa a escrita a cada chamada
    rec["last_at"] = _iso(now)
    if cwd:
        rec["cwd"] = cwd
    if wt_cwd:
        rec.setdefault("worktrees", {})[wt_cwd] = _iso(now)
    if file:
        wt = worktree_of(file)
        rel = _rel(file, wt) if wt else None
        if wt and rel and not rel.startswith(".."):
            rec.setdefault("worktrees", {})[wt] = _iso(now)
            files = rec.setdefault("files", {})
            files[wt + "|" + rel] = _iso(now)
            if len(files) > MAX_FILES:
                for k in sorted(files, key=lambda k: files[k])[:len(files) - MAX_FILES]:
                    del files[k]
    _save(fp, rec)
    return rec


def _prune(d, now):
    for name in os.listdir(d):
        fp = os.path.join(d, name)
        try:
            if (now.timestamp() - os.path.getmtime(fp)) > KEEP_DAYS * 86400:
                os.remove(fp)
        except OSError:
            pass


def sessions(project):
    d = os.path.join(project, ".aisef", "runtime", "sessions")
    out = []
    try:
        names = os.listdir(d)
    except OSError:
        return out
    for name in names:
        if name.endswith(".json"):
            rec = _load(os.path.join(d, name))
            if rec and rec.get("session_id"):
                out.append(rec)
    return out


def _age(rec, now):
    t = _parse(rec.get("last_at"))
    return (now - t).total_seconds() if t else None


def others(project, session_id, now=None, window=RECENT_S):
    now = now or _now()
    return [r for r in sessions(project)
            if r["session_id"] != session_id and _age(r, now) is not None and _age(r, now) <= window]


def _git(wt, *args, timeout=15):
    try:
        r = subprocess.run(["git", "-C", wt] + list(args), capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def dirty(wt, paths=None):
    """[(codigo, caminho)] alterados sem commit na worktree (inclui nao rastreados). None se o git falhar."""
    out = _git(wt, "status", "--porcelain=v1", "-uall", *(["--"] + list(paths) if paths else []))
    if out is None:
        return None
    rows = []
    for line in out.splitlines():
        if len(line) > 3:
            p = line[3:].split(" -> ")[-1].strip().strip('"')
            rows.append((line[:2].strip() or "?", p))
    return rows


def worktrees(path):
    """[{path, branch}] de `git worktree list --porcelain` do repositorio que contem `path`."""
    out = _git(path, "worktree", "list", "--porcelain")
    rows, cur = [], None
    for line in (out or "").splitlines():
        if line.startswith("worktree "):
            cur = {"path": os.path.normpath(line[9:].strip()), "branch": None}
            rows.append(cur)
        elif cur is not None and line.startswith("branch "):
            cur["branch"] = line[7:].strip().replace("refs/heads/", "", 1)
    return rows


def _branch(wt):
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import aisef_git
        return aisef_git.current_branch(wt)
    except Exception:
        return None


def _short(sid):
    return str(sid)[:8]


def _ago(seconds):
    if seconds is None:
        return "?"
    m = int(seconds // 60)
    return "agora" if m < 1 else "ha %d min" % m if m < 90 else "ha %d h" % (m // 60)


def overlap(project, session_id, file, now=None):
    """Outra sessao editou este mesmo arquivo (mesmo caminho na worktree dela) e ele continua alterado sem commit la.
    Devolve [{session, worktree, branch, file, ago, active}]. Sem candidato, nao roda git (o gateway passa aqui a cada
    edicao)."""
    now = now or _now()
    wt = worktree_of(file)
    rel = _rel(file, wt) if wt else None
    if not rel or rel.startswith(".."):
        return []
    hits = []
    for r in others(project, session_id, now):
        for k, at in (r.get("files") or {}).items():
            owt, _, orel = k.rpartition("|")
            if orel != rel or not os.path.isdir(owt):
                continue
            if not dirty(owt, [orel]):
                continue  # ja foi commitado (ou descartado) la: nao ha trabalho em paralelo
            age = _age(r, now)
            hits.append({"session": _short(r["session_id"]), "worktree": owt, "branch": _branch(owt), "file": orel,
                         "edited_at": at, "ago": _ago(age), "active": age is not None and age <= ACTIVE_S,
                         "same_dir": _key(owt) == _key(wt)})
    return hits


def concurrent(project, session_id, cwd, now=None):
    """Mudancas sem commit que nao sao desta sessao: de outras sessoes (registradas), e de worktrees sem sessao
    conhecida mexidas ha pouco. Inclui a mesma pasta quando outra sessao ativa tambem trabalha nela."""
    now = now or _now()
    if not session_id:
        return []  # sem saber quem e esta sessao, nao ha como separar o trabalho dela do das outras
    me = next((r for r in sessions(project) if r["session_id"] == session_id), None)
    here = worktree_of(cwd or project)
    mine = {_key(w) for w in ((me or {}).get("worktrees") or {})}
    if here:
        mine.add(_key(here))
    owners = {}
    oth = others(project, session_id, now)
    for r in oth:
        for w in (r.get("worktrees") or {}):
            owners.setdefault(_key(w), []).append(r)
    # worktree de fatia do AISEF (.aisef/worktrees/<T>): e de quem reservou a fatia; sem reserva de outra sessao, e
    # desta (o orquestrador criou; o subagente pode ter editado so pelo shell, sem registro de arquivo)
    slices = _key(os.path.join(project, ".aisef", "worktrees"))
    by_task = {c.get("task_id"): r for r in oth for c in (r.get("claims") or []) if c.get("task_id")}
    known = {_key(w["path"]): w for w in worktrees(here or project)}
    for k, rs in owners.items():  # worktree de outra sessao que o `worktree list` nao trouxe (outro repo? removida?)
        if k not in known:
            p = next(w for r in rs for w in r.get("worktrees", {}) if _key(w) == k)
            if os.path.isdir(p):
                known[k] = {"path": p, "branch": None}
    out = []
    for k, w in known.items():
        if k.startswith(slices + os.sep) and not owners.get(k):
            r = by_task.get(os.path.basename(w["path"]))
            if r is None:
                continue
            owners[k] = [r]
        rs = owners.get(k, [])
        if k in mine and not [r for r in rs if (_age(r, now) or 1e9) <= ACTIVE_S]:
            continue  # pasta desta sessao (ou das fatias dela) sem outra sessao ativa junto
        files = dirty(w["path"])
        if not files:
            continue
        mt = []
        for _, p in files:
            try:
                mt.append(os.path.getmtime(os.path.join(w["path"], p)))
            except OSError:
                pass
        last = max(mt) if mt else None
        if not rs and (last is None or now.timestamp() - last > UNKNOWN_RECENT_S):
            continue  # worktree esquecida, sem sessao conhecida: nao e trabalho em andamento
        if k in mine:  # mesma pasta: so os arquivos que a outra sessao editou
            theirs = {key.rpartition("|")[2] for r in rs for key in (r.get("files") or {}) if _key(key.rpartition("|")[0]) == k}
            files = [f for f in files if f[1] in theirs]
            if not files:
                continue
        stat = _git(w["path"], "diff", "--shortstat", "HEAD") or ""
        out.append({"worktree": w["path"], "branch": w.get("branch") or _branch(w["path"]),
                    "sessions": [{"session": _short(r["session_id"]), "ago": _ago(_age(r, now)),
                                  "active": (_age(r, now) or 1e9) <= ACTIVE_S} for r in rs],
                    "same_dir": k in mine, "files": files, "shortstat": stat.strip(),
                    "last_edit": _iso(datetime.datetime.fromtimestamp(last, datetime.timezone.utc)) if last else None})
    out.sort(key=lambda x: x["last_edit"] or "", reverse=True)
    return out


def render(items, limit=8):
    """Texto curto para o gateway e o doctor mostrarem ao usuario."""
    lines = []
    for it in items:
        who = ", ".join("sessao %s (%s%s)" % (s["session"], "ativa, " if s["active"] else "", s["ago"]) for s in it["sessions"]) \
            or "sem sessao do AISEF registrada"
        where = "nesta mesma pasta" if it["same_dir"] else "em %s" % it["worktree"]
        lines.append("- %s, branch %s, %s: %d arquivo(s) sem commit%s" % (
            where, it["branch"] or "?", who, len(it["files"]), (" (%s)" % it["shortstat"]) if it["shortstat"] else ""))
        for code, p in it["files"][:limit]:
            lines.append("    %s %s" % (code, p))
        if len(it["files"]) > limit:
            lines.append("    ... mais %d" % (len(it["files"]) - limit))
        lines.append("    ver o diff: git -C \"%s\" diff HEAD" % it["worktree"].replace("\\", "/"))
    return "\n".join(lines)


# ---------------------------------------------------------------- coordenacao: cada sessao numa area separada

def _static(pattern):
    """Parte fixa de um glob (ate o primeiro curinga), para comparar areas."""
    cut = min([i for i, c in enumerate(pattern) if c in "*?["] or [len(pattern)])
    return pattern[:cut]


def _norm_glob(p):
    p = str(p or "").replace("\\", "/").strip()
    while p.startswith("./"):
        p = p[2:]
    return p.rstrip("/") + "/**" if p.endswith("/") else p


def matches(rel, pattern):
    import fnmatch
    pattern = _norm_glob(pattern)
    if not pattern:
        return False
    if fnmatch.fnmatchcase(rel, pattern):
        return True
    if pattern.endswith("/**") and (rel == pattern[:-3] or rel.startswith(pattern[:-2])):
        return True
    return "*" not in pattern and "?" not in pattern and (rel == pattern or rel.startswith(pattern + "/"))


def areas_overlap(a, b):
    """Duas areas (globs) podem cobrir o mesmo arquivo. Aproximado para o lado seguro: na duvida, sobrepoe."""
    a, b = _norm_glob(a), _norm_glob(b)
    if not a or not b:
        return False
    if matches(a, b) or matches(b, a):
        return True
    sa, sb = _static(a), _static(b)
    return sa.startswith(sb) or sb.startswith(sa)


def claim(project, session_id, paths, note=None, task_id=None, now=None):
    """Reserva uma area (globs relativos a raiz do repositorio) para esta sessao. Uma reserva por task_id (ou por nota):
    reservar de novo substitui. Devolve as reservas de outras sessoes que se sobrepoem (a coordenar com o usuario)."""
    if not session_id or not paths:
        return []
    now = now or _now()
    rec = touch(project, session_id, now=now) or {}
    fp = os.path.join(_dir(project), _safe_id(session_id) + ".json")
    rec = _load(fp) or rec
    key = task_id or note or ",".join(paths)
    rec["claims"] = [c for c in rec.get("claims") or [] if (c.get("task_id") or c.get("note") or ",".join(c["paths"])) != key]
    rec["claims"].append({"paths": [_norm_glob(p) for p in paths if _norm_glob(p)], "note": note, "task_id": task_id,
                          "at": _iso(now)})
    rec["last_at"] = _iso(now)
    _save(fp, rec)
    return [c for c in others_claims(project, session_id, now)
            if any(areas_overlap(p, q) for p in rec["claims"][-1]["paths"] for q in c["paths"])]


def release(project, session_id, task_id=None):
    """Solta a reserva da fatia (task_id) ou todas as desta sessao."""
    fp = os.path.join(_dir(project), _safe_id(session_id) + ".json")
    rec = _load(fp)
    if not rec:
        return 0
    before = len(rec.get("claims") or [])
    rec["claims"] = [c for c in rec.get("claims") or [] if task_id and c.get("task_id") != task_id]
    _save(fp, rec)
    return before - len(rec["claims"])


def others_claims(project, session_id, now=None):
    """Reservas de outras sessoes ainda vistas (RECENT_S): [{session, ago, active, paths, note, task_id}]."""
    now = now or _now()
    out = []
    for r in others(project, session_id, now):
        age = _age(r, now)
        for c in r.get("claims") or []:
            out.append({"session": _short(r["session_id"]), "ago": _ago(age), "active": age is not None and age <= ACTIVE_S,
                        "paths": c.get("paths") or [], "note": c.get("note"), "task_id": c.get("task_id"),
                        "branch": _branch(r.get("cwd")) if r.get("cwd") else None})
    return out


def claimed_by_other(project, session_id, file, now=None):
    """Reserva de outra sessao que cobre este arquivo (caminho relativo a worktree dele), ou None."""
    wt = worktree_of(file)
    rel = _rel(file, wt) if wt else None
    if not rel or rel.startswith(".."):
        return None
    return next((dict(c, file=rel) for c in others_claims(project, session_id, now)
                 if any(matches(rel, p) for p in c["paths"])), None)


def _label(c):
    what = c.get("note") or (c.get("task_id") and "fatia %s" % c["task_id"]) or "trabalho"
    return "sessao %s (%s%s) em %s: %s" % (c["session"], "ativa, " if c["active"] else "", c["ago"], what,
                                            ", ".join(c["paths"][:6]) + (" ..." if len(c["paths"]) > 6 else ""))


def coordination_notice(project, session_id, now=None):
    """Aviso para ESTA sessao quando as areas das outras mudam (sessao nova, reserva nova ou solta). Devolve o texto
    uma vez por mudanca (guarda o que ja mostrou no proprio registro) ou None."""
    if not session_id:
        return None
    now = now or _now()
    cl = [c for c in others_claims(project, session_id, now) if c["active"]]
    act = [r for r in others(project, session_id, now, ACTIVE_S)]
    sig = "|".join(sorted(_label(c).split(" (")[0] + ":" + ",".join(c["paths"]) for c in cl)) + "#" + \
        ",".join(sorted(_short(r["session_id"]) for r in act))
    fp = os.path.join(_dir(project), _safe_id(session_id) + ".json")
    rec = _load(fp)
    if rec is None or rec.get("seen") == sig:
        return None
    rec["seen"] = sig
    _save(fp, rec)
    if not act:
        return None  # as outras sessoes sairam: nada a coordenar
    me = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aisef_sessions.py").replace("\\", "/")
    lines = ["AISEF: outra sessao do Claude Code esta trabalhando neste projeto agora. Coordene para cada uma ficar numa "
             "parte separada e uma nao afetar o trabalho da outra:"]
    lines += ["- " + _label(c) for c in cl] or ["- sessao %s (sem area reservada ainda)" % ", ".join(_short(r["session_id"]) for r in act)]
    lines.append("Fique fora dessas areas (o gateway pergunta antes de editar nelas). Reserve a sua antes de editar: "
                 "python3 -I %s claim --project . --session %s --paths '<globs>' --note '<o que vai fazer>'. "
                 "Se o pedido do usuario cair na area da outra sessao, mostre isso a ele e combine a divisao antes." % (me, session_id))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="AISEF: outras sessoes trabalhando no mesmo projeto")
    sub = ap.add_subparsers(dest="cmd", required=True)
    cp = sub.add_parser("claim", help="reserva uma area do projeto para esta sessao")
    cp.add_argument("--project", default=".")
    cp.add_argument("--session", required=True)
    cp.add_argument("--paths", required=True, help="globs separados por virgula, relativos a raiz do repositorio")
    cp.add_argument("--note", default=None)
    cp.add_argument("--task", default=None)
    rp = sub.add_parser("release", help="solta a reserva da fatia (--task) ou todas as desta sessao")
    rp.add_argument("--project", default=".")
    rp.add_argument("--session", required=True)
    rp.add_argument("--task", default=None)
    st = sub.add_parser("status", help="mudancas sem commit de outras sessoes e worktrees")
    st.add_argument("--project", default=".")
    st.add_argument("--session", default=os.environ.get("CLAUDE_SESSION_ID"))
    st.add_argument("--diff", action="store_true", help="mostra o diff completo de cada uma")
    st.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import aisef_git
    project = aisef_git.aisef_root(os.path.abspath(a.project))
    if a.cmd == "claim":
        clash = claim(project, a.session, [p for p in a.paths.split(",") if p.strip()], a.note, a.task)
        print("area reservada para a sessao %s: %s" % (_short(a.session), a.paths))
        if clash:
            print("ATENCAO: sobrepoe a area de outra sessao; mostre ao usuario e combine a divisao:\n"
                  + "\n".join("- " + _label(c) for c in clash))
            return 3
        return 0
    if a.cmd == "release":
        print("%d reserva(s) solta(s)" % release(project, a.session, a.task))
        return 0
    items = concurrent(project, a.session, os.path.abspath(a.project))
    cl = others_claims(project, a.session)
    if a.json:
        print(json.dumps({"changes": items, "claims": cl}, ensure_ascii=False, indent=2))
        return 0
    if cl:
        print("areas reservadas por outras sessoes (fique fora delas):\n" + "\n".join("- " + _label(c) for c in cl) + "\n")
    if not items:
        print("nenhuma outra sessao com mudancas sem commit neste projeto")
        return 0
    print("outras sessoes com mudancas sem commit:\n" + render(items, limit=50))
    if a.diff:
        for it in items:
            print("\n===== %s (%s)" % (it["worktree"], it["branch"] or "?"))
            sys.stdout.write(_git(it["worktree"], "diff", "HEAD", timeout=60) or "")
    return 0


if __name__ == "__main__":
    sys.exit(main())
