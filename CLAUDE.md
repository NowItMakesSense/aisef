# AISEF (repositório do plugin)

Plugin do Claude Code, Python só com biblioteca padrão + `cryptography` e `jsonschema`. Docs e CHANGELOG em português.

## Trabalho em andamento

Plano atual: `docs/plan/plano-0.17.md`. Para retomar, leia **só a seção 1 (Estado)** e o bloco da primeira tarefa
`[ ]` ou `[~]`. Ao terminar ou pausar uma tarefa, atualize o estado ali antes de qualquer outra coisa.

## Mapa

- `plugins/aisef/hooks/`: gateway (`gateway.py`, regras em `gateway_rules.py`, `shell_parse.py`), auditoria
  (`audit_hook.py`), doctor, corpus de contornos (`corpus/gateway.jsonl`).
- `plugins/aisef/core/`: CLI (`aisef_project.py` é a fachada), check (`check_project.py`, `check_rules_*.py`),
  log (`audit_chain.py`, `audit_signing.py`), schemas `*.schema.v0.1.json`, política `permission-policy.v0.1.json`,
  agentes (`agents/`, gerados por `tools/gen_agents.py`).
- `plugins/aisef/skills/`: skills; `docs/adr/`: decisões; `docs/reference/maturity.md`: maturidade por ID de tarefa.

## Testes

- Suíte inteira: `python run_tests.py --jobs 6` (cerca de 5 min). Rode só no fechamento.
- Só uma área: `python run_tests.py --jobs 4 --only gateway` (filtra pelo nome da suíte).
- Durante o trabalho, a suíte da área (cada `test_*.py` é um script autônomo):
  gateway `python -I plugins/aisef/hooks/test_gateway_corpus.py` e `test_gateway.py`;
  check `python -I plugins/aisef/core/test_check_project.py`; docs `python tools/gen_docs.py --check`.

## Regras do repositório

- Toda entrega: teste no `run_tests.py`, entrada no CHANGELOG, linha em `docs/reference/maturity.md` para o ID citado
  (o `gen_docs --check` falha sem ela), ADR quando a política muda.
- Agentes: edite a fonte em `plugins/aisef/core/agents/` e rode `python tools/gen_agents.py`; nunca edite
  `plugins/aisef/agents/*.md` à mão.
- Nenhum módulo do núcleo passa de 500 linhas.
- Branch `feat/*`, PR para `main`; commit só quando o usuário pedir.
