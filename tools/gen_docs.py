#!/usr/bin/env python3
"""Gera docs/reference/check-rules.md a partir do codigo do check (fonte unica), para a lista de regras nunca
ficar desatualizada. Uso: python tools/gen_docs.py [--check]   (--check: falha se o arquivo estiver diferente)

Tambem confere, em qualquer modo: o roadmap cita toda versao do CHANGELOG (H-02) e os numeros do README (regras,
casos do gateway, agentes, boas praticas) batem com o codigo. O piso de verificacoes do README e conferido pelo
run_tests.py, que e quem mede o total.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE = os.path.join(ROOT, "plugins", "aisef", "core")
SOURCES = ["check_project.py", "check_rules_1.py", "check_rules_2.py", "check_rules_3.py", "check_rules_4.py", "check_knowledge.py"]
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
    ("TELEMETRY", "Telemetria", "a cadeia de hash da telemetria (fora do log assinado) está íntegra"),
    ("BUDGET", "Orçamento", "limites da feature no modo contínuo só podem baixar os do projeto"),
    ("PROFILE", "Perfil", "perfil regulated: sem caminho rápido, TDD e blueprint em risco alto"),
    ("PLAN", "Plano de tarefas", "plano coerente com a feature e os papéis"),
    ("TASK", "Task Contracts", "requisitos e critérios ligados, sem ciclos"),
    ("DEP", "Dependências", "dependências existem e não formam ciclo"),
    ("FEATURE", "Dependências entre features", "toda feature declara de quais depende ([] = independente), sem dependência inexistente nem ciclo"),
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


def roadmap_gaps():
    """H-02: versoes do CHANGELOG que o docs/roadmap.md nao cita (o roadmap nao pode ficar para tras)."""
    root = ROOT
    with open(os.path.join(root, "CHANGELOG.md"), encoding="utf-8") as fh:
        versions = re.findall(r"^## (\d+\.\d+\.\d+)", fh.read(), re.M)
    with open(os.path.join(root, "docs", "roadmap.md"), encoding="utf-8") as fh:
        roadmap = fh.read()
    return [v for v in versions if not re.search(r"\|\s*~?~?%s~?~?\s*\|" % re.escape(v), roadmap)]


READMES = ("README.md", "README.pt-BR.md")
# Numeros que o README afirma, onde aparecem (ingles e portugues). A secao de novidades fica de fora: ela conta a
# historia de cada versao, com os numeros daquela epoca.
ROW = r"^\| \*\*(\d+)\*\* \| \*\*[\d.,]+\+?\*\* \| \*\*(\d+)\*\* \| \*\*(\d+)\*\* \|"  # regras | verificacoes | gateway | agentes
CLAIMS = {  # (padrao, numero) por idioma; a linha de numeros do topo vale para os dois
    "README.md": [(r"checked by (\d+) rules", "rules"), (r"(\d+) of them bypass attempts", "bypass"),
                  (r"(\d+) specialists:", "agents"),
                  (r"\((\d+) active on a new Python project", "python_agents"), (r"core team \((\d+) subagents", "core_agents"),
                  (r"Best-practice library\*\* \| (\d+) rules", "practices")],
    "README.pt-BR.md": [(r"conferido por (\d+) regras", "rules"), (r"(\d+) deles tentativas de contorno", "bypass"),
                        (r"(\d+) especialistas:", "agents"),
                        (r"\((\d+) ativos num projeto Python novo", "python_agents"), (r"núcleo \((\d+) subagentes", "core_agents"),
                        (r"Biblioteca de boas práticas\*\* \| (\d+) regras", "practices")],
}
CHECKS_CLAIM = r"^\| \*\*\d+\*\* \| \*\*([\d.,]+)\+\*\* \|"  # "2,500+": piso arredondado das verificacoes


def readme_facts():
    """Os numeros de verdade, calculados do codigo (sem rodar as suites)."""
    sys.path.insert(0, CORE)
    import aisef_catalog as cat
    with open(os.path.join(ROOT, "plugins", "aisef", "hooks", "corpus", "gateway.jsonl"), encoding="utf-8") as fh:
        corpus = [json.loads(x) for x in fh if x.strip()]
    roles = [r for r in cat.roles() if r["id"] != "orchestrator"]
    practices = sum(1 for _d, _s, files in os.walk(os.path.join(CORE, "practices")) for f in files if f.endswith(".md"))
    return {"rules": len(collect()), "gateway_cases": len(corpus), "bypass": sum(1 for c in corpus if c.get("bypass")),
            "agents": len(roles), "python_agents": sum(1 for r in roles if cat.applicable(r, ("python",))),
            "core_agents": sum(1 for r in roles if r["activation"] == "always" and r.get("tier", "core") == "core"),
            "practices": practices}


def _num(raw):
    return int(re.sub(r"[.,]", "", raw))


def readme_problems(facts=None, checks_total=None):
    """Numero do README que nao bate com o codigo. checks_total (do run_tests): o README traz um piso arredondado
    ("2,500+"); falha se o piso passar do medido ou se ficar mais de 10% abaixo (desatualizado)."""
    facts = facts if facts is not None else readme_facts()
    out = []
    for name in READMES:
        with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
            text = fh.read()
        text = re.sub(r"^## (?:What's new|Novidades)\s*$.*?(?=^## )", "", text, flags=re.M | re.S)
        if checks_total is None:
            row = re.search(ROW, text, re.M)
            if not row:
                out.append("%s: nao achei a linha de numeros do topo (regras | verificacoes | gateway | agentes)" % name)
            found = [(k, row.group(i + 1)) for i, k in enumerate(("rules", "gateway_cases", "agents"))] if row else []
            for pattern, key in CLAIMS[name]:
                hits = re.findall(pattern, text, re.M)
                if not hits:
                    out.append("%s: nao achei o numero de %s (padrao %r)" % (name, key, pattern))
                found += [(key, raw) for raw in hits]
            for key, raw in found:
                if _num(raw) != facts[key]:
                    out.append("%s: diz %s para %s; o codigo tem %d" % (name, raw, key, facts[key]))
        else:
            m = re.search(CHECKS_CLAIM, text, re.M)
            if not m:
                out.append("%s: nao achei o piso de verificacoes (ex.: **2,500+**) na linha de numeros" % name)
            elif _num(m.group(1)) > checks_total or _num(m.group(1)) < 0.9 * checks_total:
                out.append("%s: diz %s+ verificacoes; o run_tests mediu %d (o piso deve ficar entre 90%% e 100%%)"
                           % (name, m.group(1), checks_total))
    return out


MATURITY_SINCE = (0, 13, 0)
TASK_ID = r"\(((?:[A-Z]-\d{2}[a-z]?|D\d)(?:[ ,+]+(?:[A-Z]-\d{2}[a-z]?|D\d))*)[,)]"


def maturity_gaps():
    """IDs de tarefa do CHANGELOG (da 0.13 em diante) que docs/reference/maturity.md nao lista: todo recurso novo
    diz se ja rodou em uso real ou so no CI, e como voltar atras."""
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as fh:
        log = fh.read()
    with open(os.path.join(ROOT, "docs", "reference", "maturity.md"), encoding="utf-8") as fh:
        listed = set(re.findall(r"^\| ([A-Z]-\d{2}[a-z]?|D\d) \|", fh.read(), re.M))
    want = set()
    for ver, body in re.findall(r"^## (\d+\.\d+\.\d+)[^\n]*\n(.*?)(?=^## |\Z)", log, re.M | re.S):
        if tuple(int(x) for x in ver.split(".")) >= MATURITY_SINCE:
            for group in re.findall(TASK_ID, body):
                want.update(re.findall(r"[A-Z]-\d{2}[a-z]?|D\d", group))
    return sorted(want - listed)


def main(argv):
    text = render(collect())
    gaps = roadmap_gaps()
    if gaps:
        print("docs/roadmap.md DESATUALIZADO: faltam as versoes %s do CHANGELOG" % ", ".join(gaps))
        return 1
    missing = maturity_gaps()
    if missing:
        print("docs/reference/maturity.md DESATUALIZADO: faltam %s (recursos do CHANGELOG da 0.13 em diante)" % ", ".join(missing))
        return 1
    wrong = readme_problems()
    if wrong:
        print("README DESATUALIZADO:\n  " + "\n  ".join(wrong))
        return 1
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
