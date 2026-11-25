#!/usr/bin/env python3

"""AISEF check: grupo de regras do check_project (evidencia de TDD cruzada com o log assinado, E-01 da 0.17).

O Execution Report traz os ciclos vermelho-verde que o PROPRIO agente declarou (comando, codigo de saida, horario).
Desde a 0.17 o hook de auditoria grava o resultado de cada comando de shell no log assinado (`exit_code`, inclusive dos
que falham, pelo PostToolUseFailure). Aqui cada fase de cada ciclo precisa de um comando de verdade no log: o mesmo
comando (sem o `cd <pasta> &&` do inicio), com o mesmo resultado (falhou no vermelho, passou no verde), perto do
horario declarado, e o vermelho antes do verde. O agente nao precisa fazer nada a mais.

So vale para relatorios do periodo em que o log ja grava o resultado (o primeiro evento com `exit_code`): projetos que
vem de antes da 0.17 nao passam a falhar de uma hora para a outra."""

import re

from check_project import *  # noqa: F401,F403

WINDOW = datetime.timedelta(minutes=15)  # folga entre o horario declarado e o do evento
CD_PREFIX = re.compile(r"^\s*(?:cd|pushd|Set-Location)\s+(?:\"[^\"]*\"|'[^']*'|\S+)\s*(?:&&|;)\s*", re.I)


def norm_cmd(cmd):
    cmd = cmd or ""
    while True:
        m = CD_PREFIX.match(cmd)
        if not m:
            break
        cmd = cmd[m.end():]
    return " ".join(cmd.split())


def _when(ev):
    try:
        return parse_time(ev.get("timestamp"))
    except (ValueError, TypeError):
        return None


def shell_runs(log):
    """Eventos de comando de shell com resultado gravado: [(quando, comando normalizado, exit_code, evento)]."""
    out = []
    for ev in log:
        d = ev.get("data") or {}
        if ev.get("event_type") != "tool_used" or d.get("tool") not in ("Bash", "PowerShell"):
            continue
        if "exit_code" not in d and not d.get("failed"):
            continue
        when = _when(ev)
        if when is not None:
            out.append((when, norm_cmd(d.get("command")), d.get("exit_code"), ev))
    return out


def match_run(runs, phase, run):
    """O evento do log que sustenta a fase declarada, ou (None, motivo)."""
    try:
        at = parse_time(run["at"])
    except (ValueError, TypeError, KeyError):
        return None, "horario declarado ilegivel"
    want = norm_cmd(run.get("command"))
    near = [r for r in runs if abs(r[0] - at) <= WINDOW and want and (want == r[1] or want in r[1] or r[1] in want)]
    if not near:
        return None, "nenhum comando '%s' no log perto de %s" % (want[:80], run.get("at"))
    failed = phase == "red"
    same = [r for r in near if (r[2] != 0 if failed else r[2] == 0)]
    if not same:
        return None, "o log mostra '%s' %s, mas o relatorio diz que %s" % (
            want[:60], "passando" if failed else "falhando", "falhou" if failed else "passou")
    return min(same, key=lambda r: abs(r[0] - at)), None


def rules_tdd_no_log(_cx):
    """Regras: evidencia de TDD cruzada com o log assinado (E-01)."""
    project, rep, reports, log = _cx.get("project"), _cx.get("rep"), _cx.get("reports"), _cx.get("log") or []
    runs = shell_runs(log)
    recorded = [r[0] for r in runs if "exit_code" in (r[3].get("data") or {})]
    if not recorded or not reports:
        return  # o log ainda nao grava o resultado dos comandos (projeto de antes da 0.17)
    since = min(recorded)
    try:
        with open(os.path.join(project, "config.json"), encoding="utf-8") as fh:
            profile = (json.load(fh) or {}).get("profile") or "team"
    except (OSError, ValueError, AttributeError):
        profile = "team"
    say = rep.warn if profile == "solo" else rep.err
    for r in reports:
        where = "relatorio " + r["report_id"]
        for i, c in enumerate((r.get("tdd_evidence") or {}).get("cycles", []), 1):
            try:
                if parse_time(c["green"]["at"]) < since:
                    continue  # ciclo inteiro de antes de o log gravar resultados (pelo verde: um vermelho que nunca
                    # rodou nao pode escapar so por vir antes do primeiro evento gravado)
            except (ValueError, TypeError, KeyError):
                continue  # TDD-RED-BEFORE-GREEN ja acusa horario ilegivel
            label = "ciclo %d (%s)" % (i, c.get("test", "?"))
            found = {}
            for phase in ("red", "green"):
                hit, why = match_run(runs, phase, c[phase])
                if hit is None:
                    say("TDD-EVIDENCE-UNBACKED", where, "%s, %s: %s" % (label, "vermelho" if phase == "red" else "verde", why))
                found[phase] = hit
            if found.get("red") and found.get("green") and found["red"][0] >= found["green"][0]:
                say("TDD-EVIDENCE-UNBACKED", where, "%s: no log, o verde (%s) veio antes do vermelho (%s)"
                    % (label, found["green"][3].get("event_id"), found["red"][3].get("event_id")))
