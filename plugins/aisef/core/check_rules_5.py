#!/usr/bin/env python3

"""AISEF check: grupo de regras do check_project para a verificacao de UI (V-06 e V-07 da 0.18).

V-06: a tarefa de UI declara antes de codar como se comporta (`ui_behavior`: rotas, larguras, overflow, gestos e
estados), e o executor so entrega com a sonda de UI (`ui_probe.py`) anexada ao relatorio e sem achado medium ou pior.
Vale para tarefa com `ui_behavior`: as antigas, de antes do processo, recebem so o aviso de que falta declarar."""

import os

from check_project import *  # noqa: F401,F403
from aisef_ui import is_ui  # noqa: E402

OPEN = {"draft", "ready", "in_progress", "blocked"}
DELIVERED = {"executed", "validated", "completed"}
SEV = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def find_file(project, ref):
    """A evidencia cita o caminho a partir da raiz do repositorio (.aisef/...) ou da propria pasta .aisef."""
    for base in (os.path.dirname(project), project):
        p = os.path.normpath(os.path.join(base, ref))
        if os.path.isfile(p):
            return p
    return None


def probe_evidence(project, reports, tid):
    """(relatorio, caminho do report.json da sonda) do ultimo Execution Report da tarefa que anexou a sonda."""
    found = (None, None)
    for r in reports:
        if r.get("task_id") != tid:
            continue
        for e in r.get("evidence") or []:
            if e.get("type") == "ui_probe":
                found = (r, find_file(project, e.get("ref", "")) or e.get("ref"))
    return found


def rules_ui(_cx):
    """Regras: UI declarada e provada pela sonda (V-06)."""
    project, tasks, reports, rep = _cx.get("project"), _cx.get("tasks") or {}, _cx.get("reports") or [], _cx.get("rep")
    for tid, t in sorted(tasks.items()):
        if not is_ui(t):
            continue
        st = (t.get("state") or {}).get("status")
        where = "tarefa " + tid
        if not t.get("ui_behavior"):
            if st in OPEN:
                rep.warn("UI-BEHAVIOR-MISSING", where, "tarefa de UI sem ui_behavior: declare rotas, o que muda em cada "
                         "largura, o que fazer quando o conteudo nao cabe, os gestos esperados e os estados, antes de codar")
            continue
        if st not in DELIVERED:
            continue
        r, path = probe_evidence(project, reports, tid)
        if not r:
            rep.err("UI-PROBE-MISSING", where, "entregue sem a sonda de UI no relatorio: rode python -I <CORE>/ui_probe.py "
                    "run --project . --task %s e anexe o report.json como evidencia do tipo ui_probe" % tid)
            continue
        if not path or not os.path.isfile(path):
            rep.err("UI-PROBE-MISSING", where, "o relatorio %s cita a sonda em %s, que nao existe" % (r.get("report_id"), path))
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                probe = json.load(fh)
        except (OSError, ValueError) as e:
            rep.err("UI-PROBE-MISSING", where, "relatorio da sonda ilegivel (%s): %s" % (path, e))
            continue
        bad = [f for f in probe.get("findings") or [] if SEV.get(f.get("severity"), 0) >= SEV["medium"]]
        if bad:
            rep.err("UI-PROBE-DIRTY", where, "a sonda anexada tem %d achado(s) medium ou pior (ex.: %s %s em %s px): corrija "
                    "ou registre a excecao com motivo em .aisef/ui-probe.ignore.json"
                    % (len(bad), bad[0].get("rule"), bad[0].get("selector", ""), bad[0].get("width")))
        names = {x.get("name") for x in probe.get("routes") or []}
        missing = [x["name"] for x in t["ui_behavior"].get("routes") or [] if x.get("name") not in names]
        if missing:
            rep.err("UI-PROBE-MISSING", where, "a sonda anexada nao passou pelas rotas declaradas: %s" % ", ".join(missing))
        gestures = {(i.get("target"), i.get("gesture")) for i in probe.get("interactions") or []}
        undone = [i for i in t["ui_behavior"].get("interactions") or [] if (i["target"], i["gesture"]) not in gestures]
        if undone:
            rep.err("UI-PROBE-MISSING", where, "gesto declarado sem teste na sonda: %s em %s" % (undone[0]["gesture"], undone[0]["target"]))
