#!/usr/bin/env python3
"""AISEF: criterios das tarefas de UI (autoridade de design e, desde a V-06, sonda num navegador real).

Chamado pelo `aisef_new.py feature` para cada tarefa do brief que toca UI."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import aisef_project as ap  # noqa: E402


# Exemplo de `ui_behavior` (V-06) para o `aisef_new.py example feature`: tela de nova senha.
EXAMPLE = {"base_url": "http://127.0.0.1:5173", "routes": [{"name": "nova-senha", "path": "/reset?token=exemplo", "wait_for": "form"}],
           "widths": {"<=480": "formulario em uma coluna, botao com largura total", ">=481": "cartao centralizado de ate 420 px"},
           "overflow": [{"target": ".regras-senha", "strategy": "wrap"}],
           "interactions": [{"target": ".mostrar-senha", "gesture": "click", "expect": "change"}],
           "states": ["loading", "error"]}


def is_ui(t):
    """Tarefa do brief (touches/role) ou contrato (touches/assigned_agent) que toca a interface."""
    role = t.get("role") or (t.get("assigned_agent") or {}).get("role")
    return "ui" in (t.get("touches") or []) or role == "frontend"


def add_criteria(project, tasks):
    """Acrescenta os criterios de UI ao brief: tokens de design (quando ha autoridade) e a sonda (quando ha ui_behavior)."""
    tokens = os.path.isfile(os.path.join(ap.aisef_dir(project), "design", "tokens.json"))
    for t in [t for t in tasks if is_ui(t)]:
        if tokens:
            t["criteria"].setdefault("AC-%s-DESIGN" % t["id"], {
                "text": "UI sem cores nem fontes fora da autoridade de design (.aisef/design/tokens.json)",
                "command": "python -I <CORE>/design_check.py scan --project . --task %s" % t["id"]})
        if t.get("ui_behavior"):  # V-06: UI declarada vira criterio provado pela sonda num navegador real
            t["criteria"].setdefault("AC-%s-UIPROBE" % t["id"], {
                "text": "UI provada pela sonda nas rotas e gestos declarados (5 larguras, toque e teclado), sem achado medium ou pior",
                "command": "python -I <CORE>/ui_probe.py run --project . --task %s" % t["id"]})
