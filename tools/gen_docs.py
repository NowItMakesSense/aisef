#!/usr/bin/env python3
"""Gera docs/reference/check-rules.md a partir do codigo do check (fonte unica), para a lista de regras nunca
ficar desatualizada. Uso: python tools/gen_docs.py [--check]   (--check: falha se o arquivo estiver diferente)
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "plugins", "aisef", "core")
SOURCES = ["check_project.py", "check_rules_1.py", "check_rules_2.py", "check_rules_3.py", "check_knowledge.py"]
NOT_RULES = {"FEAT-MAINT"}  # id da feature de manutencao, nao uma regra
OUT = os.path.join(ROOT, "docs", "reference", "check-rules.md")

GROUPS = [
    ("PROJECT", "Projeto", "a pasta tem documentos AISEF para checar"),
    ("ID", "Identificadores", "ids unicos e nomes de arquivo coerentes"),
    ("POLICY", "Política", "a política de permissões é válida"),
    ("PERM", "Permissões", "recursos e escopos das tarefas respeitam a política"),
    ("AGENT", "Agentes", "Agent Contracts ativos, papel, teto de recursos e de ambiente"),
    ("FEAT", "Feature Contract", "requisitos, critérios e arquitetura da feature"),
    ("TRIAGE", "Triagem", "caminho quick, lean ou full escolhido em código, sem rebaixar"),
    ("BUDGET", "Orçamento", "limites da feature no modo contínuo só podem baixar os do projeto"),
    ("PROFILE", "Perfil", "perfil regulated: sem caminho rápido, TDD e blueprint em risco alto"),
    ("PLAN", "Plano de tarefas", "plano coerente com a feature e os papéis"),
    ("TASK", "Task Contracts", "requisitos e critérios ligados, sem ciclos"),
    ("DEP", "Dependências", "dependências existem e não formam ciclo"),
    ("PAR", "Paralelismo", "tarefas paralelas não disputam arquivos"),
    ("RTM", "Rastreabilidade (RTM)", "requisito → tarefa → critério sem buracos"),
    ("REQ", "Requisitos", "histórico de versões dos requisitos"),
    ("BP", "Engineering Blueprint", "todo elemento aponta para requisitos aprovados"),
    ("REPORT", "Execution Reports", "relatório do agente coerente com a tarefa e com evidências"),
    ("SPEC", "Spec", "fatias verticais pedem spec com seams de teste aprovados"),
    ("SLICE", "Fatias verticais", "toda fatia tem ao menos um criterio verificado por teste automatizado"),
    ("TDD", "TDD", "evidencia de teste vermelho antes do verde, no relatorio do executor"),
    ("ARCH", "Arquitetura", "deteccao valida, estilo adotado aprovado como decisao arquitetural e regra de dependencia"),
    ("DESIGN", "Autoridade de design", "tokens de design validos, aprovados como decisao arquitetural, e UI coberta por eles"),
    ("VAL", "Validação", "validação independente, nunca do próprio executor"),
    ("ROUTE", "Roteamento", "validador não roda abaixo do nível do executor"),
    ("STATE", "Estado x evidência", "cada estado tem o evento e o relatório que o sustentam"),
    ("APPROVAL", "Approval Center", "pedidos, decisões e eventos consistentes"),
    ("AUTH", "Autorizações", "escopo e reforçada válidas, no prazo e na operação certa"),
    ("LOG", "Log de auditoria", "atores, ordem e referências dos eventos"),
    ("CONFIG", "Configuração", "opções do config.json"),
    ("KNW", "Memória de projeto", "entradas de .aisef/knowledge com fonte e sem segredos"),
]


def collect():
    rules = set()
    for name in SOURCES:
        with open(os.path.join(CORE, name), encoding="utf-8") as fh:
            rules.update(re.findall(r'"([A-Z]{2,}(?:-[A-Z0-9]+)+)"', fh.read()))
    return sorted(r for r in rules if r.split("-")[0] in {g[0] for g in GROUPS} and r not in NOT_RULES)


def render(rules):
    lines = ["# Regras do aisef-check", "",
             "Gerado por `tools/gen_docs.py` a partir de `core/check_project.py` e `core/check_knowledge.py`. "
             "Não edite à mão.", "",
             "**%d regras** em %d grupos. Erro bloqueia a transição de estado; aviso não bloqueia." % (
                 len(rules), sum(1 for g in GROUPS if any(r.split("-")[0] == g[0] for r in rules))), ""]
    for prefix, title, what in GROUPS:
        mine = [r for r in rules if r.split("-")[0] == prefix]
        if not mine:
            continue
        lines += ["## %s (`%s-*`)" % (title, prefix), "", what[0].upper() + what[1:] + ".", "",
                  ", ".join("`%s`" % r for r in mine), ""]
    return "\n".join(lines)


def main(argv):
    text = render(collect())
    if "--check" in argv:
        try:
            with open(OUT, encoding="utf-8") as fh:
                same = fh.read() == text
        except FileNotFoundError:
            same = False
        print("docs/reference/check-rules.md " + ("em sincronia" if same else "DESATUALIZADO: rode python tools/gen_docs.py"))
        return 0 if same else 1
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("gravado", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
